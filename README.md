# Greed Premium — Railway Ready

این پروژه یک پیاده‌سازی مستقل از ظاهر و جریان‌های ربات نمونه است؛ سورس خصوصی ربات اصلی استخراج یا کپی نشده است.

## مشخصات تنظیم‌شده
- Admin ID: `6189261314`
- کانال عضویت اجباری: `@Rbnwei`
- کانال گزارش: `@andksaox`
- لینک Start نمونه: `https://t.me/MewAirdropRoBot?start=8834403023`
- موجودی اولیه: `$3`
- پاداش هر زیرمجموعه: `$4`
- حداقل برداشت: `$75`
- حداقل زیرمجموعه: `9`

## فایل‌ها
- `bot.py` — کد اصلی
- `requirements.txt` — وابستگی‌ها
- `Dockerfile` — اجرای پایدار
- `railway.toml` — Start/Restart
- `.env.example` — نمونه Variables
- `Procfile` — fallback برای Railway
- `.gitignore`
- `README.md`

## راه‌اندازی با GitHub → Railway

### 1) GitHub
همه فایل‌های این پوشه را در ریشه Repository قرار بده.

### 2) Railway
در Railway:
`New Project` → `Deploy from GitHub Repo` → Repository را انتخاب کن.

Railway برای پروژه‌های کدی معمولاً build و deploy را تشخیص می‌دهد و Dockerfile/Procfile هم در پروژه قرار داده شده‌اند.

### 3) Variables
در Service → Variables این مورد را حتماً بساز:

`BOT_TOKEN` = توکن واقعی BotFather

این مقادیر هم داخل پروژه تنظیم شده‌اند، ولی بهتر است در Variables هم وارد شوند:
- `ADMIN_IDS=6189261314`
- `REPORT_CHANNEL=@andksaox`
- `FORCED_CHANNEL=@Rbnwei`
- `FORCED_CHANNEL_URL=https://t.me/Rbnwei`
- `BOT_START_URL=https://t.me/MewAirdropRoBot?start=8834403023`
- `START_BALANCE=3`
- `REFERRAL_REWARD=4`
- `MIN_WITHDRAW=75`
- `MIN_REFS=9`
- `DB_FILE=/data/bot_database.db`

### 4) ذخیره دائمی دیتابیس
برای اینکه با Restart/Deploy اطلاعات کاربران و موجودی‌ها از بین نرود، در Railway یک **Volume** بساز و آن را روی:
`/data`
Mount کن.

سپس:
`DB_FILE=/data/bot_database.db`

را در Variables قرار بده.

### 5) Start Command
اگر Railway خودش Start Command را تشخیص نداد:
`python bot.py`

### 6) Deploy
Deploy را بزن و Logs را باز کن. در حالت سالم باید پیام شروع ربات را ببینی.

## نکته مهم درباره رنگ دکمه‌ها
Telegram اجازه نمی‌دهد Bot API رنگ پس‌زمینه ReplyKeyboard را برای هر دکمه تعیین کند. بنابراین این نسخه چیدمان، متن و ظاهر ایموجی‌دار مشابه نمونه را پیاده می‌کند؛ رنگ واقعی ReplyKeyboard توسط کلاینت/تم Telegram تعیین می‌شود.

اگر رنگ اختصاصی واقعی برای هر دکمه بخواهی، باید همین پروژه به Telegram Mini App/Web App تبدیل شود.

## امنیت
توکن ربات را داخل GitHub نگذار. فقط در Railway Variables قرار بده. Railway متغیرها را در زمان اجرا به برنامه می‌دهد.
