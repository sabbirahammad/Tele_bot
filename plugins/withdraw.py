import asyncio
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply, CallbackQuery
from database import get_user_balances, create_withdraw_request, update_user_state, get_user_state, get_user_withdraw_history, count_referrals, add_user, add_referral, user_exists
import os
import re

ADMINS = [int(id) for id in os.getenv("ADMIN_ID", "0").split()]

@Client.on_callback_query(filters.regex("^withdraw_info$"))
async def withdraw_info_handler(bot, cb):
    balances = get_user_balances(cb.from_user.id)
    coin = balances[0]
    fly = balances[1]
    
    # ১ কয়েন = ৩ টাকা, ১ ফ্লাই = ২ টাকা হিসেবে ক্যালকুলেশন
    coin_in_bdt = coin * 3
    fly_in_bdt = fly * 2

    text = (
        "💳 **উইথড্রাল ড্যাশবোর্ড**\n\n"
        f"🪙 Coin Balance: {coin:.2f} (≈ {coin_in_bdt:.2f} BDT)\n"
        f"💸 Fly Balance: {fly:.4f} (≈ {fly_in_bdt:.2f} BDT)\n\n"
        "✅ পেমেন্ট মেথড: bKash (Personal) অথবা Crypto Wallet\n"
        "💰 কনভার্সন রেট: 1 Coin = 3 BDT | 1 Fly = 2 BDT\n"
        "🛑 মিনিমাম উইথড্র: 10.00 Coin / 5.00 Fly\n"
        "নিচের বাটনে ক্লিক করে উইথড্র রিকোয়েস্ট দিন:"
    )
    
    buttons = [
        [
            InlineKeyboardButton("Withdraw Coin", callback_data="req_withdraw_Coin"),
            InlineKeyboardButton("Withdraw Fly", callback_data="req_withdraw_Fly")
        ],
        [InlineKeyboardButton("📜 উইথড্র হিস্ট্রি", callback_data="withdraw_history")],
        [InlineKeyboardButton("⬅️ ফিরে যান", callback_data="start_menu")]
    ]
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^referral_stats$"))
async def referral_stats_handler(bot, cb):
    user_id = cb.from_user.id
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    total_referrals = count_referrals(user_id)
    
    text = (
        "👥 **রেফারেল সিস্টেম**\n\n"
        f"🔗 **আপনার রেফারেল লিংক:**\n`{referral_link}`\n\n"
        f"📊 **মোট রেফারেল:** {total_referrals} জন\n\n"
        "💰 **রিওয়ার্ড পলিসি:**\n"
        "১. আপনার লিংকে কেউ জয়েন করলে পাবেন **0.06 Coin** ও **0.138 Fly**।\n"
        "২. আপনার রেফারেল প্রতিদিন সার্চ করলে আপনি পাবেন **0.013 Fly** রিওয়ার্ড।\n\n"
        "লিংকটি বন্ধুদের সাথে শেয়ার করুন এবং আনলিমিটেড ইনকাম করুন!"
    )
    
    buttons = [
        [InlineKeyboardButton("🚀 বন্ধুদের পাঠান", url=f"https://t.me/share/url?url={referral_link}")],
        [InlineKeyboardButton("⬅️ ফিরে যান", callback_data="start_menu")]
    ]
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cb.answer()

@Client.on_message(filters.command("withdraw_history") & filters.private)
@Client.on_callback_query(filters.regex("^withdraw_history$"))
@Client.on_callback_query(filters.regex("^withdraw_history_page_(\\d+)$"))
async def withdraw_history_handler(bot, message_or_cb: CallbackQuery, page=0):
    user_id = message_or_cb.from_user.id
    
    if isinstance(message_or_cb, CallbackQuery) and message_or_cb.data.startswith("withdraw_history_page_"):
        page = int(message_or_cb.data.split("_")[-1])
    elif isinstance(message_or_cb, CallbackQuery) and message_or_cb.data == "withdraw_history":
        page = 0 # যখন প্রথমবার "উইথড্র হিস্ট্রি" বাটনে ক্লিক করা হবে
    
    page_size = 5
    offset = page * page_size
    
    history, total_items = get_user_withdraw_history(user_id, offset, page_size)
    
    if not history:
        text = "📭 আপনার কোনো উইথড্র হিস্ট্রি পাওয়া যায়নি।"
    else:
        text = f"📜 **আপনার উইথড্র হিস্ট্রি ({total_items}টি রিকোয়েস্ট):**\n\n"
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

    buttons.append([InlineKeyboardButton("⬅️ ফিরে যান", callback_data="withdraw_info")])
    
    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
        await message_or_cb.answer() # Callback query answer
    else:
        await message_or_cb.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^req_withdraw_(Coin|Fly)$"))
