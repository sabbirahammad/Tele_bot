import os
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery # নতুন ইম্পোর্ট
from loader import user, bot
from database import count_channel_files, count_users, get_all_users, add_channel, del_channel, count_active_channels, get_pending_withdraw_requests, update_withdraw_request_status, get_withdraw_request_details, credit_user_balance

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
    total_users = len(users)

    # Confirmation step
    confirm_text = f"📢 আপনি কি নিশ্চিত যে আপনি এই মেসেজটি **{total_users}** জন ইউজারকে ব্রডকাস্ট করতে চান?\n\n" \
                   "এই অ্যাকশনটি বাতিল করা যাবে না।"
    confirm_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ নিশ্চিত করুন", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_broadcast")]
    ])
    await message.reply_text(confirm_text, reply_markup=confirm_buttons)

# New callback handler for broadcast confirmation
@Client.on_callback_query(filters.regex("confirm_broadcast") & filters.user(ADMINS))
async def confirm_broadcast_callback(bot, cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=None) # Remove buttons
    await cb.message.edit_text("📢 ব্রডকাস্টিং শুরু হচ্ছে...")

    # Get the original message to broadcast (the one the admin replied to)
    original_message = cb.message.reply_to_message
    if not original_message:
        return await cb.message.edit_text("❌ ব্রডকাস্ট করার জন্য কোনো মেসেজ খুঁজে পাওয়া যায়নি।")

    users = get_all_users()
    total_users = len(users)
    status_message = await cb.message.reply_text(f"📢 ব্রডকাস্টিং শুরু হয়েছে... {total_users} জন ইউজারকে পাঠানো হচ্ছে।")
    
    success = 0
    failed = 0
    
    for i, user_id in enumerate(users):
        try:
            await original_message.copy(user_id)
            success += 1
        except FloodWait as e:
            logging.warning(f"FloodWait for user {user_id}: {e.value} seconds. Sleeping...")
            await asyncio.sleep(e.value)
            try:
                await original_message.copy(user_id)
                success += 1
            except Exception as retry_e:
                logging.error(f"Failed to send to user {user_id} after FloodWait: {retry_e}")
                failed += 1
        except Exception as e:
            logging.error(f"Failed to send to user {user_id}: {e}")
            failed += 1
            
        # Update progress more frequently, e.g., every 10 users or 5%
        if (i + 1) % 10 == 0 or (i + 1) == total_users:
            try:
                progress_percent = ((success + failed) / total_users) * 100
                await status_message.edit_text(
                    f"⏳ ব্রডকাস্টিং প্রগ্রেস: {success + failed}/{total_users} ({progress_percent:.2f}%)\n"
                    f"✅ সফল: {success}\n❌ ব্যর্থ: {failed}"
                )
            except Exception as edit_e:
                logging.error(f"Failed to edit broadcast status message: {edit_e}")
        
        await asyncio.sleep(0.1) # Small delay to prevent FloodWait

    final_text = (
        f"✅ ব্রডকাস্ট সম্পন্ন!\n\n"
        f"🚀 সফল: {success}\n"
        f"❌ ব্যর্থ: {failed}\n\n"
        f"মোট ইউজার: {total_users}"
    )
    await status_message.edit_text(final_text)

    # Notify admin about completion
    for admin_id in ADMINS:
        if admin_id != cb.from_user.id: # Don't send to the admin who initiated if it's the same
            try:
                await bot.send_message(admin_id, f"📢 ব্রডকাস্ট সম্পন্ন হয়েছে!\n{final_text}")
            except Exception as admin_notify_e:
                logging.error(f"Failed to notify admin {admin_id} about broadcast completion: {admin_notify_e}")

@Client.on_callback_query(filters.regex("cancel_broadcast") & filters.user(ADMINS))
async def cancel_broadcast_callback(bot, cb: CallbackQuery):
    await cb.message.edit_text("❌ ব্রডকাস্ট বাতিল করা হয়েছে।")
    await cb.answer("ব্রডকাস্ট বাতিল করা হয়েছে।")

