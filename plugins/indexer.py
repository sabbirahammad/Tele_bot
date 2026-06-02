import asyncio
import re
import os
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from database import add_channel_file, get_all_channels
from loader import user, bot # Loader থেকে ইম্পোর্ট করা হলো

logger = logging.getLogger(__name__)

def get_media_name(msg, media):
    """মিডিয়া থেকে নাম বের করার চেষ্টা করে, না পেলে ক্যাপশন থেকে নাম তৈরি করে"""
    file_name = getattr(media, "file_name", None)
    
    if not file_name:
        # যদি ফাইলের নাম না থাকে, তবে ক্যাপশন থেকে নাম নেওয়ার চেষ্টা করবে
        caption = msg.caption or msg.text
        if caption:
            # ক্যাপশনের প্রথম লাইন বা প্রথম কিছু শব্দ দিয়ে নাম তৈরি করা
            # স্পেশাল ক্যারেক্টার ক্লিনআপ করা হলো সার্চ সহজ করার জন্য
            clean_caption = caption.split("\n")[0]
            # টেলিগ্রাম ইউজারনেম এবং অপ্রয়োজনীয় ডট/আন্ডারস্কোর রিমুভ করা
            clean_caption = re.sub(r'@[A-Za-z0-9_]+', '', clean_caption)
            file_name = clean_caption[:100].strip().replace("_", " ").replace(".", " ")
        else:
            file_name = f"Unnamed_File_{msg.id}"
            
    return file_name

# আপনার আইডি যেসব চ্যানেলে আছে, সেখানে নতুন ফাইল আসা মাত্র এটি কাজ করবে
@user.on_message(filters.channel & (filters.document | filters.video | filters.audio))
async def auto_index_handler(client, message):
    """
    চ্যানেলে নতুন কোনো ফাইল পোস্ট হওয়া মাত্র তা অটোমেটিক ডাটাবেজে সেভ করবে।
    """
    media = message.document or message.video or message.audio

    if not media:
        return

    file_id = media.file_id
    file_name = get_media_name(message, media)
    file_size = getattr(media, "file_size", 0)
    
    # ডাটাবেজে সেভ করা (database.py এর লজিক ডুপ্লিকেট হ্যান্ডেল করবে)
    add_channel_file(file_id, file_name, file_size, message.id, message.chat.id)

async def index_chat_history(chat_id, progress_msg=None, is_auto=False, query_ref=None):
    """একটি নির্দিষ্ট চ্যানেলের সব পুরনো ফাইল ইনডেক্স করার ফাংশন"""
    total_count = 0
    try:
        async for msg in user.get_chat_history(chat_id):
            media = msg.document or msg.video or msg.audio
            if media:
                file_id = media.file_id
                file_name = get_media_name(msg, media)
                file_size = getattr(media, "file_size", 0)
                
                add_channel_file(file_id, file_name, file_size, msg.id, chat_id)
                total_count += 1
                
                if progress_msg and total_count % 200 == 0:
                    try:
                        await progress_msg.edit_text(f"⏳ ইনডেক্সিং চলছে...\n\nএখন পর্যন্ত **{total_count}**টি ফাইল পাওয়া গেছে।")
                    except Exception: pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Error auto-indexing {chat_id}: {e}")
        
    # যদি এটি অটোমেটিক টাস্ক হয়, তবে শেষ হলে অ্যাডমিনকে জানানো
    if is_auto:
        from plugins.admin import ADMINS
        from database import get_channel_name_by_id
        ch_name = get_channel_name_by_id(chat_id) or "Unknown"
        for admin_id in ADMINS:
            try:
                await bot.send_message(
                    admin_id, 
                    f"✅ **অটো-ইনডেক্সিং সম্পন্ন:**\n\n"
                    f"🔍 রেফারেন্স সার্চ: `{query_ref or 'N/A'}`\n"
                    f"📺 চ্যানেল: {ch_name}\n📁 মোট ফাইল যুক্ত হয়েছে: {total_count}"
                )
            except Exception: pass
            
    return total_count

@Client.on_message(filters.command("index") & filters.private)
async def manual_index_command(bot, message):
    """
    নির্দিষ্ট চ্যানেল বা কনফিগার করা সব চ্যানেলের পুরনো ফাইল ইনডেক্স করার কমান্ড।
    """
    db_channels = [ch[0] for ch in get_all_channels()]
    env_channels = [c.strip() for c in os.getenv("CHANNELS", "").split(",") if c.strip()]
    target_chats = [message.command[1]] if len(message.command) > 1 else (db_channels + env_channels)
    
    if not target_chats:
        return await message.reply_text("❌ কোনো চ্যানেল নির্দিষ্ট করা হয়নি। প্রথমে `/sync` কমান্ড দিন।")

    progress = await message.reply_text(f"🔍 ইনডেক্সিং শুরু হচ্ছে... মোট {len(target_chats)}টি চ্যানেল চেক করা হবে।")
    total_count = 0
    failed_chats = 0

    for chat in target_chats:
        try:
            count = await index_chat_history(chat, progress)
            total_count += count
            logger.info(f"Indexed {count} files from channel {chat}")
        except Exception:
            failed_chats += 1

    final_text = f"✅ ইনডেক্সিং সম্পন্ন!\n\nমোট **{total_count}**টি ফাইল সংরক্ষিত হয়েছে।"
    if failed_chats > 0:
        final_text += f"\n⚠️ {failed_chats}টি চ্যানেলে অ্যাক্সেস পেতে সমস্যা হয়েছে।"
        
    await progress.edit_text(final_text)