async def process_withdraw(bot, cb):
    currency = cb.data.split("_")[-1]

    # উইথড্রাল ড্যাশবোর্ড থেকে এখানে আসার সময় আগের মেসেজ ডিলিট করতে হবে না
    # বরং এডিট করতে হবে, কারণ ক্যান্সেল বাটনটি এই মেসেজেই যুক্ত হবে।
    # তাই cb.message.edit_text ব্যবহার করা হয়েছে।
    # যদি cb.message.delete() ব্যবহার করা হত, তবে ক্যান্সেল বাটন কাজ করত না।
    
    balances = get_user_balances(cb.from_user.id)
    balance = balances[0] if currency == "Coin" else balances[1]
    min_limit = 10.0 if currency == "Coin" else 5.0
    
    if balance < min_limit:
        return await cb.answer(f"❌ মিনিমাম উইথড্র {min_limit} {currency}। আপনার বর্তমান ব্যালেন্স কম।", show_alert=True)

    # BDT ভ্যালু হিসাব করা
    bdt_value = balance * 3 if currency == "Coin" else balance * 2

    text = f"🏦 আপনি **{balance} {currency}** (অর্থাৎ **{bdt_value:.2f} BDT**) উইথড্র করতে চেয়েছেন।\n\nপেমেন্ট নেওয়ার মাধ্যমটি বেছে নিন:"
    buttons = [
        [
            InlineKeyboardButton("📱 bKash", callback_data=f"sel_method_bkash_{currency}_{balance}"),
            InlineKeyboardButton("💳 Wallet", callback_data=f"sel_method_wallet_{currency}_{balance}")
        ],
        [InlineKeyboardButton("❌ বাতিল", callback_data="cancel_withdraw")]
    ]
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@Client.on_callback_query(filters.regex("^sel_method_(bkash|wallet)_"))
async def method_selection_handler(bot, cb):
    data = cb.data.split("_")
    method = data[2]
    currency = data[3]
    balance = data[4]
    
    update_user_state(cb.from_user.id, f"awaiting_{method}_{currency}_{balance}")
    
    prompt = "📱 আপনার **বিকাশ পার্সোনাল নম্বরটি** (১১ ডিজিট) লিখে পাঠান:" if method == "bkash" else "💳 আপনার **ওয়ালেট অ্যাড্রেসটি** লিখে পাঠান:"
    
    await cb.message.edit_text(
        f"💰 পরিমাণ: **{balance} {currency}**\n"
        f"⚙️ মাধ্যম: **{method.upper()}**\n\n"
        f"{prompt}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ বাতিল করুন", callback_data="cancel_withdraw")
        ]])
    )

@Client.on_callback_query(filters.regex("^cancel_withdraw$"))
async def cancel_withdraw_handler(bot, cb):
    # স্টেট ক্লিয়ার করা
    update_user_state(cb.from_user.id, None)
    await cb.answer("উইথড্রাল বাতিল করা হয়েছে।", show_alert=True)
    # আবার ড্যাশবোর্ডে ফিরিয়ে নিয়ে যাওয়া
    await withdraw_info_handler(bot, cb)

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def wallet_input_handler(bot, message):
    state = get_user_state(message.from_user.id)
    if not state or not (state.startswith("awaiting_wallet_") or state.startswith("awaiting_bkash_")):
        return # যদি কোনো উইথড্রাল প্রসেসে না থাকে তবে কিছু করবে না

    # স্টেট থেকে কারেন্সি এবং অ্যামাউন্ট বের করা
    parts = state.split("_")
    method = parts[1]
    currency = parts[2]
    amount = float(parts[3])
    input_text = message.text

    if method == "bkash":
        if not re.match(r"^01[3-9]\d{8}$", input_text):
            return await message.reply_text("❌ সঠিক বিকাশ নম্বর দিন (১১ ডিজিট, যেমন: 017XXXXXXXX)")
    
    wallet_info = f"{method.upper()}: {input_text}"
    
    if create_withdraw_request(message.from_user.id, amount, currency, wallet_info):
        await message.reply_text(
            f"✅ আপনার {amount} {currency} উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে।\n"
            "অ্যাডমিন ২৪ ঘণ্টার মধ্যে আপনার সাথে যোগাযোগ করবে।"
        )
        # স্টেট ক্লিয়ার করা
        update_user_state(message.from_user.id, None)
        
        # অ্যাডমিনকে নোটিফিকেশন
        for admin in ADMINS:
            try:
                await bot.send_message(
                    admin,
                    f"💰 **নতুন উইথড্র রিকোয়েস্ট!**\n\n"
                    f"👤 ইউজার: {message.from_user.mention} (`{message.from_user.id}`)\n"
                    f"💵 পরিমাণ: {amount} {currency}\n"
                    f"🏦 মাধ্যম: {wallet_info}"
                )
            except: pass
    else:
        await message.reply_text("❌ ট্রানজেকশন প্রসেস করা সম্ভব হয়নি। ব্যালেন্স চেক করুন।")
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