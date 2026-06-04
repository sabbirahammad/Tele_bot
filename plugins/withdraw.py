import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply, CallbackQuery
from database import get_user_balances, create_withdraw_request, update_user_state, get_user_state, get_user_withdraw_history, count_referrals, add_user, add_referral, user_exists, get_today_date_str
from translation import get_string
import os
import re

ADMINS = [int(id) for id in os.getenv("ADMIN_ID", "0").split()]

@Client.on_callback_query(filters.regex("^withdraw_info$"))
async def withdraw_info_handler(bot, cb):
    lang = cb.from_user.language_code
    balances = get_user_balances(cb.from_user.id)
    coin = balances[0]
    fly = balances[1]
    
    text = (
        f"{get_string('withdraw_dashboard_title', lang)}\n\n"
        f"{get_string('withdraw_balance_info', lang, coin=coin, coin_bdt=coin*3, fly=fly, fly_bdt=fly*2)}\n\n"
        f"{get_string('withdraw_policy', lang)}\n"
        f"{get_string('choose_option', lang)}"
    )
    
    buttons = [
        [
            InlineKeyboardButton(get_string("withdraw_btn_coin", lang), callback_data="req_withdraw_Coin"),
            InlineKeyboardButton(get_string("withdraw_btn_fly", lang), callback_data="req_withdraw_Fly")
        ],
        [InlineKeyboardButton(get_string("history_btn", lang), callback_data="withdraw_history")],
        [InlineKeyboardButton(get_string("back_btn", lang), callback_data="start_menu")]
    ]
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^invite_earn_menu$"))
async def show_invite_earn_menu(bot, target):
    lang = target.from_user.language_code
    text = get_string("invite_earn_menu_title", lang)
    buttons = [
        [
            InlineKeyboardButton(get_string("referral_stats_title", lang), callback_data="referral_stats"),
            InlineKeyboardButton(get_string("withdraw_dashboard_title", lang), callback_data="withdraw_info")
        ],
        [InlineKeyboardButton(get_string("back_main_btn", lang), callback_data="start_menu")]
    ]
    is_callback = isinstance(target, CallbackQuery)
    reply_func = target.message.edit_text if is_callback else target.reply_text
    await reply_func(text, reply_markup=InlineKeyboardMarkup(buttons))
    if is_callback: await target.answer()

@Client.on_callback_query(filters.regex("^referral_stats$"))
async def referral_stats_handler(bot, cb):
    user_id = cb.from_user.id
    lang = cb.from_user.language_code
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    total_referrals = count_referrals(user_id)
    
    text = (
        "👥 **রেফারেল সিস্টেম**\n\n"
        f"🔗 **আপনার রেফারেল লিংক:**\n`{referral_link}`\n\n"
        f"📊 **মোট রেফারেল:** {total_referrals} জন\n\n"
        f"{get_string('referral_policy', lang)}\n\n"
        f"{'লিংকটি বন্ধুদের সাথে শেয়ার করুন!' if lang.startswith('bn') else 'Share the link with friends!'}"
    )
    
    buttons = [
        [InlineKeyboardButton("🚀 বন্ধুদের পাঠান", url=f"https://t.me/share/url?url={referral_link}")],
        [InlineKeyboardButton(get_string("back_btn", lang), callback_data="start_menu")]
    ]
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cb.answer()

@Client.on_message(filters.command("withdraw_history") & filters.private)
@Client.on_callback_query(filters.regex("^withdraw_history$"))
@Client.on_callback_query(filters.regex("^withdraw_history_page_(\\d+)$"))
async def withdraw_history_handler(bot, message_or_cb: CallbackQuery, page=0):
    user_id = message_or_cb.from_user.id
    lang = message_or_cb.from_user.language_code
    
    if isinstance(message_or_cb, CallbackQuery) and message_or_cb.data.startswith("withdraw_history_page_"):
        page = int(message_or_cb.data.split("_")[-1])
    elif isinstance(message_or_cb, CallbackQuery) and message_or_cb.data == "withdraw_history":
        page = 0 # যখন প্রথমবার "উইথড্র হিস্ট্রি" বাটনে ক্লিক করা হবে
    
    page_size = 5
    offset = page * page_size
    
    history, total_items = get_user_withdraw_history(user_id, offset, page_size)
    
    if not history:
        text = get_string("no_withdraw_history", lang)
    else:
        text = get_string("withdraw_history_title", lang, total=total_items) + "\n\n"
        for i, (amount, currency, status, date) in enumerate(history, 1):
            # স্ট্যাটাস অনুযায়ী ইমোজি সেট করা
            status_icon = "⏳" if status == "pending" else "✅" if status == "approved" else "❌"
            text += f"▪️ {amount} {currency} - {status_icon} {status.capitalize()}\n   📅 তারিখ: {date}\n\n"

    buttons = []
    nav_row = []
    
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"withdraw_history_page_{page-1}"))
    
    if offset + page_size < total_items:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"withdraw_history_page_{page+1}"))
        
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(get_string("back_btn", lang), callback_data="withdraw_info")])
    
    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await message_or_cb.answer() # Callback query answer
    else:
        await message_or_cb.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^req_withdraw_(Coin|Fly)$"))
