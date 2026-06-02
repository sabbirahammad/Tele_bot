import sqlite3
import os
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta

# ডাটাবেজ ফাইলের পাথ ডাইনামিকভাবে সেট করা (Windows/Linux উভয়ের জন্য নিরাপদ)
# Railway বা Docker এর ক্ষেত্রে /app/database/users.db ব্যবহার করা হবে
DB_DIR = os.getenv("DB_DIR", os.path.dirname(__file__))
DB_PATH = os.path.join(DB_DIR, "users.db")

def get_today_date_str():
    # BD Time (UTC+6)
    bd_time = datetime.now(timezone.utc) + timedelta(hours=6)
    return bd_time.strftime("%Y-%m-%d")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)
        # মাইগ্রেশন: users টেবিলে last_verified_date কলাম যোগ করা
        cursor.execute("PRAGMA table_info(users)")
        users_columns = [row[1] for row in cursor.fetchall()]
        if "last_verified_date" not in users_columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN last_verified_date TEXT")
            except sqlite3.OperationalError:
                pass

        # মাইগ্রেশন: users টেবিলে registration_date কলাম যোগ করা
        if "registration_date" not in users_columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN registration_date TEXT")
                # For existing users, set registration_date to their last_verified_date if available, else current date
                cursor.execute("UPDATE users SET registration_date = COALESCE(last_verified_date, ?)", (get_today_date_str(),))
            except sqlite3.OperationalError:
                pass
                
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_files (
                file_id TEXT PRIMARY KEY,
                file_name TEXT,
                file_size INTEGER,
                message_id INTEGER,
                channel_id INTEGER
            )
        """)
        # মাইগ্রেশন: যদি পুরনো ডাটাবেজ থাকে তবে কলামগুলো যোগ করবে
        cursor.execute("PRAGMA table_info(channel_files)")
        columns = [row[1] for row in cursor.fetchall()]
        if "message_id" not in columns:
            try:
                cursor.execute("ALTER TABLE channel_files ADD COLUMN message_id INTEGER")
                cursor.execute("ALTER TABLE channel_files ADD COLUMN channel_id INTEGER")
            except sqlite3.OperationalError:
                pass
                
        # channels টেবিল আপডেট: channel_name কলাম যোগ করা
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT
            )
        """)
        cursor.execute("PRAGMA table_info(channels)")
        ch_columns = [row[1] for row in cursor.fetchall()] # Fetch column names
        
        # Add channel_name column if not exists
        if "channel_name" not in ch_columns:
            try: cursor.execute("ALTER TABLE channels ADD COLUMN channel_name TEXT")
            except sqlite3.OperationalError: pass
                
        # Add invite_link column if not exists
        if "invite_link" not in ch_columns:
            try: cursor.execute("ALTER TABLE channels ADD COLUMN invite_link TEXT")
            except sqlite3.OperationalError: pass

        # Add category column if not exists, with a default value
        if "category" not in ch_columns:
            try: cursor.execute("ALTER TABLE channels ADD COLUMN category TEXT DEFAULT 'অন্যান্য'")
            except sqlite3.OperationalError: pass

        # FTS5 Virtual Table তৈরি করা (এটি দ্রুত সার্চের জন্য ইনডেক্স ধরে রাখে)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS channel_files_fts USING fts5(
                file_name,
                content='channel_files',
                content_rowid='rowid'
            )
        """)
        
        # ট্র্রিগার তৈরি করা যাতে অরিজিনাল টেবিলে ডাটা ঢুকলে অটোমেটিক FTS ইনডেক্স আপডেট হয়
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS channel_files_ai AFTER INSERT ON channel_files BEGIN
                INSERT INTO channel_files_fts(rowid, file_name) VALUES (new.rowid, new.file_name);
            END;
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS channel_files_ad AFTER DELETE ON channel_files BEGIN
                INSERT INTO channel_files_fts(channel_files_fts, rowid, file_name) VALUES('delete', old.rowid, old.file_name);
            END;
        """)

        conn.commit()
    
    # প্রতিবার ডাটাবেজ ইনিশিয়ালাইজ হওয়ার সময় সব চ্যানেলের ক্যাটাগরি পুনরায় চেক করে আপডেট করা হবে
    recalculate_all_categories()
    
    # যদি আগে থেকে ডাটা থাকে, তবে FTS টেবিল পপুলেট করা (একবারই চলবে)
    sync_fts_index()


