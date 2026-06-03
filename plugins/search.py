import os
import logging
import re
import asyncio
import aiohttp
import base64
import urllib.parse
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from database import search_files, get_files_by_channel, get_channel_name_by_id, get_unique_categories, get_channels_by_category, get_all_channels, search_channels_by_keywords, search_categories_by_keywords, is_user_verified, verify_user, get_channel_invite_link, increment_category_click
from loader import GPLINKS_API, user, bot
from translation import get_string
# সার্চ রেজাল্ট পেজিনেশন হ্যান্ডেল করার জন্য মেমোরি ক্যাশ
USER_SEARCHES = {}
logger = logging.getLogger(__name__)

# গ্লোবাল কিউ এবং ট্র্যাকার: একই সাথে একাধিক ক্রলিং প্রসেস সিরিয়াল করার জন্য
CRAWL_QUEUE = asyncio.Queue()
QUEUED_QUERIES = set()
CRAWL_WORKER_TASK = None

async def crawl_worker():
    """ব্যাকগ্রাউন্ডে কিউ থেকে একটা একটা করে সার্চ কুয়েরি প্রসেস করবে"""
    while True:
        query = await CRAWL_QUEUE.get()
        try:
            await auto_join_channels(query)
        except Exception as e:
            logger.error(f"Error in crawl_worker for query '{query}': {e}")
        finally:
            CRAWL_QUEUE.task_done()
            QUEUED_QUERIES.discard(query)

async def trigger_deep_crawl(query):
    """সার্চ রেজাল্ট না পেলে এই ফাংশনটি কুয়েরিটাকে কিউতে অ্যাড করে দিবে"""
    global CRAWL_WORKER_TASK
    # যদি ওয়ার্কার টাস্ক রান না করা থাকে, তবে স্টার্ট করবে
    if CRAWL_WORKER_TASK is None or CRAWL_WORKER_TASK.done():
        CRAWL_WORKER_TASK = asyncio.create_task(crawl_worker())
    
    # ডুপ্লিকেট কুয়েরি এড়াতে সেট চেক করা
    if query not in QUEUED_QUERIES:
        QUEUED_QUERIES.add(query)
        await CRAWL_QUEUE.put(query)
        logger.info(f"Added '{query}' to deep crawl queue. Position in queue: {CRAWL_QUEUE.qsize()}")

async def auto_join_channels(query):
    """সার্চ রেজাল্ট না পাওয়া গেলে নতুন চ্যানেল খুঁজে জয়েন করার Automated Deep Crawling ফাংশন"""
    from database import add_channel, get_channel_name_by_id
    from plugins.indexer import index_chat_history
    from plugins.admin import ADMINS
    from plugins.trending_keywords import ALL_TRENDING_SUFFIXES
    
    # Generate keywords using the 500+ trending suffixes
    keywords = [f"{query} {suffix}".strip() for suffix in ALL_TRENDING_SUFFIXES]
    # Remove duplicate combinations (e.g., if query is already empty) while preserving order
    keywords = list(dict.fromkeys(keywords))
    
    total_joined = 0
    joined_chats = set()
    newly_joined_chat_ids = []

    try:
        logger.info(f"Automated Deep Crawling শুরু হয়েছে: {query} (Checking {len(keywords)} variations)")
        
        for keyword in keywords:
            if total_joined >= 15:
                break
                
            logger.info(f"Searching globally for keyword: {keyword}")
            
            try:
                async for message in user.search_global(keyword, limit=20):
                    if total_joined >= 15:
                        break
                    
                    chat = message.chat
                    if not chat or chat.type != enums.ChatType.CHANNEL or chat.id in joined_chats:
                        continue
                    
                    joined_chats.add(chat.id)
                    
                    if not get_channel_name_by_id(chat.id):
                        try:
                            # Members count check (try to get if not present)
                            try:
                                full_chat = await user.get_chat(chat.id)
                                members_count = full_chat.members_count or 0
                            except FloodWait as e:
                                logger.warning(f"FloodWait while getting chat info: {e.value}s")
                                await asyncio.sleep(e.value)
                                full_chat = await user.get_chat(chat.id)
                                members_count = full_chat.members_count or 0
                            except Exception:
                                members_count = getattr(chat, 'members_count', 0) or 0
                                
                            if members_count <= 100:
                                logger.info(f"Skipping {chat.title} because members_count ({members_count}) <= 100")
                                continue
                                
                            logger.info(f"নতুন সোর্স চ্যানেল খুঁজে পাওয়া গেছে: {chat.title} (ID: {chat.id}, Members: {members_count}). Joining...")
                            
                            try:
                                await user.join_chat(chat.id)
                            except FloodWait as e:
                                logger.warning(f"FloodWait before joining chat {chat.id}: {e.value}s")
                                await asyncio.sleep(e.value)
                                await user.join_chat(chat.id)
                            
                            link = f"https://t.me/{chat.username}" if chat.username else getattr(chat, 'invite_link', None)
                            if not link:
                                try: 
                                    link = await user.export_chat_invite_link(chat.id)
                                except FloodWait as e:
                                    await asyncio.sleep(e.value)
                                    link = await user.export_chat_invite_link(chat.id)
                                except Exception: 
                                    pass
                            
                            add_channel(chat.id, chat.title, link)
                            newly_joined_chat_ids.append(chat.id)
                            total_joined += 1
                            
                            # অ্যাডমিনকে জানানো
                            for admin_id in ADMINS:
                                try:
                                    await bot.send_message(
                                        admin_id, 
                                        f"📢 **Deep Crawling অ্যালার্ট:**\n\n"
                                        f"🔍 কিওয়ার্ড: `{keyword}`\n"
                                        f"🏷 নাম: {chat.title}\n"
                                        f"🆔 আইডি: `{chat.id}`\n"
                                        f"👥 মেম্বার: {members_count}"
                                    )
                                except Exception: pass
                                
                            logger.info(f"সফলভাবে জয়েন করা হয়েছে: {chat.title}")
                            await asyncio.sleep(10) # 10 seconds after successful join
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                        except Exception as e:
                            logger.exception(f"চ্যানেল {chat.title} (ID: {chat.id}) এ জয়েন করতে ব্যর্থ হয়েছে: {e}")
                            continue
            except FloodWait as e:
                logger.warning(f"FloodWait during search_global: {e.value}s")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.exception(f"Error in search_global for '{keyword}': {e}")
                
            await asyncio.sleep(5) # 5 seconds after every global search query

        # অটোমেটিক ইনডেক্সিং শুরু করা
        if newly_joined_chat_ids:
            logger.info(f"Deep crawling finished. Joined {len(newly_joined_chat_ids)} new channels. Starting indexing...")
            for chat_id in newly_joined_chat_ids:
                try:
                    asyncio.create_task(index_chat_history(chat_id, is_auto=True, query_ref=query))
                except Exception as e:
                    logger.error(f"Failed to start indexing for {chat_id}: {e}")
        else:
            logger.info(f"Deep crawling finished. No new valid channels found for '{query}'.")
            for admin_id in ADMINS:
                try:
                    await bot.send_message(admin_id, f"🔍 **Deep Crawling রিপোর্ট:**\n\nসার্চ কুয়েরি: `{query}`\nঅবস্থা: নতুন কোনো চ্যানেল খুঁজে পাওয়া যায়নি বা মেম্বার সংখ্যা ১০০ এর কম।")
                except Exception: pass

    except Exception as e:
        logger.exception(f"Auto-discovery failed for query '{query}': {e}")

