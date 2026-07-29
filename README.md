# Moataz Download Bot

بوت Telegram عربي لتحميل وتقطيع المقاطع العامة من YouTube وFacebook وInstagram، مهيأ للعمل على خادم سحابي خاص باستخدام Docker وDocker Compose مع HTTPS تلقائي عبر Caddy.

> استخدم البوت فقط للمحتوى الذي تملكه أو لديك إذن قانوني لتنزيله، والتزم بحقوق النشر وشروط المنصات.

## المزايا

- تنزيل الفيديو والصوت بصيغ متعددة عبر `yt-dlp` وFFmpeg.
- عرض الصيغ المتاحة قبل بدء التنزيل.
- دعم التقطيع بصيغة: `الرابط | البداية | النهاية`.
- Webhook محمي بسر Telegram.
- رفع الملفات الصغيرة مباشرة إلى Telegram.
- روابط HTTPS مؤقتة للملفات الأكبر من حد Telegram.
- لوحة إدارة محمية على `/dashboard`.
- فحص صحة على `/health`.
- تخزين دائم للتنزيلات والسجلات باستخدام Docker volumes.
- إعادة تشغيل تلقائية عند تعطل الخدمة أو إعادة تشغيل الخادم.
- تشغيل داخل مستخدم غير root مع تقليل صلاحيات الحاوية.
- HTTPS تلقائي وتجديد تلقائي للشهادة عبر Caddy.

## متطلبات الخادم

- خادم Ubuntu أو Debian حديث.
- اسم نطاق يشير إلى عنوان IP الخاص بالخادم.
- فتح المنافذ `80` و`443` في الجدار الناري.
- Docker Engine وDocker Compose Plugin.

## التثبيت

```bash
git clone https://github.com/Mtzallqmy/moataz-dowloadbot.git
cd moataz-dowloadbot
git checkout cloud-server-production
cp .env.example .env
nano .env
```

عدّل القيم الأساسية:

```env
DOMAIN=bot.example.com
APP_MODE=webhook
BOT_TOKEN=ضع_توكن_البوت
PUBLIC_BASE_URL=https://bot.example.com
WEBHOOK_SECRET=قيمة_عشوائية_طويلة
ADMIN_USERNAME=admin
ADMIN_PASSWORD=كلمة_مرور_قوية
```

يمكن إنشاء الأسرار بالأمر:

```bash
openssl rand -hex 32
```

شغّل الخدمة:

```bash
docker compose up -d --build
```

## أوامر الإدارة

عرض الحالة:

```bash
docker compose ps
```

عرض السجلات:

```bash
docker compose logs -f --tail=200 bot
```

إعادة التشغيل:

```bash
docker compose restart
```

تحديث المشروع:

```bash
git pull
docker compose up -d --build
```

إيقاف الخدمة:

```bash
docker compose down
```

## المسارات

- الخدمة: `https://YOUR_DOMAIN/`
- الصحة: `https://YOUR_DOMAIN/health`
- لوحة الإدارة: `https://YOUR_DOMAIN/dashboard`

## إعدادات البيئة

```env
DOMAIN=bot.example.com
APP_MODE=webhook
BOT_TOKEN=
PUBLIC_BASE_URL=https://bot.example.com
WEBHOOK_SECRET=
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
DOWNLOAD_DIR=/app/downloads
MAX_FILE_MB=500
TELEGRAM_UPLOAD_LIMIT_MB=49
DOWNLOAD_LINK_TTL_SECONDS=3600
MAX_DURATION_SECONDS=7200
CONCURRENT_FRAGMENTS=4
COOKIES_FILE=
ALLOWED_DOMAINS=youtube.com,youtu.be,facebook.com,fb.watch,instagram.com
PORT=8000
```

لا ترفع `.env` أو ملفات Cookies أو التنزيلات إلى GitHub.

## النسخ الاحتياطي

البيانات الدائمة محفوظة في Docker volumes. لعرضها:

```bash
docker volume ls | grep moataz
```

## التحقق بعد النشر

```bash
curl -fsS https://YOUR_DOMAIN/health
```

ثم افتح البوت في Telegram وأرسل `/start` واختبر رابطًا عامًا قصيرًا.

## ملاحظات تشغيلية

- يجب أن يطابق `PUBLIC_BASE_URL` قيمة `https://DOMAIN`.
- لا تشغّل أكثر من نسخة من حاوية البوت لأن حالة المستخدم والمهام محفوظة داخل العملية الحالية.
- ملفات أكبر من حد رفع Telegram تُتاح عبر رابط مؤقت؛ لذلك يجب أن يبقى النطاق متاحًا عبر HTTPS.
- المقاطع الخاصة أو المقيدة قد تحتاج ملف Cookies صالحًا ومصرحًا باستخدامه.
