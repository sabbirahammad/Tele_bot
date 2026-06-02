import os
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# GPLinks API Token
GPLINKS_API = os.getenv("GPLINKS_API", "c6c60266f958ad52b6999f348e63d1f2bc6fc629")

# Bot Client: ইউজারদের সাথে কথা বলার জন্য
bot = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

# User Client: আপনার জয়েন করা চ্যানেলের ফাইল ইনডেক্স করার জন্য
user = Client(
    os.getenv("SESSION_STRING", "user_session"), # সেশন স্ট্রিং থাকলে সেটি ব্যবহার করবে
    api_id=API_ID,
    api_hash=API_HASH
)