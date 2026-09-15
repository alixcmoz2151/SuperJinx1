import os
import re
import sqlite3
import threading
import logging
from datetime import datetime

import telebot
from telebot import types

# =========================================================
# Greed Premium — Telegram Referral / Withdrawal Bot
# Railway-ready | SQLite | Persian UI
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Optional settings — change them from Railway Variables
BOT_NAME = os.getenv("BOT_NAME", "Greed")
REPORT_CHANNEL = os.getenv("REPORT_CHANNEL", "@andksaox").strip()       # e.g. @your_report_channel
FORCED_CHANNEL = os.getenv("FORCED_CHANNEL", "@Rbnwei").strip()       # e.g. @your_required_channel
FORCED_CHANNEL_URL = os.getenv("FORCED_CHANNEL_URL", "https://t.me/Rbnwei").strip()
BOT_START_URL = os.getenv("BOT_START_URL", "https://t.me/MewAirdropRoBot?start=8834403023").strip()

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "6189261314").split(",")
    if x.strip().isdigit()
}

START_BALANCE = float(os.getenv("START_BALANCE", "3"))
REFERRAL_REWARD = float(os.getenv("REFERRAL_REWARD", "4"))
MIN_WITHDRAW = float(os.getenv("MIN_WITHDRAW", "75"))
MIN_REFS = int(os.getenv("MIN_REFS", "9"))
DB_FILE = os.getenv("DB_FILE", "bot_database.db")

# Main button labels — editable from Railway Variables
BTN_ACCOUNT = os.getenv("BTN_ACCOUNT", "👤 حساب کاربری")
BTN_REFERRAL = os.getenv("BTN_REFERRAL", "👥 زیرمجموعه گیری")
BTN_WITHDRAW = os.getenv("BTN_WITHDRAW", "💸 برداشت")
BTN_GUIDE = os.getenv("BTN_GUIDE", "⁉️ راهنما")

# Optional guide image. Put guide.jpg beside bot.py, or leave empty.
GUIDE_IMAGE = os.getenv("GUIDE_IMAGE", "guide.jpg")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add BOT_TOKEN in Railway Variables.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True)
db_lock = threading.RLock()


# ------------------------- Database -------------------------