def add_user(user_id, username):
    today = get_today_date_str()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # INSERT OR IGNORE ব্যবহার করা হচ্ছে। যদি ইউজার না থাকে, তবে নতুন করে যোগ হবে এবং registration_date সেট হবে।
        # যদি ইউজার থাকে, তবে কোনো পরিবর্তন হবে না।
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, registration_date) VALUES (?, ?, ?)", (user_id, username, today))
        conn.commit()

def is_user_verified(user_id):
    is_verified_today, _ = get_user_status(user_id)
    return is_verified_today

def get_user_status(user_id):
    """ইউজারের ভেরিফিকেশন স্ট্যাটাস এবং এটি তার প্রথম দিন কিনা তা রিটার্ন করে।"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_verified_date, registration_date FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result:
            last_verified_date_str = result[0]
            registration_date_str = result[1]
            
            today_str = get_today_date_str()
            is_first_day = (registration_date_str == today_str)
            is_verified_today = (last_verified_date_str == today_str) or is_first_day
            return is_verified_today, is_first_day
        return False, False # User not found

def verify_user(user_id):
    today = get_today_date_str()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Ensure user exists first and registration_date is set if new
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, registration_date) VALUES (?, ?, ?)", (user_id, "User", today))
        cursor.execute("UPDATE users SET last_verified_date = ? WHERE user_id = ?", (today, user_id))
        conn.commit()

def search_files(query):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # আরও উন্নত ক্লিনিং: বন্ধনী এবং অন্যান্য সিম্বল বাদ দেওয়া
        clean_query = re.sub(r'[.\-_@()\[\]{}]', ' ', query)
        keywords = [k.strip() for k in clean_query.split() if k.strip()]
        
        if not keywords:
            return []
            
        # লেভেল ১: FTS5 সার্চ (BM25 Ranking ব্যবহার করে যাতে প্রাসঙ্গিক ফাইল উপরে থাকে)
        fts_query = " ".join([f'"{kw}"*' for kw in keywords])
        
        try:
            cursor.execute("""
                SELECT file_name, file_size, message_id, channel_id 
                FROM channel_files 
                JOIN channel_files_fts ON channel_files.rowid = channel_files_fts.rowid
                WHERE channel_files_fts MATCH ?
                ORDER BY rank, file_size DESC LIMIT 100
            """, (fts_query,))
            results = cursor.fetchall()
        except sqlite3.OperationalError:
            results = []

        # লেভেল ২: উন্নত Fallback (যদি FTS এ কিছু না পাওয়া যায়)
        if not results:
            # প্রতিটি কিওয়ার্ড আলাদাভাবে LIKE দিয়ে চেক করা (AND লজিক)
            like_conditions = " AND ".join(["file_name LIKE ?" for _ in keywords])
            like_params = [f"%{kw}%" for kw in keywords]
            
            cursor.execute(f"""
                SELECT file_name, file_size, message_id, channel_id 
                FROM channel_files 
                WHERE {like_conditions} 
                ORDER BY file_size DESC LIMIT 100
            """, like_params)
            results = cursor.fetchall()
                
        # ডুপ্লিকেট রেজাল্ট বাদ দেওয়া (একই ফাইল হয়তো দুই চ্যানেলে থাকতে পারে)
        unique_results = []
        seen = set()
        for res in results:
            # message_id এবং channel_id দিয়ে ইউনিক চেক
            ident = (res[2], res[3])
            if ident not in seen:
                seen.add(ident)
                unique_results.append(res)

        return unique_results[:100]

def add_channel_file(file_id, file_name, file_size, message_id, channel_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # INSERT OR IGNORE এর বদলে REPLACE ব্যবহার করছি যাতে ফাইলের নাম বা লোকেশন আপডেট হতে পারে
        cursor.execute("""
            INSERT OR REPLACE INTO channel_files (file_id, file_name, file_size, message_id, channel_id)
            VALUES (?, ?, ?, ?, ?)
        """, (file_id, file_name, file_size, message_id, channel_id))
        conn.commit()

def count_channel_files():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM channel_files")
        return cursor.fetchone()[0]

def count_users():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]

# Adult keywords list for grouping into Porn category
ADULT_KEYWORDS = {
    "porn", "xxx", "18+", "adult", "sex", "nude", "choti", "vabi", "boudi", 
    "ullu", "xvideo", "xnxx", "brazzers", "deshi", "desi", "mms", "leaked",
    "hot", "kamar", "choda", "magi", "kutta", "bf", "blue film", "mia khalifa",
    "koku", "kooku", "primeshots", "voovi", "rabbit", "hotwebseries", "bangla choti",
    "choti golpo", "khanki", "nengta", "nengti", "nudity", "bhabi", "desi bhabi",
    "xnx", "xhamster", "pornhub", "onlyfans", "slut", "whore", "boobs", "pussy",
    "dick", "cock", "milf", "stepmom", "incest", "bostir", "bosti", "kacha", "khamar",
    "chodachudi", "gud", "voda", "bara", "shala", "shali", "fuck", "fucking",
    "hardcore", "softcore", "bdsm", "hentai", "jav", "lesbian", "gay", "bisexual",
    "trans", "shemale", "cum", "cumshot", "creampie", "squirting", "squirt",
    "orgasm", "masturbation", "blowjob", "handjob", "tit", "tits", "ass", "booty",
    "butt", "anal", "deepthroat", "facial", "gangbang", "threesome", "orgy",
    "amateur", "homemade", "webcam", "cam", "strip", "stripper", "naked",
    "erotic", "erotica", "sensual", "kamasutra", "lust", "desire", "passion",
    "seduction", "seduce", "flirt", "x-rated", "uncensored", "nsfw", "dirty", "filthy",
    "naughty", "smut", "smutty", "kinky", "fetish", "taboo", "bhojpuri", "telugu sex",
    "bengali sex", "bangla sex", "tamil sex", "mallu", "mallu auntie", "aunty", 
    "chudasi", "devor", "nonod", "shashuri", "shashur", "debor",
    "nanad", "sasuri", "sasur", "shalika", "jamai", "bou", "stri",
    "shami", "purush", "mohila", "meye", "chele", "dudh", "khankir", "magir", "vesha",
    "besha", "notiboy", "notigirl", "callgirl", "escort", "prostitute", "brothel",
    "red light", "kotha", "randi", "raand", "chinnal", "chinal", "kutti",
    "suar", "shuor", "haramkhor", "haramzada", "haramzadi", "banchod", "madarchod",
    "behenchod", "bhosdike", "chutiya", "gandu", "laura", "lawra", "lodu", "loda",
    "bada", "baal", "bichi", "khada", "daraise", "vitor", "bahir", "dhuka", "ber kor",
    "jolochitra", "jouno", "kamonmotta", "kamona", "vasana", "jounota", "jounomilon",
    "sohobash", "milon", "shohobash", "chumu", "ador", "gujarati sex",
    "punjabi sex", "marathi sex", "kannada sex", "malayalam sex", "urdu sex", "pakistani sex",
    "nepali sex", "sri lankan sex", "indian sex", "desi sex", "asian sex", "village sex",
    "scandal", "mms scandal", "viral video", "leaked video", "hidden cam", "spy cam",
    "bathroom cam", "changing room", "hotel room", "oyo room", "oyo sex", "gf bf",
    "lover sex", "first night", "suhag raat", "basor raat", "bangladeshi randi",
    "bd randi", "dhaka call girl", "sylhet call girl", "chittagong call girl",
    "bangla audio story", "bangla choti audio", "hot natok", "hot telefilm",
    "playboy", "penthouse", "hustler", "bondage", "discipline", "sadism", "masochism",
    "domination", "submission", "master", "slave", "mistress", "roleplay",
    "schoolgirl", "flight attendant", "stewardess", "courtesan", "concubine",
    "harem", "polygamy", "polyandry", "swinging", "swinger", "cuckold", "cuckquean",
    "cuck", "hotwife", "stag", "vixen", "unicorn", "foursome", "bukkake", "gokkun",
    "swallow", "spit", "snowball", "felching", "rimming", "anilingus", "cunnilingus",
    "fellatio", "footjob", "titjob", "paizuri", "boobjob", "thighjob", "armpitjob",
    "hairjob", "facejob", "earjob", "nosejob", "eyejob", "lipjob", "tonguejob", "gumjob",
    "toothjob", "throatjob", "gagging", "choking", "breathplay", "asphyxiation",
    "autoerotic", "fingering", "fisting", "dildo", "vibrator", "plug",
    "beads", "v-string", "c-string", "jockstrap"
}

WEB_SERIES_KEYWORDS = {
    "webseries", "series", "ott", "netflix", "prime", "disney", "hotstar", "hulu", "hbo", "flix", "cine", "cinema", "movie", "films", "entertainment", "streaming", "stream", "binge", "watch", "hd", "uhd", "fhd", "bluray", "webdl", "hdrip", "dualaudio", "multiaudio", "englishseries", "hindiseries", "koreandrama", "kdrama", "jdrama", "cdrama", "turkishseries", "anime", "animeseries", "cartoon", "hollywood", "bollywood", "southmovie", "tollywood", "kollywood", "punjabimovies", "banglaseries", "banglaott", "banglacinema", "cinehub", "moviehub", "serieshub", "otthub", "dramahub", "flixhub", "streamhub", "mediahub", "hub", "world", "zone", "club", "house", "kingdom", "empire", "arena", "planet", "universe", "galaxy", "network", "central", "point", "base", "vault", "archive", "collection", "library", "studio", "factory", "depot", "lounge", "corner", "junction", "portal", "spot", "express", "premium", "vip", "pro", "plus", "exclusive", "official", "unlimited", "mega", "ultra", "ultimate", "supreme", "elite", "royal", "master", "top", "best", "daily update", "updates", "newrelease", "trending", "viral", "popular", "latest", "fresh", "spotlight", "featured", "original", "classic", "golden", "blockbuster", "hitseries", "hitmovies", "superhit", "epic", "legend", "infinity", "alpha", "apex", "primetime", "showtime", "nightflix", "movieverse", "cineverse", "seriesverse", "ottverse", "dramaverse", "flixzone", "cinezone", "moviezone", "serieszone", "ottzone", "dramazone", "streamzone", "movieworld", "cineworld", "seriesworld", "ottworld", "dramaworld", "flixworld", "movieclub", "cineclub", "seriesclub", "ottclub", "dramaclub", "bingeclub", "watchclub", "moviekingdom", "cinekingdom", "serieskingdom", "ottkingdom", "movieempire", "cineempire", "seriesempire", "ottempire", "dramaempire", "movieplanet", "cineplanet", "seriesplanet", "ottplanet", "dramaplanet", "moviegalaxy", "cinegalaxy", "seriesgalaxy", "ottgalaxy", "dramagalaxy", "movievault", "cinevault", "seriesvault", "ottvault", "dramavault", "moviearchive", "cinearchive", "seriesarchive", "ottarchive", "dramaarchive", "movielibrary", "cinelibrary", "serieslibrary", "ottlibrary", "dramalibrary", "moviestation", "cinestation", "seriesstation", "ottstation", "dramastation", "bingeworld", "watchworld", "streamworld", "mediaworld", "moviecafe", "cinecafe", "ottcafe", "flixcafe", "bingehub", "watchhub", "streamhub",
    # 100+ Additional Keywords
    "discovery", "paramount", "apple", "peacock", "sonyliv", "zee5", "hoichoi", "voot", "altbalaji", "mxplayer", "mubi", "crunchyroll", "funimation", "viki", "tving", "wavve", "iqiyi", "wetv", "youku", "mangotv", "viu", "bioscope", "chorki", "addatimes", "sunnxt", "aha", "erosnow", "hungama", "ullu", "koku", "kooku", "primeshots", "voovi", "rabbit", "hotwebseries", "cineprime", "hunters", "besharams", "hootzy", "jalebi", "moodx", "neonx", "primeplay", "yessma", "balloons", "fliz", "gupchup", "hotshots", "nuefliks", "palay", "redprime", "smooth", "vidman", "digimovieplex", "dreamfilm", "feelit", "highshorts", "primeflicks", "shemaroo", "stage", "tvf", "filtercopy", "dicemedia", "pocketaces", "arre", "scoopwhoop", "ttt", "girliyapa", "rvcj", "goldmines", "tseries", "penmovies", "rajshri", "yashraj", "dharma", "phantom", "balaji", "excel", "redchillies", "nadiadwala", "salman", "aamir", "hrithik", "prabhas", "alluarjun", "vijay", "ajith", "mahesh", "pawankalyan", "ntr", "ramcharan", "suriya", "vikram", "dhanush", "siva", "karthi", "dulquer", "nivin", "fahadh", "tovino", "prithviraj", "rakshit", "rishab", "rajb", "yash", "darshan", "sudeep", "puneeth", "upendra", "shiva", "pogo", "nickelodeon", "marvel", "dc", "mcu", "dceu", "starwars", "pixar", "dreamworks", "animax", "kodik", "rexdl", "apkmirror"
}

def get_adult_keyword(channel_name):
    # Replace common separators with spaces for better matching
    name_lower = re.sub(r'[\-_,.]', ' ', channel_name.lower())
    
    # Sort keywords by length descending to match multi-word phrases first
    sorted_keywords = sorted(ADULT_KEYWORDS, key=len, reverse=True)
    for kw in sorted_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', name_lower):
            return kw
    return None

def get_web_series_keyword(channel_name):
    name_lower = re.sub(r'[\-_,.]', ' ', channel_name.lower())
    # Sort by length descending to match longer phrases like "Web Series" before "Series"
    sorted_keywords = sorted(WEB_SERIES_KEYWORDS, key=len, reverse=True)
    for kw in sorted_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', name_lower):
            return kw
    return None

def clean_word(word):
    return re.sub(r'[^\w\s]', '', word).strip()

def get_first_word(text):
    words = text.split()
    for w in words:
        cleaned = clean_word(w)
        if cleaned and not cleaned.isnumeric() and len(cleaned) > 1:
            return cleaned.lower()
    return None

def guess_category(channel_name):
    if not channel_name:
        return 'অন্যান্য'
    
    adult_kw = get_adult_keyword(channel_name)
    if adult_kw:
        return f"Porn||{adult_kw.capitalize()}"
        
    web_kw = get_web_series_keyword(channel_name)
    if web_kw:
        return f"Web Series||{web_kw.capitalize()}"
        
    # Dynamic category based on first word
    first_word = get_first_word(channel_name)
    if first_word:
        return first_word.capitalize()
    
    return 'অন্যান্য'

def recalculate_all_categories():
    """ডাটাবেজে থাকা সব চ্যানেলের নাম অনুযায়ী পুনরায় ডাইনামিক ক্যাটাগরি তৈরি করবে"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_name FROM channels")
        channels = cursor.fetchall()
        
        updates = []
        
        for ch_id, ch_name in channels:
            if not ch_name:
                updates.append(("অন্যান্য", ch_id))
                continue
                
            adult_kw = get_adult_keyword(ch_name)
            if adult_kw:
                cat_name = f"Porn||{adult_kw.capitalize()}"
                updates.append((cat_name, ch_id))
                continue
                
            web_kw = get_web_series_keyword(ch_name)
            if web_kw:
                cat_name = f"Web Series||{web_kw.capitalize()}"
                updates.append((cat_name, ch_id))
            else:
                first_word = get_first_word(ch_name)
                if first_word:
                    cat_name = first_word.capitalize()
                else:
                    cat_name = "অন্যান্য"
                updates.append((cat_name, ch_id))
                
        cursor.executemany("UPDATE channels SET category = ? WHERE channel_id = ?", updates)
        conn.commit()