async def process_withdraw(bot, cb):
    lang = cb.from_user.language_code
    currency = cb.data.split("_")[-1]
    
    balances = get_user_balances(cb.from_user.id)
    balance = balances[0] if currency == "Coin" else balances[1]
    min_limit = 10.0 if currency == "Coin" else 5.0
    
    if balance < min_limit:
        return await cb.answer(get_string("min_withdraw_alert", lang, limit=min_limit, currency=currency), show_alert=True)

    bdt_value = balance * 3 if currency == "Coin" else balance * 2
    text = get_string("sel_method_title", lang, amount=balance, currency=currency, bdt=bdt_value)
    
    buttons = [
        [
            InlineKeyboardButton("📱 bKash", callback_data=f"sel_method_bkash_{currency}_{balance}"),
            InlineKeyboardButton("💳 Wallet", callback_data=f"sel_method_wallet_{currency}_{balance}")
        ],
        [InlineKeyboardButton(get_string("cancel_btn", lang), callback_data="cancel_withdraw")]
    ]
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^sel_method_(bkash|wallet)_"))
async def method_selection_handler(bot, cb):
    lang = cb.from_user.language_code
    data = cb.data.split("_")
    method = data[2]
    currency = data[3]
    balance = data[4]
    
    update_user_state(cb.from_user.id, f"awaiting_{method}_{currency}_{balance}")
    prompt = get_string("bkash_prompt" if method == "bkash" else "wallet_prompt", lang)
    
    await cb.message.edit_text(
        f"💰 পরিমাণ: **{balance} {currency}**\n"
        f"⚙️ মাধ্যম: **{method.upper()}**\n\n"
        f"{prompt}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(get_string("cancel_btn", lang), callback_data="cancel_withdraw")
        ]])
    )

@Client.on_callback_query(filters.regex("^cancel_withdraw$"))
async def cancel_withdraw_handler(bot, cb):
    update_user_state(cb.from_user.id, None)
    await cb.answer("Cancelled" if cb.from_user.language_code != 'bn' else "বাতিল করা হয়েছে।")
    await withdraw_info_handler(bot, cb)

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def wallet_input_handler(bot, message):
    lang = message.from_user.language_code
    state = get_user_state(message.from_user.id)
    if not state or not (state.startswith("awaiting_wallet_") or state.startswith("awaiting_bkash_")):
    parts = state.split("_")
    method = parts[1]
    currency = parts[2]
    amount = float(parts[3])
    input_text = message.text

    if method == "bkash":
        if not re.match(r"^01[3-9]\d{8}$", input_text):
            return await message.reply_text(get_string("invalid_bkash", lang))
    
    wallet_info = f"{method.upper()}: {input_text}"
    
    if create_withdraw_request(message.from_user.id, amount, currency, wallet_info):
        await message.reply_text(get_string("withdraw_success", lang, amount=amount, currency=currency))
        update_user_state(message.from_user.id, None)
        
        for admin in ADMINS:
            try:
                await bot.send_message(admin, f"💰 **New Withdraw!**\n\nUser: {message.from_user.mention}\nAmount: {amount} {currency}\nWallet: {wallet_info}")
            except: pass
    else:
        await message.reply_text("❌ Failed. Check balance.")
        update_user_state(message.from_user.id, None)

@Client.on_callback_query(filters.regex(r"^v_ref_(\d+)"))
async def verify_ref_handler(bot, cb):
    inviter_id = int(cb.data.split("_")[-1])
    user_id = cb.from_user.id
    
    if not user_exists(user_id):
        add_user(user_id, cb.from_user.username or "User")
        if add_referral(user_id, inviter_id):
            try:
                await bot.send_message(inviter_id, "🎉 নতুন রেফারেল! আপনি **0.06 Coin** এবং **0.138 Fly** বোনাস পেয়েছেন।")
            except: pass
    
    await cb.message.edit_text("✅ ভেরিফিকেশন সফল হয়েছে! এখন আপনি বটটি ব্যবহার করতে পারবেন।")
    await asyncio.sleep(2)
    # ইউজারকে মেইন স্টার্ট হ্যান্ডলারে পাঠিয়ে দেওয়া
    from plugins.start import start_handler
    await start_handler(bot, cb.message)