import logging
import asyncio
import base64
import sqlite3
from pyrogram import Client, filters
import os # os মডিউল ইম্পোর্ট করা হয়েছে
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from database import add_user, get_all_channels, verify_user, get_user_status, DB_PATH # Added get_user_status, DB_PATH
from translation import get_string

logging.info("start.py loaded successfully!")

async def auto_delete_message(message, delay=600):
    """নির্ধারিত সময় পর মেসেজ ডিলিট করার ফাংশন (ডিফল্ট ১০ মিনিট)"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(bot, message):    # অ্যাড দেখে ফিরে আসা ইউজারদের হ্যান্ডেল করা
    if len(message.command) > 1:
        param = message.command[1]
        
        if param == "verify_daily":
            verify_user(message.from_user.id)
            # The actual message will be determined below based on is_first_day
            # Continue to show main menu below
            
        elif param == "show_cats":
            # সার্কেল ইমপোর্ট এড়াতে ফাংশনের ভেতরে ইমপোর্ট করা হয়েছে
            verify_user(message.from_user.id)
            from plugins.search import show_categories_handler
            await message.reply_text("✅ ভেরিফিকেশন সফল হয়েছে!\n\n📂 **ক্যাটাগরি সমূহ নিচে দেওয়া হলো:**")
            return await show_categories_handler(bot, message)
            
        elif param == "show_porn_cats":
            verify_user(message.from_user.id)
            from plugins.search import show_porn_categories_from_message
            await message.reply_text("✅ ভেরিফিকেশন সফল হয়েছে!\n\n🔞 **Porn সাব-ক্যাটাগরি সমূহ নিচে দেওয়া হলো:**")
            return await show_porn_categories_from_message(bot, message)
            
        elif param == "show_web_series":
            verify_user(message.from_user.id)
            from plugins.search import show_web_series_channels_handler
            await message.reply_text("✅ ভেরিফিকেশন সফল হয়েছে!\n\n📺 **ওয়েব সিরিজ চ্যানেলসমূহ নিচে দেওয়া হলো:**")
            return await show_web_series_channels_handler(bot, message)
            
        elif param.startswith("q_"):
            verify_user(message.from_user.id)
            from plugins.search import search
            try:
                # Base64 ডিকোড করে অরিজিনাল কুয়েরি বের করা
                encoded_query = param[2:]
                padding = '=' * (4 - len(encoded_query) % 4)
                query = base64.urlsafe_b64decode(encoded_query + padding).decode('utf-8')
                
                # মেসেজ অবজেক্টের টেক্সট পরিবর্তন করে সার্চ ফাংশন কল করা
                message.text = query
                await message.reply_text(f"✅ ভেরিফিকেশন সফল হয়েছে!\n🔍 **'{query}'** এর রেজাল্ট খোঁজা হচ্ছে...")
                return await search(bot, message)
            except Exception:
                await message.reply_text("✅ ভেরিফিকেশন সফল হয়েছে!")

        elif param.startswith("file_"):
            # ফরম্যাট: file_channelid_messageid (channelid could be negative)
            sent_msg = None
            try:
                # Remove the "file_" prefix first to handle negative signs
                data = param[5:]
                # rsplit to handle negative numbers better, assuming message_id is positive
                parts = data.rsplit("_", 1)
                if len(parts) == 2:
                    ch_id = int(parts[0])
                    msg_id = int(parts[1])
                    
                    try:
                        # 1. First try to copy directly with the bot
                        sent_msg = await bot.copy_message(
                            chat_id=message.chat.id,
                            from_chat_id=ch_id,
                            message_id=msg_id
                        )
                    except Exception as bot_err:
                        logging.warning(f"Bot could not copy message directly: {bot_err}. Trying user fallback...")
                        try:
                            # 2. Fallback: User client copies the message to the Bot's DM
                            from loader import user
                            bot_me = await bot.get_me()
                            user_me = await user.get_me()

                            # Peer id invalid এরর এড়াতে চ্যাটটি রেজলভ করে নেওয়া হচ্ছে
                            try:
                                await user.get_chat(ch_id)
                            except Exception:
                                pass

                            # User forwards the message and we get the message object directly from the response
                            fwd_msg = await user.forward_messages(
                                chat_id=bot_me.username,
                                from_chat_id=ch_id,
                                message_ids=msg_id
                            )
                            
                            fwd_msg_id = fwd_msg.id if not isinstance(fwd_msg, list) else fwd_msg[0].id

                            if fwd_msg_id:
                                # Bot copies from its own DM to Target User
                                sent_msg = await bot.copy_message(
                                    chat_id=message.chat.id,
                                    from_chat_id=user_me.id,
                                    message_id=fwd_msg_id
                                )

                                # Cleanup the bot's DM
                                await bot.delete_messages(chat_id=user_me.id, message_ids=fwd_msg_id)
                        except Exception as user_err:
                            logging.error(f"User fallback also failed: {user_err}")                            
                    if sent_msg:
                        try:
                            # ইউজারকে সতর্কতা মেসেজ পাঠানো
                            warning_msg = await message.reply_text("⏳ **সতর্কতা:** কপিরাইট এড়াতে এই ফাইলটি ১০ মিনিট পর অটোমেটিক ডিলিট করে দেওয়া হবে। দয়া করে এর মধ্যেই ফাইলটি সেভ বা অন্য কোথাও ফরোয়ার্ড করে রাখুন।")
                            
                            # অটো-ডিলিট টাস্ক শুরু করা
                            asyncio.create_task(auto_delete_message(sent_msg, 600))
                            asyncio.create_task(auto_delete_message(warning_msg, 600))
                        except Exception:
                            logging.warning("Failed to send warning message or set auto-delete.")
                        return 
                    else:
                        await message.reply_text("❌ ফাইলটি পাওয়া যায়নি। চ্যানেলটি হয়তো প্রাইভেট বা ডিলিট হয়ে গেছে।")
                        return
            except Exception as e:
                logging.error(f"Error handling file link: {e}")
            return
            
    user_id = message.from_user.id
    
    # Check if user exists to determine if it's a new user's first /start
    is_existing_user = False
    with sqlite3.connect(DB_PATH) as conn: # Directly using sqlite3.connect here
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            is_existing_user = True

    username = message.from_user.username or "No Username"    
    add_user(user_id, username) # Ensure user is in DB, sets registration_date if new

    # Now get the user status after ensuring they are in the database
    is_verified_today, is_first_day = get_user_status(user_id)
    lang = message.from_user.language_code

    # If a new user just typed /start and it's their first day, give them a special welcome.
    if not is_existing_user and is_first_day:
        verify_user(user_id) # Mark as verified for the free day
        text = get_string("welcome", lang, name=message.from_user.first_name) + "\n\n" + get_string("first_day_free", lang)
    else:
        text = get_string("welcome", lang, name=message.from_user.first_name)
    
    # Reply Keyboard for main menu
    main_menu = ReplyKeyboardMarkup(
        [
            [get_string("cat_btn", lang), get_string("movie_btn", lang), get_string("live_btn", lang), get_string("porn_btn", lang)],
            [get_string("wc_btn", lang), get_string("apk_btn", lang), get_string("buy_btn", lang), get_string("series_btn", lang)]
        ],
        resize_keyboard=True, # বাটনগুলো সাইজ মতো ছোট দেখাবে
        is_persistent=True    # বাটনগুলো সবসময় ইনপুট ফিল্ডের নিচে থাকবে
    )
    # Inline keyboard for the initial message (consistent with return_to_start_menu)
    inline_buttons = [
        [
            InlineKeyboardButton(get_string("cat_btn", lang), callback_data="show_categories"),
            InlineKeyboardButton(get_string("movie_btn", lang), callback_data="show_movie_channels"),
            InlineKeyboardButton(get_string("live_btn", lang), callback_data="show_live_link_channels"),
            InlineKeyboardButton(get_string("porn_btn", lang), callback_data="show_channels_in_category_Porn"),
        ],
        [
            InlineKeyboardButton(get_string("wc_btn", lang), callback_data="show_world_cup_info"),
            InlineKeyboardButton(get_string("apk_btn", lang), url="https://elitepassit.com"),
            InlineKeyboardButton(get_string("buy_btn", lang), callback_data="show_buy_bot_contact"),
            InlineKeyboardButton(get_string("series_btn", lang), callback_data="show_web_series_channels"),
        ],
        [InlineKeyboardButton(get_string("channel_btn", lang), url=os.getenv("CHANNEL_LINK", "https://t.me/YourChannelUsername"))],
        [InlineKeyboardButton(get_string("help_btn", lang), callback_data="help_data")]
    ]

    await message.reply_text(text, reply_markup=main_menu)
    prompt_text = "আপনার পছন্দের অপশনটি বেছে নিন:" if lang and lang.startswith("bn") else "Choose your preferred option:"
    await message.reply_text(prompt_text, reply_markup=InlineKeyboardMarkup(inline_buttons))