async def get_shortlink(url):
    """GPLinks API ব্যবহার করে লিংক শর্ট করার ফাংশন"""
    # api.gplinks.com এন্ডপয়েন্টটি সবচেয়ে বেশি স্টেবল
    api_url = "https://api.gplinks.com/api"
    
    # ইউআরএলটি আগেই এনকোড করে নেওয়া ভালো যাতে স্পেশাল ক্যারেক্টার নিয়ে সমস্যা না হয়
    encoded_url = urllib.parse.quote(url)
    
    payload = {
        "api": GPLINKS_API,
        "url": encoded_url,
        "format": "text"
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(api_url, params=payload) as response:
                short_url = await response.text()
                if response.status == 200 and short_url.startswith("http"):
                    return short_url.strip()
                else:
                    print(f"Error: GPLinks API returned status {response.status}")
    except Exception as e:
        print(f"Error shortening link: {e}")
    # Return None instead of the original URL to prevent bypass
    return None

async def send_daily_verification_message(bot, message, next_action="verify_daily"):
    bot_info = await bot.get_me()
    verification_link = f"https://telegram.me/{bot_info.username}?start={next_action}"
    short_link = await get_shortlink(verification_link)
    
    if not short_link:
        return await message.reply_text(get_string("gplinks_error", message.from_user.language_code))
    
    text = get_string("verify_ad", message.from_user.language_code)
    buttons = [[InlineKeyboardButton(get_string("unlock_btn", message.from_user.language_code), url=short_link)]]
    return await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    
@Client.on_message(filters.text & filters.private)
async def search(bot, message):
    # যদি এটি একটি কমান্ড হয়
    if message.text.startswith("/"):
        if message.text.startswith("/search"):
            parts = message.text.split(None, 1)
            if len(parts) > 1:
                # If command is /search, don't translate query
                query = parts[1]
            else:
                return await message.reply_text(get_string("search_usage", message.from_user.language_code))
        elif message.text in ["/catagory", "/movie", "/livelink", "/worldcup", "/apk", "/buybot", "/series", "/porn"]:
            query = message.text
        else:
            # এটি অন্য কমান্ড (যেমন /start), তাই অন্য হ্যান্ডলারকে কাজ করতে দাও
            message.continue_propagation()
            return
    else:
        query = message.text

    lang = message.from_user.language_code

    # Free options that don't need daily verification
    if query in [get_string("apk_btn", lang), "/apk"]:
        return await message.reply_text(
            get_string("apk_download_text", lang),
            disable_web_page_preview=True
        )
    elif query in [get_string("buy_btn", lang), "/buybot"]:
        return await show_buy_bot_contact_handler(bot, message)

    # Check daily verification for all other actions
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        if query in [get_string("cat_btn", lang), "/catagory"]:
            action = "show_cats"
        else:
            if query in [get_string("porn_btn", lang), "/porn"]:
                action = "show_porn_cats" # New
            elif query in [get_string("series_btn", lang), "/series"]:
                action = "show_web_series" # New
            try:
                # কুয়েরিটিকে Base64 এ এনকোড করা হচ্ছে যাতে স্পেশাল ক্যারেক্টার হ্যান্ডেল করা যায়
                encoded_query = base64.urlsafe_b64encode(query.encode('utf-8')).decode('utf-8').rstrip('=')
                action = f"q_{encoded_query}"
                # টেলিগ্রামের ৬৪ ক্যারেক্টার লিমিট চেক
                if len(action) > 64: # If the encoded query is too long for callback_data, fallback to generic verification
                    action = "verify_daily" 
            except Exception:
                action = "verify_daily"
        
        return await send_daily_verification_message(bot, message, action)

    # Reply Keyboard বাটনগুলোর ক্লিক হ্যান্ডেল করা
    if query in [get_string("cat_btn", lang), "/catagory"]:
        return await show_categories_handler(bot, message)
    elif query in [get_string("movie_btn", lang), "/movie"]:
        return await show_movie_channels_handler(bot, message)
    elif query in [get_string("live_btn", lang), "/livelink"]:
        return await show_live_link_channels_handler(bot, message)
    elif query in [get_string("series_btn", lang), "/series"]:
        return await show_web_series_channels_handler(bot, message)
    elif query in [get_string("porn_btn", lang), "/porn"]:
        return await show_porn_categories_from_message(bot, message)
    elif query in [get_string("wc_btn", lang), "/worldcup"]:
        return await show_world_cup_info_handler(bot, message)

    wait_msg = await message.reply_text(get_string("searching", lang))
    results = search_files(query)
    
    # যদি ফাইল পাওয়া যায়, তবে সেগুলো আগে পাঠিয়ে দিই
    if results:
        if len(results) == 1:
            await wait_msg.delete()
            name, size, message_id, channel_id = results[0]
            size_mb = round(size / (1024 * 1024), 2)
            bot_info = await bot.get_me()
            
            # সরাসরি ফাইলের লিংক তৈরি
            dest_url = f"https://t.me/{bot_info.username}?start=file_{channel_id}_{message_id}"
            
            text_file = f"🎥 **{name}**\n⚖️ সাইজ: {size_mb} MB"
            buttons_file = [
                [InlineKeyboardButton(get_string("download_btn", lang), url=dest_url)],
                [InlineKeyboardButton(get_string("back_main_btn", lang), callback_data="start_menu")]
            ]
            await message.reply_text(text_file, reply_markup=InlineKeyboardMarkup(buttons_file))
        else:
            USER_SEARCHES[message.chat.id] = {"query": query, "results": results}
            await wait_msg.delete()
            await send_search_results(bot, message.chat.id, 0)
        
    # যদি রেজাল্ট ৫টির কম হয় (বা ০ হয়), তবে আমরা অতিরিক্ত ক্যাটাগরি বা চ্যানেল সাজেশন খুঁজব
    if not results or len(results) < 5:
        clean_query = re.sub(r'[.\-_@()\[\]{}]', ' ', query)
        keywords = [k.strip() for k in clean_query.split() if len(k.strip()) > 1]
        
        if keywords:
            # ১. ক্যাটাগরি চেক করা
            matched_categories = search_categories_by_keywords(keywords)
            if matched_categories:
                # যদি কোনো ফাইলই না পাওয়া যেত, তবে 'wait_msg' ডিলিট করতে হবে
                if not results:
                    await wait_msg.delete()
                
                cat_name = matched_categories[0]
                prefix = "💡 **আপনি হয়তো এই ক্যাটাগরি খুঁজছেন:**\n\n" if results else ""
                
                if cat_name == "Porn":
                    return await show_porn_categories_from_message(bot, message, prefix=prefix)
                elif cat_name == "Web Series":
                    from database import get_web_series_subcategories
                    subcats = get_web_series_subcategories()
                    if subcats:
                        buttons = []
                        row = []
                        for subcat in subcats:
                            row.append(InlineKeyboardButton(subcat, callback_data=f"show_web_subcat_{subcat}"))
                            if len(row) == 2:
                                buttons.append(row)
                                row = []
                        if row: buttons.append(row)
                        buttons.append([InlineKeyboardButton(get_string("back_cat_btn", lang), callback_data="show_categories")])
                        return await message.reply_text(
                            f"{prefix}{get_string('cat_list_title', lang, page=1)}",
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
                else:
                    channels = get_channels_by_category(cat_name)
                    if channels:
                        buttons = []
                        row = []
                        for ch_id, ch_name, invite_link in channels:
                            if invite_link:
                                row.append(InlineKeyboardButton(ch_name, url=invite_link))
                            else:
                                row.append(InlineKeyboardButton(f"{ch_name} 🔒", callback_data="no_link"))
                            if len(row) == 2:
                                buttons.append(row)
                                row = []
                        if row: buttons.append(row)
                        buttons.append([InlineKeyboardButton(get_string("back_cat_btn", lang), callback_data="show_categories")])
                        return await message.reply_text(
                            f"{prefix}📂 **Category: {cat_name}**\n\n{get_string('choose_option', lang)}",
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )

            # ২. চ্যানেল চেক করা
            matched_channels = search_channels_by_keywords(keywords)
            if matched_channels:
                if not results:
                    await wait_msg.delete()
                
                prefix = "💡 **আপনি হয়তো এই চ্যানেলগুলো খুঁজছেন:**\n\n" if results else ""
                buttons = []
                row = []
                for ch_id, ch_name, invite_link in matched_channels:
                    # Only add channels with invite links
                    row.append(InlineKeyboardButton(ch_name, url=invite_link))
                    if len(row) == 2:
                        buttons.append(row)
                        row = []
                if row: buttons.append(row)
                buttons.append([InlineKeyboardButton(get_string("back_main_btn", lang), callback_data="start_menu")])
                return await message.reply_text(
                    f"{prefix}📺 **সার্চের সাথে মিলে যাওয়া চ্যানেলসমূহ:**\n\nআপনার পছন্দের চ্যানেলে জয়েন করুন:",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )

    # যদি কোনো ফাইল বা সাজেশন কিছুই না পাওয়া যায়
    if not results:
        # ব্যাকগ্রাউন্ডে নতুন চ্যানেল খোঁজা এবং জয়েন করার টাস্ক শুরু করা
        await trigger_deep_crawl(query)
        return await wait_msg.edit_text(get_string("no_results", lang))

async def send_search_results(bot, chat_id, page):
    state = USER_SEARCHES.get(chat_id)
    if not state:
        return await bot.send_message(chat_id, "❌ Session expired. Please search again.")

    results = state["results"]
    query = state["query"]
    lang = "bn" # Default to bn or fetch from context if available

    page_size = 5
    start_idx = page * page_size
    end_idx = start_idx + page_size
    paged_results = results[start_idx:end_idx]

    bot_info = await bot.get_me()
    sent_count = 0
    for name, size, message_id, channel_id in paged_results:
        try:
            size_mb = round(size / (1024 * 1024), 2)
            # Direct link to file without ad
            dest_url = f"https://t.me/{bot_info.username}?start=file_{channel_id}_{message_id}"
            
            text_file = f"🎥 **{name}**\n⚖️ সাইজ: {size_mb} MB"
            buttons_file = [[InlineKeyboardButton("📥 ডাউনলোড / দেখুন", url=dest_url)]]
            
            await bot.send_message(chat_id, text_file, reply_markup=InlineKeyboardMarkup(buttons_file))
            sent_count += 1
            await asyncio.sleep(0.4) # ফ্লাড ওয়েট এড়াতে সামান্য বিরতি
        except Exception:
            pass

    if sent_count == 0 and page == 0:
        return await bot.send_message(chat_id, "❌ ভিডিওগুলো পাঠানো সম্ভব হয়নি। বটের হয়তো ওই চ্যানেলে অ্যাক্সেস নেই।")

    total_results = len(results)
    total_pages = (total_results + page_size - 1) // page_size

    text = get_string("search_results_title", lang, query=query, total=total_results, page=page+1, total_pages=total_pages)

    buttons = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"search_page_{page-1}"))
    if end_idx < total_results:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"search_page_{page+1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(get_string("back_main_btn", lang), callback_data="start_menu")])

    await bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^search_page_(\d+)"))
