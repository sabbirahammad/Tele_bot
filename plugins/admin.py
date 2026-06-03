import os
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from loader import user # User ক্লায়েন্ট ইম্পোর্ট
from database import count_channel_files, count_users, get_all_users, add_channel, del_channel, count_active_channels

ADMINS = [int(id) for id in os.getenv("ADMIN_ID", "0").split()]

@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_handler(bot, message):
    total_users = count_users()
    total_files = count_channel_files()
    active_channels = count_active_channels()
    
    await message.reply_text(
        f"📊 **বট স্ট্যাটাস:**\n\n"
        f"👥 মোট ইউজার: {total_users}\n"
        f"📁 মোট ফাইল ইনডেক্সড: {total_files}\n"
        f"📺 সক্রিয় চ্যানেল: {active_channels}"
    )

@Client.on_message(filters.command("add_channel") & filters.user(ADMINS))
async def add_channel_handler(bot, message):
    if len(message.command) < 2:
        return await message.reply_text("ব্যবহার: `/add_channel [Channel ID]`\nID পেতে কোনো মেসেজ ফরোয়ার্ড করুন @userinfobot এ।")
    try:
        chat_id = int(message.command[1])
        chat_info = await user.get_chat(chat_id) # User দিয়ে তথ্য ফেচ করা
        channel_name = chat_info.title or "Unknown Channel"
        
        # ইউজারনেম বা ইনভাইট লিংক খোঁজা
        link = f"https://t.me/{chat_info.username}" if chat_info.username else chat_info.invite_link
        
        # যদি লিংক না পাওয়া যায় তবে তৈরি করার চেষ্টা করা (যদি পারমিশন থাকে)
        if not link:
            try:
                link = await user.export_chat_invite_link(chat_id)
            except:
                link = None
                
        add_channel(chat_id, channel_name, link) 
        await message.reply_text(f"✅ চ্যানেল `{chat_id}` ইনডেক্সিং লিস্টে যুক্ত করা হয়েছে।")
    except ValueError:
        await message.reply_text("❌ সঠিক চ্যানেল আইডি দিন।")

@Client.on_message(filters.command("sync") & filters.user(ADMINS))
async def sync_channels_handler(bot, message):
    """
    আপনার আইডিতে থাকা সব চ্যানেল অটোমেটিক ডাটাবেজে সিঙ্ক করার কমান্ড।
    """
    if not user.is_connected:
        return await message.reply_text(
            "❌ **User Client (STRING_SESSION) চালু নেই!**\nদয়া করে রেলওয়ে ভেরিয়েবল চেক করুন এবং বট রিস্টার্ট দিন।"
        )
        
    msg = await message.reply_text("🔄 আপনার জয়েন করা চ্যানেলগুলো সিঙ্ক করা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন।")
    count = 0
    try:
        async for dialog in user.get_dialogs():
            # শুধুমাত্র চ্যানেল এবং সুপারগ্রুপগুলো নেওয়া হচ্ছে
            if dialog.chat.type in [enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP]:
                chat = dialog.chat
                link = f"https://t.me/{chat.username}" if chat.username else chat.invite_link
                
                if not link:
                    try:
                        link = await user.export_chat_invite_link(chat.id)
                    except:
                        link = None
                        
                add_channel(dialog.chat.id, dialog.chat.title, link)
                count += 1
        
        await msg.edit_text(f"✅ সিঙ্ক সম্পন্ন! মোট {count}টি চ্যানেল আপনার `/start` মেনুর ক্যাটাগরিতে যুক্ত করা হয়েছে।")
    except Exception as e:
        await msg.edit_text(f"❌ সিঙ্ক করার সময় এরর হয়েছে: {str(e)}")

@Client.on_message(filters.command("del_channel") & filters.user(ADMINS))
async def del_channel_handler(bot, message):
    if len(message.command) < 2:
        return await message.reply_text("ব্যবহার: `/del_channel [Channel ID]`")
    try:
        chat_id = int(message.command[1])
        del_channel(chat_id)
        await message.reply_text(f"🗑️ চ্যানেল `{chat_id}` লিস্ট থেকে বাদ দেওয়া হয়েছে।")
    except ValueError:
        await message.reply_text("❌ সঠিক চ্যানেল আইডি দিন।")

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_handler(bot, message):
    if not message.reply_to_message:
        return await message.reply_text("ব্যবহার: কোনো মেসেজ রিপ্লাই দিয়ে `/broadcast` লিখুন।")
    
    users = get_all_users()
    status = await message.reply_text(f"📢 ব্রডকাস্টিং শুরু হয়েছে... {len(users)} জন ইউজারকে পাঠানো হচ্ছে।")
    
    success = 0
    failed = 0
    
    for user_id in users:
        try:
            await message.reply_to_message.copy(user_id)
            success += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await message.reply_to_message.copy(user_id)
            success += 1
        except Exception:
            failed += 1
            
        # প্রতি ২০টি মেসেজ পর পর প্রগ্রেস আপডেট (অপশনাল)
        if (success + failed) % 20 == 0:
            try:
                await status.edit_text(f"⏳ প্রগ্রেস: {success + failed}/{len(users)}")
            except:
                pass

    await status.edit_text(
        f"✅ ব্রডকাস্ট সম্পন্ন!\n\n🚀 সফল: {success}\n❌ ব্যর্থ: {failed}"
    )