def add_channel(channel_id, channel_name, invite_link=None, category=None):
    if category is None or category == 'অন্যান্য':
        category = guess_category(channel_name)
        
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO channels (channel_id, channel_name, invite_link, category) VALUES (?, ?, ?, ?)", (channel_id, channel_name, invite_link, category))
        conn.commit()

def get_unique_categories():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM channels WHERE category IS NOT NULL AND category != '' ORDER BY category")
        raw_cats = [row[0] for row in cursor.fetchall()]
        
        main_cats = set()
        for cat in raw_cats:
            if cat.startswith("Porn||"):
                main_cats.add("Porn")
            elif cat.startswith("Web Series||"):
                main_cats.add("Web Series")
            else:
                main_cats.add(cat)
                
        return sorted(list(main_cats))

def get_porn_subcategories():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM channels WHERE category LIKE 'Porn||%'")
        raw_cats = [row[0] for row in cursor.fetchall()]
        
        subcats = set()
        for cat in raw_cats:
            parts = cat.split("||")
            if len(parts) > 1 and parts[1] != "Others":
                subcats.add(parts[1])
        
        # Add Others at the end if it exists
        if "Porn||Others" in raw_cats:
            return sorted(list(subcats)) + ["Others"]
        return sorted(list(subcats))

def get_web_series_subcategories():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM channels WHERE category LIKE 'Web Series||%'")
        raw_cats = [row[0] for row in cursor.fetchall()]
        
        subcats = set()
        for cat in raw_cats:
            parts = cat.split("||")
            if len(parts) > 1:
                subcats.add(parts[1])
        
        return sorted(list(subcats))