def db():
    conn = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    with db_lock, db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL NOT NULL DEFAULT 0,
                refs INTEGER NOT NULL DEFAULT 0,
                wallet TEXT DEFAULT '',
                invited_by INTEGER DEFAULT NULL,
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                is_blocked INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                wallet TEXT NOT NULL,
                refs INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                confirmed_at TEXT DEFAULT NULL
            )
        """)
        conn.commit()


init_db()


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def upsert_user(user, invited_by=None):
    uid = user.id
    username = user.username or ""
    first_name = user.first_name or ""
    timestamp = now()

    with db_lock, db() as conn:
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (uid,)
        ).fetchone()

        if row:
            conn.execute("""
                UPDATE users
                SET username = ?, first_name = ?, last_seen = ?, is_blocked = 0
                WHERE user_id = ?
            """, (username, first_name, timestamp, uid))
        else:
            valid_inviter = None
            if invited_by and invited_by != uid:
                inviter = conn.execute(
                    "SELECT user_id FROM users WHERE user_id = ?",
                    (invited_by,)
                ).fetchone()
                if inviter:
                    valid_inviter = invited_by

            conn.execute("""
                INSERT INTO users
                (user_id, username, first_name, balance, refs, wallet,
                 invited_by, created_at, last_seen)
                VALUES (?, ?, ?, ?, 0, '', ?, ?, ?)
            """, (
                uid, username, first_name, START_BALANCE,
                valid_inviter, timestamp, timestamp
            ))
        conn.commit()


def get_user(user_id):
    with db_lock, db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()


def add_referral_if_new(referrer_id, referred_id):
    if not referrer_id or referrer_id == referred_id:
        return False

    with db_lock, db() as conn:
        referrer = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (referrer_id,)
        ).fetchone()
        referred = conn.execute(
            "SELECT user_id, invited_by FROM users WHERE user_id = ?",
            (referred_id,)
        ).fetchone()

        if not referrer or not referred:
            return False

        if referred["invited_by"] not in (None, 0):
            return False

        already = conn.execute(
            "SELECT id FROM referrals WHERE referred_id = ?",
            (referred_id,)
        ).fetchone()
        if already:
            return False

        conn.execute("""
            INSERT INTO referrals(referrer_id, referred_id, created_at)
            VALUES (?, ?, ?)
        """, (referrer_id, referred_id, now()))

        conn.execute("""
            UPDATE users
            SET balance = balance + ?, refs = refs + 1
            WHERE user_id = ?
        """, (REFERRAL_REWARD, referrer_id))

        conn.execute("""
            UPDATE users SET invited_by = ? WHERE user_id = ?
        """, (referrer_id, referred_id))

        conn.commit()
        return True


# ------------------------- Keyboards -------------------------

def main_keyboard():
    # Telegram Bot API does NOT provide arbitrary per-button background colors
    # for ReplyKeyboard. The layout below mirrors the reference screenshot.
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(BTN_ACCOUNT)
    kb.row(BTN_WITHDRAW, BTN_REFERRAL)
    kb.row(BTN_GUIDE)
    return kb


def force_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)

    if FORCED_CHANNEL_URL:
        kb.add(types.InlineKeyboardButton(
            "📢 عضو کانال",
            url=FORCED_CHANNEL_URL
        ))
    elif FORCED_CHANNEL:
        kb.add(types.InlineKeyboardButton(
            "📢 عضو کانال",
            url=f"https://t.me/{FORCED_CHANNEL.lstrip('@')}"
        ))

    if BOT_START_URL:
        kb.add(types.InlineKeyboardButton(
            "🚀 فقط استارت کن",
            url=BOT_START_URL
        ))

    kb.add(types.InlineKeyboardButton(
        "✅ عضو شدم / چک کن",
        callback_data="check_force"
    ))
    return kb


def admin_withdraw_keyboard(withdraw_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "✅ تایید پرداخت",
        callback_data=f"confirm_withdraw:{withdraw_id}"
    ))
    kb.add(types.InlineKeyboardButton(
        "❌ رد درخواست",
        callback_data=f"reject_withdraw:{withdraw_id}"
    ))
    return kb


# ------------------------- Force Subscribe -------------------------

def is_member(user_id):
    if not FORCED_CHANNEL:
        return True

    try:
        member = bot.get_chat_member(FORCED_CHANNEL, user_id)
        return member.status in ("creator", "administrator", "member")
    except Exception as e:
        logging.warning("Membership check failed: %s", e)
        # If the channel cannot be checked (bad username / bot not admin),
        # do not lock all users out.
        return True


def show_force_message(chat_id):
    text = (
        "🔒 <b>برای استفاده از ربات ابتدا عضو کانال شوید.</b>\n\n"
        "بعد از عضویت روی «عضو شدم / چک کن» بزنید."
    )
    bot.send_message(chat_id, text, reply_markup=force_keyboard())


def welcome(chat_id):
    bot.send_message(
        chat_id,
        "سلام 👀\n"
        "به ربات ما خوش‌اومدی.\n\n"
        "خدمات مورد نظرت رو انتخاب کن 👇",
        reply_markup=main_keyboard()
    )


# ------------------------- Referral -------------------------

def parse_start_ref(message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None

    value = parts[1].strip()
    if value.startswith("ref_"):
        value = value[4:]

    return int(value) if value.isdigit() else None


def referral_link(user_id):
    me = bot.get_me()
    return f"https://t.me/{me.username}?start={user_id}"


# ------------------------- Handlers -------------------------

@bot.message_handler(commands=["start"])
def start_handler(message):
    invited_by = parse_start_ref(message)
    upsert_user(message.from_user, invited_by)

    if not is_member(message.from_user.id):
        show_force_message(message.chat.id)
        return

    credited = add_referral_if_new(invited_by, message.from_user.id)

    welcome(message.chat.id)

    if credited:
        referrer = get_user(invited_by)
        if referrer:
            try:
                bot.send_message(
                    invited_by,
                    f"🎉 <b>یک کاربر جدید با لینک شما وارد شد!</b>\n\n"
                    f"👤 کاربر: {message.from_user.first_name or 'کاربر'}\n"
                    f"💰 پاداش: <b>${REFERRAL_REWARD:.2f}</b>\n"
                    f"👥 تعداد زیرمجموعه: <b>{referrer['refs']}</b>",
                )
            except Exception:
                pass


@bot.callback_query_handler(func=lambda c: c.data == "check_force")
def check_force_callback(call):
    if is_member(call.from_user.id):
        bot.answer_callback_query(call.id, "عضویت تایید شد ✅")
        welcome(call.message.chat.id)
    else:
        bot.answer_callback_query(
            call.id,
            "هنوز عضویت شما تایید نشده است.",
            show_alert=True
        )


@bot.message_handler(func=lambda m: m.text == BTN_ACCOUNT)
def account_handler(message):
    if not is_member(message.from_user.id):
        show_force_message(message.chat.id)
        return

    user = get_user(message.from_user.id)
    if not user:
        upsert_user(message.from_user)
        user = get_user(message.from_user.id)

    link = referral_link(message.from_user.id)
    text = (
        "👤 <b>حساب کاربری شما</b>\n\n"
        f"🆔 آیدی شما: <code>{user['user_id']}</code>\n"
        f"💰 موجودی شما: <b>${user['balance']:.2f}</b>\n"
        f"👥 تعداد زیرمجموعه‌ها: <b>{user['refs']}</b>\n\n"
        f"🔗 <b>لینک دعوت اختصاصی:</b>\n"
        f"<code>{link}</code>"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "📋 کپی لینک دعوت",
        callback_data="copy_ref"
    ))
    bot.send_message(message.chat.id, text, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "copy_ref")
def copy_ref_callback(call):
    link = referral_link(call.from_user.id)
    bot.answer_callback_query(call.id, "لینک در پیام بالا قابل کپی است 📋")
    try:
        bot.send_message(
            call.message.chat.id,
            f"📋 <b>لینک دعوت شما:</b>\n<code>{link}</code>\n\n"
            "روی متن لینک نگه دارید و آن را کپی کنید."
        )
    except Exception:
        pass


@bot.message_handler(func=lambda m: m.text == BTN_REFERRAL)
def referral_handler(message):
    if not is_member(message.from_user.id):
        show_force_message(message.chat.id)
        return

    user = get_user(message.from_user.id)
    link = referral_link(message.from_user.id)

    bot.send_message(
        message.chat.id,
        "📈 <b>با دعوت دوستان درآمد کسب کن!</b>\n\n"
        f"دوستات رو به ربات دعوت کن و به ازای هر نفر "
        f"<b>${REFERRAL_REWARD:.2f}</b> پاداش بگیر 💵\n\n"
        f"🔗 <b>لینک اختصاصی دعوت شما:</b>\n"
        f"<code>{link}</code>\n\n"
        "⏳ هرچه افراد بیشتری دعوت کنی، موجودی‌ات سریع‌تر افزایش پیدا می‌کند.",
    )


@bot.message_handler(func=lambda m: m.text == BTN_WITHDRAW)
def withdraw_start(message):
    if not is_member(message.from_user.id):
        show_force_message(message.chat.id)
        return

    user = get_user(message.from_user.id)
    if not user:
        upsert_user(message.from_user)
        user = get_user(message.from_user.id)

    if user["balance"] < MIN_WITHDRAW:
        bot.send_message(
            message.chat.id,
            "❌ <b>امکان برداشت وجود ندارد.</b>\n\n"
            f"💰 موجودی فعلی: <b>${user['balance']:.2f}</b>\n"
            f"💵 حداقل برداشت: <b>${MIN_WITHDRAW:.2f}</b>\n"
            f"👥 حداقل زیرمجموعه موردنیاز: <b>{MIN_REFS}</b>"
        )
        return

    if user["refs"] < MIN_REFS:
        bot.send_message(
            message.chat.id,
            "❌ <b>تعداد زیرمجموعه کافی نیست.</b>\n\n"
            f"👥 زیرمجموعه فعلی: <b>{user['refs']}</b>\n"
            f"📌 حداقل موردنیاز: <b>{MIN_REFS}</b>"
        )
        return

    msg = bot.send_message(
        message.chat.id,
        "💳 <b>آدرس کیف پول خود را ارسال کنید.</b>\n\n"
        "مثال: آدرس شبکه موردنظر خود را دقیق ارسال کنید.\n"
        "⚠️ قبل از ارسال، شبکه و آدرس را دوباره بررسی کنید."
    )
    bot.register_next_step_handler(msg, receive_wallet)


def receive_wallet(message):
    if not message.text:
        msg = bot.send_message(message.chat.id, "❌ آدرس معتبر ارسال کنید.")
        bot.register_next_step_handler(msg, receive_wallet)
        return

    wallet = message.text.strip()
    if len(wallet) < 12 or len(wallet) > 150:
        msg = bot.send_message(message.chat.id, "❌ فرمت آدرس مناسب نیست. دوباره ارسال کنید.")
        bot.register_next_step_handler(msg, receive_wallet)
        return

    user = get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "❌ کاربر پیدا نشد. دوباره /start را بزنید.")
        return

    amount = MIN_WITHDRAW

    with db_lock, db() as conn:
        # Prevent multiple pending requests for the same user.
        pending = conn.execute("""
            SELECT id FROM withdrawals
            WHERE user_id = ? AND status = 'pending'
        """, (message.from_user.id,)).fetchone()

        if pending:
            bot.send_message(message.chat.id, "⏳ یک درخواست برداشت شما هنوز در حال بررسی است.")
            return

        cur = conn.execute("""
            INSERT INTO withdrawals
            (user_id, amount, wallet, refs, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        """, (message.from_user.id, amount, wallet, user["refs"], now()))
        withdrawal_id = cur.lastrowid

        # Reserve the amount immediately to prevent double spending.
        conn.execute("""
            UPDATE users SET balance = balance - ? WHERE user_id = ?
        """, (amount, message.from_user.id))
        conn.commit()

    bot.send_message(
        message.chat.id,
        "✅ <b>درخواست برداشت با موفقیت ثبت شد!</b>\n\n"
        f"💵 مبلغ: <b>${amount:.2f}</b>\n"
        "📨 درخواست شما برای بررسی ارسال شد."
    )

    report = (
        "💸 <b>درخواست برداشت جدید</b>\n\n"
        f"🆔 User ID: <code>{user['user_id']}</code>\n"
        f"👤 Username: @{user['username'] or 'ندارد'}\n"
        f"💰 مبلغ: <b>${amount:.2f}</b>\n"
        f"👥 زیرمجموعه: <b>{user['refs']}</b>\n"
        f"💳 کیف پول:\n<code>{wallet}</code>\n"
        f"🔢 شماره درخواست: <code>#{withdrawal_id}</code>\n"
        f"🕐 زمان: <code>{now()}</code>"
    )

    targets = set(ADMIN_IDS)
    if REPORT_CHANNEL:
        targets.add(REPORT_CHANNEL)

    for target in targets:
        try:
            bot.send_message(
                target,
                report,
                reply_markup=admin_withdraw_keyboard(withdrawal_id)
            )
        except Exception as e:
            logging.warning("Could not send withdrawal report to %s: %s", target, e)


# ------------------------- Admin withdrawal actions -------------------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_withdraw:"))
def confirm_withdraw(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "دسترسی ندارید.", show_alert=True)
        return

    withdrawal_id = int(call.data.split(":", 1)[1])

    with db_lock, db() as conn:
        row = conn.execute("""
            SELECT w.*, u.username
            FROM withdrawals w
            JOIN users u ON u.user_id = w.user_id
            WHERE w.id = ?
        """, (withdrawal_id,)).fetchone()

        if not row:
            bot.answer_callback_query(call.id, "درخواست پیدا نشد.", show_alert=True)
            return

        if row["status"] != "pending":
            bot.answer_callback_query(call.id, "این درخواست قبلاً پردازش شده.", show_alert=True)
            return

        conn.execute("""
            UPDATE withdrawals
            SET status = 'confirmed', confirmed_at = ?
            WHERE id = ?
        """, (now(), withdrawal_id))
        conn.commit()

    bot.answer_callback_query(call.id, "پرداخت تایید شد ✅")
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
    except Exception:
        pass

    try:
        bot.send_message(
            row["user_id"],
            "✅ <b>پرداخت شما تایید شد!</b>\n\n"
            f"💵 مبلغ درخواست: <b>${row['amount']:.2f}</b>\n"
            "درخواست شما با موفقیت تایید و ارسال شد."
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith("reject_withdraw:"))
def reject_withdraw(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "دسترسی ندارید.", show_alert=True)
        return

    withdrawal_id = int(call.data.split(":", 1)[1])

    with db_lock, db() as conn:
        row = conn.execute("""
            SELECT * FROM withdrawals WHERE id = ?
        """, (withdrawal_id,)).fetchone()

        if not row:
            bot.answer_callback_query(call.id, "درخواست پیدا نشد.", show_alert=True)
            return

        if row["status"] != "pending":
            bot.answer_callback_query(call.id, "این درخواست قبلاً پردازش شده.", show_alert=True)
            return

        # Return reserved funds on rejection.
        conn.execute("""
            UPDATE users SET balance = balance + ? WHERE user_id = ?
        """, (row["amount"], row["user_id"]))

        conn.execute("""
            UPDATE withdrawals
            SET status = 'rejected', confirmed_at = ?
            WHERE id = ?
        """, (now(), withdrawal_id))
        conn.commit()

    bot.answer_callback_query(call.id, "درخواست رد شد ❌")
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
    except Exception:
        pass

    try:
        bot.send_message(
            row["user_id"],
            "❌ <b>درخواست برداشت شما رد شد.</b>\n\n"
            "مبلغ رزروشده به موجودی شما برگشت داده شد."
        )
    except Exception:
        pass


@bot.message_handler(func=lambda m: m.text == BTN_GUIDE)
def guide_handler(message):
    if not is_member(message.from_user.id):
        show_force_message(message.chat.id)
        return

    text = (
        "📚 <b>راهنمای ربات</b>\n\n"
        "👥 <b>زیرمجموعه گیری:</b>\n"
        f"به ازای هر کاربر واقعی که با لینک شما وارد شود "
        f"<b>${REFERRAL_REWARD:.2f}</b> پاداش می‌گیرید.\n\n"
        "👤 <b>حساب کاربری:</b>\n"
        "موجودی، تعداد زیرمجموعه و لینک اختصاصی شما را نمایش می‌دهد.\n\n"
        "💸 <b>برداشت:</b>\n"
        f"حداقل برداشت <b>${MIN_WITHDRAW:.2f}</b> و حداقل "
        f"<b>{MIN_REFS}</b> زیرمجموعه لازم است.\n\n"
        "⚠️ هنگام ثبت برداشت، آدرس کیف پول و شبکه را با دقت بررسی کنید."
    )

    if GUIDE_IMAGE and os.path.exists(GUIDE_IMAGE):
        try:
            with open(GUIDE_IMAGE, "rb") as photo:
                bot.send_photo(message.chat.id, photo)
        except Exception:
            pass

    bot.send_message(message.chat.id, text)


# ------------------------- Admin commands -------------------------

@bot.message_handler(commands=["stats"])
def stats_handler(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    with db_lock, db() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        refs = conn.execute("SELECT COUNT(*) AS c FROM referrals").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM withdrawals WHERE status='pending'"
        ).fetchone()["c"]

    bot.send_message(
        message.chat.id,
        "📊 <b>آمار ربات</b>\n\n"
        f"👤 کاربران: <b>{users}</b>\n"
        f"👥 دعوت‌های ثبت‌شده: <b>{refs}</b>\n"
        f"💸 برداشت‌های در انتظار: <b>{pending}</b>"
    )


@bot.message_handler(commands=["broadcast"])
def broadcast_help(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    bot.send_message(
        message.chat.id,
        "برای ارسال پیام همگانی:\n"
        "<code>/broadcast متن پیام</code>"
    )


@bot.message_handler(commands=["setbalance"])
def set_balance(message):
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit():
        bot.send_message(message.chat.id, "فرمت: /setbalance USER_ID AMOUNT")
        return

    uid = int(parts[1])
    try:
        amount = float(parts[2])
    except ValueError:
        bot.send_message(message.chat.id, "مبلغ نامعتبر است.")
        return

    with db_lock, db() as conn:
        conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (amount, uid)
        )
        conn.commit()

    bot.send_message(message.chat.id, "موجودی تنظیم شد ✅")


# ------------------------- Error-safe polling -------------------------

def run():
    logging.info("Starting %s bot...", BOT_NAME)
    logging.info(
        "Config: reward=$%.2f | min_withdraw=$%.2f | min_refs=%d",
        REFERRAL_REWARD, MIN_WITHDRAW, MIN_REFS
    )

    # Drop old updates after deployment/restart.
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30,
        skip_pending=True,
        allowed_updates=["message", "callback_query"]
    )


if __name__ == "__main__":
    run()
