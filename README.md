# Moataz Download Bot

بوت تيليجرام عربي لتحميل وتقطيع المقاطع العامة من YouTube وFacebook وInstagram باستخدام `yt-dlp` و`FFmpeg`، مع تشغيل Webhook عبر FastAPI، أزرار Inline شفافة، اختيار الجودة، استخراج MP3، لوحة إدارة محمية، وفحص صحة الخدمة.

> استخدم البوت فقط لتنزيل المحتوى الذي تملكه أو لديك إذن قانوني لتنزيله، والتزم بشروط المنصات وحقوق النشر.

## المميزات

- Webhook حقيقي عبر Telegram Bot API وFastAPI.
- تنزيل فيديو بجودات 360p و480p و720p و1080p وأفضل جودة متاحة.
- استخراج الصوت بصيغة MP3 بجودة 192kbps.
- تقطيع حر عبر: `الرابط | البداية | النهاية`.
- دعم الوقت بصيغ: ثوانٍ، `MM:SS`، `HH:MM:SS`.
- أزرار Inline للتنقل واختيار العملية والجودة.
- تنظيف تلقائي للملفات المؤقتة بعد الإرسال.
- تقييد النطاقات، الحجم، والمدة من متغيرات البيئة.
- حماية Webhook بمسار سري و`X-Telegram-Bot-Api-Secret-Token`.
- لوحة إدارة محمية بـ HTTP Basic Auth.
- نقطة فحص صحة `/health` وإحصاءات وقت التشغيل.
- جاهز للتشغيل على Termux أو Docker والتوسعة لاحقًا.

## بنية المشروع

```text
app/
  __init__.py
  bot.py          # تدفق البوت والأزرار والرسائل
  config.py       # إعدادات البيئة
  downloader.py   # yt-dlp وFFmpeg والتقطيع
  main.py         # FastAPI وWebhook والداشبورد
  state.py        # إحصاءات وقت التشغيل
scripts/
  setup-termux.sh
  start-termux.sh
.env.example
Dockerfile
requirements.txt
```

## المتطلبات

- Python 3.11 أو أحدث.
- FFmpeg.
- بوت من BotFather والحصول على `BOT_TOKEN`.
- رابط HTTPS عام ثابت أو نفق HTTPS مثل Cloudflare Tunnel أو ngrok، لأن Telegram Webhook لا يقبل رابط localhost مباشرًا.

## التشغيل على Termux

يفضل تثبيت Termux من F-Droid أو GitHub، ثم نفّذ:

```bash
pkg update -y && pkg upgrade -y
pkg install -y git
termux-setup-storage
cd ~
git clone https://github.com/Mtzallqmy/moataz-dowloadbot.git
cd moataz-dowloadbot
bash scripts/setup-termux.sh
```

عدّل ملف البيئة:

```bash
nano .env
```

مثال:

```env
BOT_TOKEN=ضع_توكن_البوت
PUBLIC_BASE_URL=https://your-public-domain.example
WEBHOOK_SECRET=ضع_سلسلة_عشوائية_طويلة_بدون_مسافات
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ضع_كلمة_مرور_قوية
DOWNLOAD_DIR=./downloads
MAX_FILE_MB=45
MAX_DURATION_SECONDS=7200
ALLOWED_DOMAINS=youtube.com,youtu.be,facebook.com,fb.watch,instagram.com
PORT=8000
```

شغّل الخادم:

```bash
bash scripts/start-termux.sh
```

سيعمل محليًا على:

```text
http://127.0.0.1:8000
```

## توفير رابط HTTPS في Termux

### Cloudflare Quick Tunnel

ثبّت `cloudflared` إذا كان متاحًا في مستودعات Termux:

```bash
pkg install cloudflared
cloudflared tunnel --url http://127.0.0.1:8000
```

انسخ رابط HTTPS الناتج وضعه في `PUBLIC_BASE_URL` داخل `.env`، ثم أعد تشغيل البوت. رابط Quick Tunnel يتغير عند إعادة تشغيل النفق، لذلك يلزم تحديث المتغير وإعادة التشغيل كل مرة. للإنتاج استخدم نطاقًا ثابتًا ونفق Cloudflare مسمى أو استضافة سحابية.

### ngrok

بعد إعداد ngrok وتشغيله:

```bash
ngrok http 8000
```

ضع رابط HTTPS الناتج في `PUBLIC_BASE_URL` ثم أعد تشغيل الخادم.

## اختبار التشغيل

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
```

لوحة الإدارة:

```text
https://YOUR_DOMAIN/dashboard
```

استخدم `ADMIN_USERNAME` و`ADMIN_PASSWORD`.

فحص Webhook من Telegram:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

## طريقة استخدام البوت

1. أرسل `/start`.
2. اختر فيديو أو MP3.
3. اختر جودة الفيديو عند الحاجة.
4. أرسل الرابط.
5. للتقطيع أرسل مثلًا:

```text
https://youtu.be/VIDEO_ID | 00:30 | 01:10
```

## التشغيل عبر Docker

```bash
docker build -t moataz-download-bot .
docker run --rm --env-file .env -p 8000:8000 -v "$PWD/downloads:/app/downloads" moataz-download-bot
```

## أوامر الصيانة

تحديث المشروع:

```bash
git pull
source .venv/bin/activate
pip install -U -r requirements.txt
```

تحديث yt-dlp فقط:

```bash
source .venv/bin/activate
pip install -U yt-dlp
```

عرض السجل مباشرة:

```bash
bash scripts/start-termux.sh 2>&1 | tee -a logs/bot.log
```

تشغيله في جلسة لا تتوقف عند إغلاق الشاشة:

```bash
pkg install tmux
tmux new -s downloadbot
bash scripts/start-termux.sh
```

للخروج مع إبقاء الجلسة تعمل: اضغط `Ctrl+B` ثم `D`، وللعودة:

```bash
tmux attach -t downloadbot
```

## حدود مهمة

- Telegram يفرض حدودًا على إرسال الملفات للبوتات؛ اجعل `MAX_FILE_MB` مناسبًا لحسابك وبيئة التشغيل.
- بعض روابط Facebook وInstagram الخاصة أو المقيدة قد تتطلب Cookies. لم يتم تضمين تجاوز الحماية أو تسجيل الدخول الآلي.
- تشغيل خادم دائم على هاتف Android أقل استقرارًا من VPS بسبب إدارة البطارية والشبكة. عطّل تحسين البطارية لتطبيق Termux عند الاختبار.
- الإحصاءات الحالية محفوظة في الذاكرة وتُصفّر عند إعادة التشغيل. يمكن لاحقًا إضافة PostgreSQL أو SQLite وقائمة مستخدمين وسجل مهام دائم.

## الأمان

- لا ترفع ملف `.env` إلى GitHub.
- استخدم سر Webhook طويلًا وعشوائيًا وكلمة مرور إدارة قوية.
- لا تجعل لوحة الإدارة عامة دون HTTPS.
- لا توسّع `ALLOWED_DOMAINS` إلا لنطاقات موثوقة.
- المشروع لا يدعم تنزيل المحتوى المحمي بحقوق رقمية DRM أو تجاوز القيود الأمنية.

## الترخيص

أضف الترخيص المناسب قبل الاستخدام التجاري أو التوزيع الواسع.

جميع الحقوق محفوظة — معتز العلقمي