async def search_pagination_handler(bot, cb):
    page = int(cb.data.split("_")[-1])
    await cb.message.delete()
    await send_search_results(bot, cb.from_user.id, page)

async def auto_delete_message(message, delay=600):
    """নির্ধারিত সময় পর মেসেজ ডিলিট করার ফাংশন"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

@Client.on_callback_query(filters.regex(r"^fetch_"))
async def fetch_file_handler(bot, cb):
    # ক্যলব্যাক ডাটা থেকে চ্যানেল আইডি এবং মেসেজ আইডি বের করা
    _, channel_id_str, message_id_str = cb.data.split("_", 2)
    
    try:
        ch_id = int(channel_id_str)
        msg_id = int(message_id_str)
        
        sent_msg = None
        try:
            # 1. First try: Bot copies directly
            sent_msg = await bot.copy_message(
                chat_id=cb.from_user.id,
                from_chat_id=ch_id,
                message_id=msg_id
            )
        except Exception:
            # 2. Fallback: Use User client to copy to bot's DM, then bot copies to user
            from loader import user
            if not user.is_connected:
                await user.start()

            bot_me = await bot.get_me()
            user_me = await user.get_me()

            # Ensure peer is resolved or re-joined
            try:
                await user.get_chat(ch_id)
            except Exception as e:
                logger.warning(f"User client: Peer {ch_id} not resolved, attempting re-join if link available: {e}")
                link = get_channel_invite_link(ch_id)
                if link:
                    try: await user.join_chat(link)
                    except Exception as join_err: logger.warning(f"User client failed to join chat {ch_id} with link {link}: {join_err}")

            try:
                fwd_msg = await user.forward_messages(
                    chat_id=bot_me.id,
                    from_chat_id=ch_id,
                    message_ids=msg_id
                )
            except Exception as e:
                logger.error(f"User client forward failed: {e}")
                fwd_msg = None
            
            fwd_msg_id = None
            if fwd_msg:
                fwd_msg_id = fwd_msg.id if not isinstance(fwd_msg, list) else fwd_msg[0].id
            
            sent_msg = await bot.copy_message(
                chat_id=cb.from_user.id,
                from_chat_id=user_me.id,
                message_id=fwd_msg_id
            )
            
            await bot.delete_messages(chat_id=user_me.id, message_ids=fwd_msg_id)
            
        if sent_msg:
            await cb.answer("✅ ফাইলটি পাঠানো হয়েছে!")
            # ইউজারকে সতর্কতা মেসেজ পাঠানো
            warning_msg = await bot.send_message(cb.from_user.id, "⏳ **সতর্কতা:** কপিরাইট এড়াতে এই ফাইলটি ১০ মিনিট পর ডিলিট করে দেওয়া হবে।")
            asyncio.create_task(auto_delete_message(sent_msg, 600))
            asyncio.create_task(auto_delete_message(warning_msg, 600))
        else:
            await cb.answer("❌ ফাইলটি পাঠানো সম্ভব হয়নি। চ্যানেলটি হয়তো প্রাইভেট বা ডিলিট হয়ে গেছে।", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in fetch_file_handler for user {cb.from_user.id}, channel {ch_id}, message {msg_id}: {e}")
        await cb.answer("❌ ফাইলটি পাঠানো সম্ভব হয়নি। বটটি কি ওই চ্যানেলে অ্যাড করা আছে?", show_alert=True)

@Client.on_callback_query(filters.regex(r"^list_channel_files_"))
async def list_channel_files_handler(bot, cb):
    channel_id_str = cb.data.split("_")[-1]
    channel_id = int(channel_id_str)

    # Check daily verification for callback queries too
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)

    channel_name = get_channel_name_by_id(channel_id)
    if not channel_name:
        return await cb.answer("চ্যানেল খুঁজে পাওয়া যায়নি।", show_alert=True)

    results = get_files_by_channel(channel_id)

    if not results:
        return await cb.answer(f"দুঃখিত, '{channel_name}' চ্যানেলে কোনো ফাইল খুঁজে পাওয়া যায়নি।", show_alert=True)

    bot_info = await bot.get_me()
    buttons = []
    # ইউআই ক্লিন রাখতে এবং মেসেজ লিমিট এড়াতে প্রথম ১৫টি রেজাল্ট দেখানো হচ্ছে
    for name, size, message_id, ch_id in results:
        size_mb = round(size / (1024 * 1024), 2)
        # Direct link without ad
        dest_url = f"https://t.me/{bot_info.username}?start=file_{ch_id}_{message_id}"
        
        buttons.append([InlineKeyboardButton(
            text=f"📄 {name} [{size_mb} MB]",
            url=dest_url
        )])

    text = f"📁 **'{channel_name}' চ্যানেল থেকে ফাইলসমূহ:**\n\n"
    if len(results) >= 15: # Assuming get_files_by_channel has a default limit of 15
        text += "⚠️ অনেক রেজাল্ট পাওয়া গেছে, শীর্ষ ১৫টি নিচে দেওয়া হলো।"

    buttons.append([InlineKeyboardButton("⬅️ মূল মেনুতে ফিরে যান", callback_data="start_menu")])
    await cb.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cb.answer() # Acknowledge the callback

@Client.on_callback_query(filters.regex(r"^page_channels_(\d+)"))
async def browse_channels_handler(bot, cb):
    """ক্যাটাগরি বাটনগুলোর পেজিনেশন হ্যান্ডেল করার জন্য"""
    page = int(cb.data.split("_")[-1])
    page_size = 28 # 7 rows * 4 items
    channels = get_all_channels()
    
    start_idx = page * page_size
    end_idx = start_idx + page_size
    paged_channels = channels[start_idx:end_idx]
    
    if not paged_channels and page > 0:
        return await cb.answer("আর কোনো চ্যানেল নেই।", show_alert=True)

    buttons = []
    row = []
    for ch_id, ch_name, invite_link in paged_channels:
        # Only add channels with invite links
        row.append(InlineKeyboardButton(ch_name, url=invite_link))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ আগের পাতা", callback_data=f"page_channels_{page-1}"))
    if len(channels) > end_idx:
        nav_row.append(InlineKeyboardButton("➡️ পরের পাতা", callback_data=f"page_channels_{page+1}"))
    
    if nav_row: buttons.append(nav_row)

    await cb.message.edit_text(
        f"📂 **চ্যানেল লিস্ট (পাতা {page + 1}):**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def show_categories_handler(bot, target, page=0):
    categories = get_unique_categories()
    
    is_callback = isinstance(target, CallbackQuery)
    if not categories:
        if is_callback: await target.answer("কোনো ক্যাটাগরি খুঁজে পাওয়া যায়নি।", show_alert=True)
        else: await target.reply_text("কোনো ক্যাটাগরি খুঁজে পাওয়া যায়নি।")
        return
    
    page_size = 28 # 7 rows * 4 items
    start_idx = page * page_size
    end_idx = start_idx + page_size
    paged_categories = categories[start_idx:end_idx]
    
    buttons = []
    row = []
    for category in paged_categories:
        row.append(InlineKeyboardButton(category, callback_data=f"show_channels_in_category_{category}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ আগের পাতা", callback_data=f"page_categories_{page-1}"))
    if len(categories) > end_idx:
        nav_row.append(InlineKeyboardButton("➡️ পরের পাতা", callback_data=f"page_categories_{page+1}"))
    
    if nav_row: buttons.append(nav_row)
    
    buttons.append([InlineKeyboardButton("⬅️ মূল মেনুতে ফিরে যান", callback_data="start_menu")])

    text = f"📂 **ক্যাটাগরি সমূহ (পাতা {page + 1}):**\n\nআপনার পছন্দের ক্যাটাগরি নির্বাচন করুন:"
    if is_callback:
        await target.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await target.answer()
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^page_categories_(\d+)"))
async def page_categories_callback(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)
    page = int(cb.data.split("_")[-1])
    await show_categories_handler(bot, cb, page)

@Client.on_callback_query(filters.regex(r"^show_categories$"))
async def show_categories_callback(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)
    await show_categories_handler(bot, cb)

@Client.on_callback_query(filters.regex(r"^show_channels_in_category_"))
async def show_channels_by_category_handler(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)

    category_name = cb.data.split("_", 4)[-1] # Extracts category name from callback_data
    
    # ক্যাটাগরি পপুলারিটি ট্র্যাক করা হচ্ছে
    increment_category_click(category_name)

    if category_name == "Porn":
        return await show_porn_categories_from_message(bot, cb)

    if category_name == "Web Series":
        from database import get_web_series_subcategories
        subcats = get_web_series_subcategories()
        if not subcats:
            return await cb.answer("Web Series ক্যাটাগরিতে কোনো চ্যানেল নেই।", show_alert=True)
            
        buttons = []
        row = []
        for subcat in subcats:
            row.append(InlineKeyboardButton(subcat, callback_data=f"show_web_subcat_{subcat}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
        
        buttons.append([InlineKeyboardButton("⬅️ ক্যাটাগরি লিস্টে ফিরে যান", callback_data="show_categories")])

        await cb.message.edit_text(
            "📺 **Web Series সাব-ক্যাটাগরি সমূহ:**\n\nআপনার পছন্দের সাব-ক্যাটাগরি নির্বাচন করুন:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return await cb.answer()

    channels = get_channels_by_category(category_name)
    
    if not channels:
        return await cb.answer(f"'{category_name}' ক্যাটাগরিতে কোনো চ্যানেল খুঁজে পাওয়া যায়নি।", show_alert=True)
    
    buttons = []
    row = []
    for ch_id, ch_name, invite_link in channels:
        row.append(InlineKeyboardButton(ch_name, url=invite_link))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton("⬅️ ক্যাটাগরি লিস্টে ফিরে যান", callback_data="show_categories")])

    await cb.message.edit_text(
        f"📁 **'{category_name}' ক্যাটাগরির চ্যানেলসমূহ:**\n\nআপনার পছন্দের চ্যানেলে জয়েন করুন:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cb.answer()

async def show_porn_categories_from_message(bot, target, prefix=""):
    from database import get_porn_subcategories
    subcats = get_porn_subcategories()
    is_callback = isinstance(target, CallbackQuery)

    if not subcats:
        msg = "🔞 কোনো Porn সাব-ক্যাটাগরি খুঁজে পাওয়া যায়নি।"
        if is_callback: return await target.answer(msg, show_alert=True)
        else: return await target.reply_text(msg)

    buttons = []
    row = []
    for subcat in subcats:
        row.append(InlineKeyboardButton(subcat, callback_data=f"show_porn_subcat_{subcat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    buttons.append([InlineKeyboardButton("⬅️ ক্যাটাগরি লিস্টে ফিরে যান", callback_data="show_categories")])

    text = f"{prefix}🔞 **Porn সাব-ক্যাটাগরি সমূহ:**\n\nআপনার পছন্দের সাব-ক্যাটাগরি নির্বাচন করুন:"
    if is_callback:
        await target.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await target.answer()
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^show_porn_subcat_"))
async def show_porn_subcat_handler(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)

    subcategory = cb.data.split("_", 3)[-1]
    # সাব-ক্যাটাগরি পপুলারিটি ট্র্যাক করা হচ্ছে
    increment_category_click(f"Porn||{subcategory}")

    channels = get_channels_by_category("Porn", subcategory)
    
    if not channels:
        return await cb.answer(f"'{subcategory}' সাব-ক্যাটাগরিতে কোনো চ্যানেল খুঁজে পাওয়া যায়নি।", show_alert=True)
    
    buttons = []
    row = []
    for ch_id, ch_name, invite_link in channels:
        row.append(InlineKeyboardButton(ch_name, url=invite_link))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton("⬅️ সাব-ক্যাটাগরিতে ফিরে যান", callback_data="show_channels_in_category_Porn")])

    await cb.message.edit_text(
        f"🔞 **'{subcategory}' এর চ্যানেলসমূহ:**\n\nআপনার পছন্দের চ্যানেলে জয়েন করুন:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cb.answer()

@Client.on_callback_query(filters.regex(r"^show_web_subcat_"))
async def show_web_subcat_handler(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)

    subcategory = cb.data.split("_", 3)[-1]
    # সাব-ক্যাটাগরি পপুলারিটি ট্র্যাক করা হচ্ছে
    increment_category_click(f"Web Series||{subcategory}")

    channels = get_channels_by_category("Web Series", subcategory)
    
    if not channels:
        return await cb.answer(f"'{subcategory}' সাব-ক্যাটাগরিতে কোনো চ্যানেল খুঁজে পাওয়া যায়নি।", show_alert=True)
    
    buttons = []
    row = []
    for ch_id, ch_name, invite_link in channels:
        row.append(InlineKeyboardButton(ch_name, url=invite_link))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton("⬅️ সাব-ক্যাটাগরিতে ফিরে যান", callback_data="show_channels_in_category_Web Series")])

    await cb.message.edit_text(
        f"📺 **'{subcategory}' এর চ্যানেলসমূহ:**\n\nআপনার পছন্দের চ্যানেলে জয়েন করুন:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await cb.answer()

async def show_web_series_channels_handler(bot, target):
    from database import get_web_series_subcategories
    subcats = get_web_series_subcategories()
    is_callback = isinstance(target, CallbackQuery)

    if not subcats:
        msg = "📺 কোনো Web Series সাব-ক্যাটাগরি খুঁজে পাওয়া যায়নি।"
        if is_callback: return await target.answer(msg, show_alert=True)
        else: return await target.reply_text(msg)

    buttons = []
    row = []
    for subcat in subcats:
        row.append(InlineKeyboardButton(subcat, callback_data=f"show_web_subcat_{subcat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)

    buttons.append([InlineKeyboardButton("⬅️ মূল মেনুতে ফিরে যান", callback_data="start_menu")])

    text = "📺 **Web Series সাব-ক্যাটাগরি সমূহ (অটো ফিল্টারড):**\n\nআপনার পছন্দের সাব-ক্যাটাগরি নির্বাচন করুন:"
    if is_callback:
        await target.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await target.answer()
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^show_web_series_channels$"))
async def show_web_series_channels_callback(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)
    await show_web_series_channels_handler(bot, cb)

async def show_movie_channels_handler(bot, target):
    # মুভি চ্যানেলের জন্য স্ট্রং কি-ওয়ার্ড ফিল্টারিং (নামের যেকোনো অংশে থাকলেই ক্যাটাগরিতে নিয়ে নিবে)
    keywords = ["movie", "মুভি", "cinema", "সিনেমা", "film", "ফিল্ম", "hollywood", "bollywood", "hindi", "tamil", "bangla", "series", "ওয়েব সিরিজ"]
    channels = search_channels_by_keywords(keywords)
    is_callback = isinstance(target, CallbackQuery)
    
    if not channels:
        msg = "🎬 কোনো মুভি চ্যানেল খুঁজে পাওয়া যায়নি।"
        if is_callback: return await target.answer(msg, show_alert=True)
        else: return await target.reply_text(msg)
    
    buttons = []
    row = []
    for ch_id, ch_name, invite_link in channels:
        row.append(InlineKeyboardButton(ch_name, url=invite_link))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton("⬅️ মূল মেনুতে ফিরে যান", callback_data="start_menu")])

    text = "🎬 **মুভি চ্যানেলসমূহ (অটো ফিল্টারড):**\n\nআপনার পছন্দের চ্যানেলে জয়েন করুন:"
    if is_callback:
        await target.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await target.answer()
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^show_movie_channels$"))
async def show_movie_channels_callback(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)
    await show_movie_channels_handler(bot, cb)

async def show_live_link_channels_handler(bot, target):
    # লাইভ লিংকের জন্য স্ট্রং কি-ওয়ার্ড ফিল্টারিং
    keywords = ["live", "লাইভ", "cricket", "ক্রিকেট", "football", "ফুটবল", "sports", "খেলা", "streaming", "gtv", "t sports"]
    channels = search_channels_by_keywords(keywords)
    is_callback = isinstance(target, CallbackQuery)
    
    if not channels:
        msg = "🔴 কোনো লাইভ চ্যানেল খুঁজে পাওয়া যায়নি।"
        if is_callback: return await target.answer(msg, show_alert=True)
        else: return await target.reply_text(msg)
    
    buttons = []
    row = []
    for ch_id, ch_name, invite_link in channels:
        row.append(InlineKeyboardButton(ch_name, url=invite_link))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton("⬅️ মূল মেনুতে ফিরে যান", callback_data="start_menu")])

    text = "🔴 **লাইভ লিংক চ্যানেলসমূহ (অটো ফিল্টারড):**\n\nআপনার পছন্দের চ্যানেলে জয়েন করুন:"
    if is_callback:
        await target.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await target.answer()
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^show_live_link_channels$"))
async def show_live_link_channels_callback(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)
    await show_live_link_channels_handler(bot, cb)

async def show_world_cup_info_handler(bot, target):
    # বিশ্বকাপের জন্য স্ট্রং কি-ওয়ার্ড ফিল্টারিং
    keywords = ["world cup", "বিশ্বকাপ", "wc 2024", "wc2024", "t20 wc", "fifa", "ফুটবল বিশ্বকাপ"]
    channels = search_channels_by_keywords(keywords)
    is_callback = isinstance(target, CallbackQuery)

    text = "🏆 **বিশ্বকাপ তথ্য ও লাইভ লিংক:**\n\n"
    buttons = []
    if channels:
        text += "নিম্নোক্ত চ্যানেলগুলোতে বিশ্বকাপ সম্পর্কিত তথ্য ও লাইভ লিংক পেতে পারেন:\n"
        row = []
        for ch_id, ch_name, invite_link in channels:
            row.append(InlineKeyboardButton(ch_name, url=invite_link))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
    else:
        text += "বর্তমানে বিশ্বকাপ সম্পর্কিত কোনো চ্যানেল খুঁজে পাওয়া যায়নি। রিয়েল-টাইম তথ্যের জন্য ভবিষ্যতে আপডেট করা হবে।"
    
    buttons.append([InlineKeyboardButton("⬅️ মূল মেনুতে ফিরে যান", callback_data="start_menu")])
    if is_callback:
        await target.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await target.answer()
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^show_world_cup_info$"))
async def show_world_cup_info_callback(bot: Client, cb: CallbackQuery):
    if not is_user_verified(cb.from_user.id):
        await cb.message.delete()
        return await send_daily_verification_message(bot, cb.message)
    await show_world_cup_info_handler(bot, cb)

async def show_buy_bot_contact_handler(bot, target):
    text = (
        "🤖 **বট কেনার জন্য যোগাযোগ করুন:**\n\n"
        "📞 **ফোন:** `01337449557`\n"
        "📧 **ইমেইল:** `sabbirahammad123467@gmail.com`\n\n"
        "আমাদের সাথে যোগাযোগ করার জন্য ধন্যবাদ!"
    )
    is_callback = isinstance(target, CallbackQuery)
    buttons = [[InlineKeyboardButton("⬅️ মূল মেনুতে ফিরে যান", callback_data="start_menu")]]
    if is_callback:
        await target.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await target.answer()
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex(r"^show_buy_bot_contact$"))
async def show_buy_bot_contact_callback(bot: Client, cb: CallbackQuery):
    await show_buy_bot_contact_handler(bot, cb)

@Client.on_callback_query(filters.regex(r"^start_menu$"))
async def return_to_start_menu(bot: Client, cb: CallbackQuery):
    channel_link = os.getenv("CHANNEL_LINK", "https://t.me/YourChannelUsername")
    
    text = (
        f"👋 হ্যালো {cb.from_user.first_name}!\n\n"
        "🚀 আমি একটি শক্তিশালী ফাইল সার্চার বট।\n"
        "নিচের ক্যাটাগরিগুলো থেকে ফাইল খুঁজুন অথবা সরাসরি নাম লিখে মেসেজ পাঠান:"
    )
    
    buttons = []
    new_options_row1 = [
        InlineKeyboardButton("📂 ক্যাটাগরি", callback_data="show_categories"),
        InlineKeyboardButton("🎬 মুভি", callback_data="show_movie_channels"),
        InlineKeyboardButton("🔴 লাইভ লিংক", callback_data="show_live_link_channels"),
    ]
    new_options_row2 = [
        InlineKeyboardButton("🏆 বিশ্বকাপ", callback_data="show_world_cup_info"),
        InlineKeyboardButton("⚽ ফ্যান্টাসি ফুটবল APK", url="https://elitepassit.com"),
        InlineKeyboardButton("🤖 বট কিনুন", callback_data="show_buy_bot_contact"),
    ]
    
    buttons.append(new_options_row1)
    buttons.append(new_options_row2)
    buttons.append([InlineKeyboardButton("📢 আমাদের চ্যানেল", url=channel_link)])
    buttons.append([InlineKeyboardButton("🛠 সাহায্য", callback_data="help_data")])
    
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cb.answer()

@Client.on_inline_query()
async def inline_search_handler(bot: Client, query: InlineQuery):
    """ইনলাইন সার্চ হ্যান্ডেলার যা SEO বাড়াতে সাহায্য করবে"""
    search_query = query.query.strip()
    if not search_query:
        return

    results = search_files(search_query)
    if not results:
        return

    inline_results = []
    bot_info = await bot.get_me()

    for name, size, message_id, channel_id in results[:10]: # টপ ১০টি রেজাল্ট
        size_mb = round(size / (1024 * 1024), 2)
        dest_url = f"https://t.me/{bot_info.username}?start=file_{channel_id}_{message_id}"
        
        inline_results.append(
            InlineQueryResultArticle(
                title=name,
                description=f"Size: {size_mb} MB",
                input_message_content=InputTextMessageContent(
                    f"🎥 **{name}**\n⚖️ সাইজ: {size_mb} MB\n\nনিচের বাটনে ক্লিক করে ফাইলটি নিন:"
                ),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 ডাউনলোড করুন", url=dest_url)]
                ])
            )
        )

    await query.answer(
        results=inline_results,
        cache_time=1
    )

@Client.on_callback_query(filters.regex(r"^no_link$"))
async def no_link_callback(bot: Client, cb: CallbackQuery):
    await cb.answer("এই চ্যানেলটির ইনভাইট লিংক যুক্ত করা হয়নি বা এটি একটি প্রাইভেট চ্যানেল।", show_alert=True)

@Client.on_callback_query(filters.regex(r"^help_data$"))
async def help_callback_handler(bot: Client, cb: CallbackQuery):
    help_text = (
        "🛠 **বট সহায়তা কেন্দ্র**\n\n"
        "১. ফাইল খুঁজতে সরাসরি মুভির নাম লিখে মেসেজ দিন।\n"
        "২. ক্যাটাগরি বাটনে ক্লিক করে নির্দিষ্ট চ্যানেলে জয়েন করতে পারেন।\n"
        "৩. প্রতিদিন প্রথমবার ডাউনলোডের সময় একটি ছোট অ্যাড দেখতে হবে।"
    )
    await cb.message.edit_text(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ফিরে যান", callback_data="start_menu")]]))
