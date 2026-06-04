import asyncio
# পাইথন ৩.১২+ এবং বিশেষ করে ৩.১৪ এর জন্য Pyrogram compatibility fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import os
import logging
from pyrogram.types import BotCommand
from database import init_db
from loader import bot, user

# লগিং সেটআপ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)

async def start_services():
    init_db()
    await bot.start()
    
    # বটের মেনু বাটন সেট করা যাতে ইউজার শুরুতেই ফিচারগুলো দেখতে পায়
    await bot.set_bot_commands([
        BotCommand("start", "🚀 বট শুরু করুন"),
        BotCommand("catagory", "📂 সব ক্যাটাগরি"),
        BotCommand("porn", "🔞 Porn ক্যাটাগরি"), # Added for consistency with search.py
        BotCommand("movie", "🎬 মুভি চ্যানেল"),
        BotCommand("invite", "🤝 ইনভাইট ও ইনকাম"),
        BotCommand("livelink", "🔴 লাইভ লিংক"),
        BotCommand("series", "📺 Web Series"), # Added for consistency with search.py
        BotCommand("worldcup", "🏆 বিশ্বকাপ আপডেট"),
        BotCommand("apk", "⚽ ফ্যান্টাসি ফুটবল APK"),
        BotCommand("buybot", "🤖 বট কিনুন")
    ])
    
    logging.info("--- Bot Client Started ---")
    # সেশন স্ট্রিং অন্তত ৩০০ ক্যারেক্টার হওয়া উচিত (Pyrogram v2 এর জন্য)
    if user.session_string and len(user.session_string) > 300: 
        try:
            await user.start()
            logging.info("--- User Client (Your ID) Started ---")
        except Exception as e:
            logging.error(f"❌ User Client failed to start: {str(e)}")
            logging.warning("Please check if your STRING_SESSION is valid and complete.")
    else:
        logging.warning("⚠️ STRING_SESSION missing! The bot will only work with existing database records.")
        logging.warning("Global search and auto-indexing are DISABLED.")

    await asyncio.Event().wait()

async def stop_services():
    await bot.stop()
    if user.is_connected:
        await user.stop()
    logging.info("--- All Services Stopped ---")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        loop.run_until_complete(stop_services())