def get_channels_by_category(category_name, subcategory=None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if category_name == "Porn" and subcategory:
            full_cat = f"Porn||{subcategory}"
            cursor.execute("SELECT channel_id, channel_name, invite_link FROM channels WHERE category = ? ORDER BY channel_name", (full_cat,))
        elif category_name == "Web Series" and subcategory:
            full_cat = f"Web Series||{subcategory}"
            cursor.execute("SELECT channel_id, channel_name, invite_link FROM channels WHERE category = ? ORDER BY channel_name", (full_cat,))
        else:
            cursor.execute("SELECT channel_id, channel_name, invite_link FROM channels WHERE category = ? ORDER BY channel_name", (category_name,))
        return cursor.fetchall()

def search_channels_by_keywords(keywords):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_name, invite_link FROM channels ORDER BY channel_name")
        channels = cursor.fetchall()
        
        matched_channels = []
        for ch_id, ch_name, invite_link in channels:
            if not ch_name: continue
            name_lower = ch_name.lower()
            for kw in keywords:
                if re.search(r'\b' + re.escape(kw.lower()) + r'\b', name_lower):
                    matched_channels.append((ch_id, ch_name, invite_link))
                    break
        return matched_channels

def search_categories_by_keywords(keywords):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM channels WHERE category IS NOT NULL AND category != ''")
        raw_cats = [row[0] for row in cursor.fetchall()]
        
        main_cats = set()
        for cat in raw_cats:
            cat_lower = cat.lower()
            matched = False
            for kw in keywords:
                if re.search(r'\b' + re.escape(kw.lower()) + r'\b', cat_lower):
                    matched = True
                    break
            
            if matched:
                if cat.startswith("Porn||"):
                    main_cats.add("Porn")
                elif cat.startswith("Web Series||"):
                    main_cats.add("Web Series")
                else:
                    main_cats.add(cat)
                
        return sorted(list(main_cats))

def del_channel(channel_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        conn.commit()

def get_all_channels():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, channel_name, invite_link FROM channels")
        return cursor.fetchall()

def count_active_channels():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM channels")
        return cursor.fetchone()[0]

def get_all_users():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]

def get_files_by_channel(channel_id, limit=15):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, file_size, message_id, channel_id FROM channel_files WHERE channel_id = ? LIMIT ?", (channel_id, limit))
        return cursor.fetchall()

def get_channel_name_by_id(channel_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT channel_name FROM channels WHERE channel_id = ?", (channel_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def sync_fts_index():
    """পুরানো ডাটাগুলোকে FTS ইনডেক্সে যুক্ত করার জন্য"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM channel_files_fts")
        if cursor.fetchone()[0] == 0:
            # যদি ইনডেক্স খালি থাকে তবে সব ডাটা কপি করবে
            cursor.execute("INSERT INTO channel_files_fts(rowid, file_name) SELECT rowid, file_name FROM channel_files")
            conn.commit()