@Client.on_message(filters.command("auto") & filters.user(ADMINS))
async def auto_crawl_handler(bot, message):
    if len(message.command) < 2:
        return await message.reply_text("ব্যবহার: `/auto [keyword]`\nযেমন: `/auto pushpa`")
    
    query = message.text.split(None, 1)[1].strip()
    
    await message.reply_text(f"✅ **'{query}'** কিওয়ার্ডটি Deep Crawling Queue-তে যুক্ত করা হয়েছে। বট ব্যাকগ্রাউন্ডে চ্যানেল খুঁজে জয়েন এবং ইনডেক্স করা শুরু করবে।")
    
    from plugins.search import trigger_deep_crawl
    await trigger_deep_crawl(query)

@Client.on_message(filters.command("withdraw_requests") & filters.user(ADMINS))
async def show_withdraw_requests(bot, message):
    requests = get_pending_withdraw_requests()
    
    if not requests:
        return await message.reply_text("✅ বর্তমানে কোনো পেন্ডিং উইথড্র রিকোয়েস্ট নেই।")
    
    for req in requests:
        req_id, user_id, amount, currency, wallet, date = req
        
        # ইউজারের তথ্য আনার চেষ্টা
        try:
            user_info = await bot.get_users(user_id)
            user_mention = user_info.mention
        except Exception:
            user_mention = f"User ID: `{user_id}`"
            
        text = (
            f"💰 **উইথড্র রিকোয়েস্ট #{req_id}**\n\n"
            f"👤 ইউজার: {user_mention}\n"
            f"💵 পরিমাণ: {amount} {currency}\n"
            f"🏦 ওয়ালেট: `{wallet}`\n"
            f"📅 তারিখ: {date}\n"
            f"📊 স্ট্যাটাস: পেন্ডিং"
        )
        
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{req_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{req_id}")
            ]
        ])
        await message.reply_text(text, reply_markup=buttons)

@Client.on_callback_query(filters.regex("^approve_withdraw_") & filters.user(ADMINS))
async def approve_withdraw_callback(bot, cb: CallbackQuery):
    request_id = int(cb.data.split("_")[-1])
    
    req_details = get_withdraw_request_details(request_id)
    if not req_details:
        return await cb.answer("❌ রিকোয়েস্ট খুঁজে পাওয়া যায়নি।", show_alert=True)
    
    user_id, amount, currency, wallet, status = req_details
    
    if status != 'pending':
        return await cb.answer(f"❌ এই রিকোয়েস্টটি ইতিমধ্যেই {status} করা হয়েছে।", show_alert=True)
        
    update_withdraw_request_status(request_id, 'approved')
    
    await cb.message.edit_text(f"✅ উইথড্র রিকোয়েস্ট #{request_id} **Approve** করা হয়েছে।")
    await cb.answer("রিকোয়েস্ট Approve করা হয়েছে।")
    
    # ইউজারকে জানানো
    try:
        await bot.send_message(user_id, f"✅ আপনার **{amount} {currency}** উইথড্র রিকোয়েস্ট Approve করা হয়েছে।\nআপনার ওয়ালেটে টাকা পাঠানো হবে শীঘ্রই।")
    except Exception: pass

@Client.on_callback_query(filters.regex("^reject_withdraw_") & filters.user(ADMINS))
async def reject_withdraw_callback(bot, cb: CallbackQuery):
    request_id = int(cb.data.split("_")[-1])
    
    req_details = get_withdraw_request_details(request_id)
    if not req_details:
        return await cb.answer("❌ রিকোয়েস্ট খুঁজে পাওয়া যায়নি।", show_alert=True)
    
    user_id, amount, currency, wallet, status = req_details
    
    if status != 'pending':
        return await cb.answer(f"❌ এই রিকোয়েস্টটি ইতিমধ্যেই {status} করা হয়েছে।", show_alert=True)
        
    update_withdraw_request_status(request_id, 'rejected')
    credit_user_balance(user_id, amount, currency) # ব্যালেন্স ফেরত দেওয়া
    
    await cb.message.edit_text(f"❌ উইথড্র রিকোয়েস্ট #{request_id} **Reject** করা হয়েছে এবং **{amount} {currency}** ইউজারের ব্যালেন্সে ফেরত দেওয়া হয়েছে।")
    await cb.answer("রিকোয়েস্ট Reject করা হয়েছে।")
    
    # ইউজারকে জানানো
    try:
        await bot.send_message(user_id, f"❌ দুঃখিত, আপনার **{amount} {currency}** উইথড্র রিকোয়েস্ট Reject করা হয়েছে।\nআপনার ব্যালেন্স ফেরত দেওয়া হয়েছে।")
    except Exception: pass