STRINGS = {
    "bn": {
        "welcome": "👋 হ্যালো {name}!\n\n🚀 আমি একটি শক্তিশালী ফাইল সার্চার বট।\nনিচের ক্যাটাগরিগুলো থেকে ফাইল খুঁজুন অথবা সরাসরি নাম লিখে মেসেজ পাঠান:",
        "first_day_free": "🎉 **অভিনন্দন! আপনার প্রথম দিন ফ্রি!**\n\nআজ আপনি কোনো অ্যাড না দেখেই আনলিমিটেড ফাইল এবং মুভি ডাউনলোড করতে পারবেন।",
        "verify_ad": "🔒 **বটটি বর্তমানে লক করা আছে!**\n\nসারাদিন (২৪ ঘণ্টা) ফ্রিতে আনলিমিটেড মুভি ও ফাইল ডাউনলোড করতে মাত্র ১টি ছোট অ্যাড দেখে বটটি আনলক করুন।",
        "unlock_btn": "✅ আনলক করুন (Ad)",
        "cat_btn": "📂 ক্যাটাগরি",
        "movie_btn": "🎬 মুভি",
        "live_btn": "🔴 লাইভ লিংক",
        "porn_btn": "🔞 Porn",
        "wc_btn": "🏆 বিশ্বকাপ",
        "apk_btn": "⚽ ফ্যান্টাসি ফুটবল APK",
        "buy_btn": "🤖 বট কিনুন",
        "series_btn": "📺 Web Series",
        "help_btn": "🛠 সাহায্য",
        "channel_btn": "📢 আমাদের চ্যানেল",
        "searching": "🔍 খুঁজছি... দয়া করে অপেক্ষা করুন।",
        "no_results": "😔 দুঃখিত, বর্তমানে এই ফাইলটি আমাদের কাছে নেই।\n\n🔍 তবে আমি আপনার হয়ে টেলিগ্রামে নতুন সোর্স খুঁজছি। কিছুক্ষণ পর আবার সার্চ করে দেখুন!",
        "copyright_warn": "⏳ **সতর্কতা:** কপিরাইট এড়াতে এই ফাইলটি ১০ মিনিট পর অটোমেটিক ডিলিট করে দেওয়া হবে।",
        "choose_option": "আপনার পছন্দের অপশনটি বেছে নিন:",
        "cat_list_title": "📂 **ক্যাটাগরি সমূহ (পাতা {page}):**\n\nআপনার পছন্দের ক্যাটাগরি নির্বাচন করুন:",
        "back_main_btn": "⬅️ মূল মেনুতে ফিরে যান",
        "back_cat_btn": "⬅️ ক্যাটাগরি লিস্টে ফিরে যান",
        "download_btn": "📥 ডাউনলোড / দেখুন",
        "search_results_title": "🔍 **'{query}' এর জন্য মোট {total}টি ভিডিও/ফাইল পাওয়া গেছে।**\n\nপৃষ্ঠা: {page} / {total_pages}",
        "gplinks_error": "⚠️ লিংক তৈরি করতে সমস্যা হচ্ছে, দয়া করে পরে আবার চেষ্টা করুন অথবা অ্যাডমিনকে জানান।",
        "search_usage": "⚠️ ব্যবহারবিধি: `/search <ফাইলের নাম>`",
        "apk_download_text": "📥 **APK ডাউনলোড করুন:**\n\nলিংক: [এখানে ক্লিক করুন](https://example.com/apk)"
    },
    "en": {
        "welcome": "👋 Hello {name}!\n\n🚀 I am a powerful file searcher bot.\nSearch for files from categories below or send a message with the file name:",
        "first_day_free": "🎉 **Congratulations! Your first day is free!**\n\nToday you can download unlimited files and movies without watching any ads.",
        "verify_ad": "🔒 **The bot is currently locked!**\n\nTo download unlimited movies and files for free all day (24h), unlock the bot by watching just 1 small ad.",
        "unlock_btn": "✅ Unlock (Ad)",
        "cat_btn": "📂 Categories",
        "movie_btn": "🎬 Movies",
        "live_btn": "🔴 Live Links",
        "porn_btn": "🔞 Porn",
        "wc_btn": "🏆 World Cup",
        "apk_btn": "⚽ Fantasy Football APK",
        "buy_btn": "🤖 Buy Bot",
        "series_btn": "📺 Web Series",
        "help_btn": "🛠 Help",
        "channel_btn": "📢 Our Channel",
        "searching": "🔍 Searching... please wait.",
        "no_results": "😔 Sorry, we don't have this file at the moment.\n\n🔍 However, I am searching for new sources for you on Telegram. Please search again after a while!",
        "copyright_warn": "⏳ **Warning:** To avoid copyright issues, this file will be automatically deleted after 10 minutes.",
        "choose_option": "Choose your preferred option:",
        "cat_list_title": "📂 **Categories (Page {page}):**\n\nSelect your preferred category:",
        "back_main_btn": "⬅️ Return to Main Menu",
        "back_cat_btn": "⬅️ Back to Category List",
        "download_btn": "📥 Download / View",
        "search_results_title": "🔍 **Found {total} files for '{query}'.**\n\nPage: {page} / {total_pages}",
        "gplinks_error": "⚠️ Error generating link, please try again later or contact admin.",
        "search_usage": "⚠️ Usage: `/search <file name>`",
        "apk_download_text": "📥 **Download APK:**\n\nLink: [Click Here](https://example.com/apk)"
    }
}

def get_string(key, lang_code, **kwargs):
    # যদি language_code 'bn' হয় তবে বাংলা, নাহলে ডিফল্ট ইংলিশ
    lang = "bn" if lang_code and lang_code.startswith("bn") else "en"
    text = STRINGS.get(lang).get(key, STRINGS["en"][key])
    if kwargs:
        return text.format(**kwargs)
    return text