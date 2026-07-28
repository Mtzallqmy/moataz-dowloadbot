# Moataz Download Bot

بوت Telegram عربي لتحميل وتقطيع المقاطع العامة من YouTube وFacebook وInstagram، مصمم للعمل مباشرة داخل Termux الرسمي على Android ARM64 دون Debian أو Docker أو Rust.

> استخدم البوت فقط للمحتوى الذي تملكه أو لديك إذن قانوني لتنزيله، والتزم بحقوق النشر وشروط المنصات.

## البنية الخفيفة

- خادم ASGI مباشر يعمل عبر `uvicorn` العادي دون extras أو reload.
- عميل Telegram Bot API مباشر باستخدام مكتبة Python القياسية.
- لا يستخدم FastAPI أو Pydantic أو pydantic-core أو python-telegram-bot.
- الاعتماديات الخارجية الأساسية فقط: `uvicorn` و`yt-dlp`.
- المعالجة عبر FFmpeg المثبت من مستودعات Termux.

## الوظائف

- Webhook محمي بـ `WEBHOOK_SECRET` وترويسة Telegram السرية.
- تنزيل فيديو بجودات 360p و480p و720p و1080p وأفضل جودة.
- استخراج MP3.
- تقطيع حر: `الرابط | البداية | النهاية`.
- قبول الثواني أو `MM:SS` أو `HH:MM:SS`.
- أزرار Telegram Inline.
- حد للحجم والمدة والنطاقات.
- تنظيف الملفات المؤقتة عند النجاح أو الفشل.
- لوحة إدارة محمية بـ HTTP Basic Auth على `/dashboard`.
- فحص صحة على `/health` وإحصاءات تشغيل.
- وضع محلي للاختبار دون تسجيل Webhook.

## التثبيت على Termux

استخدم نسخة Termux الرسمية الحديثة، ثم نفّذ:

```bash
pkg update -y
pkg install git -y
git clone https://github.com/Mtzallqmy/moataz-dowloadbot.git
cd moataz-dowloadbot
git checkout termux-compat
bash scripts/setup-termux.sh
nano .env
python scripts/check-termux.py
bash scripts/start-termux.sh
```

سكربت التجهيز يثبت فقط `python` و`git` و`ffmpeg` و`openssl`، وينشئ `.venv` ومجلدي `downloads` و`logs`، ولا يثبت Rust أو clang أو make ولا يرقّي pip أو setuptools أو wheel.

## إعداد `.env`

```env
APP_MODE=webhook
BOT_TOKEN=
PUBLIC_BASE_URL=
WEBHOOK_SECRET=
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
DOWNLOAD_DIR=./downloads
MAX_FILE_MB=45
MAX_DURATION_SECONDS=7200
ALLOWED_DOMAINS=youtube.com,youtu.be,facebook.com,fb.watch,instagram.com
PORT=8000
```

في وضع `webhook` يجب أن يبدأ `PUBLIC_BASE_URL` بـ `https://`، ولا يقبل `localhost`. تُحذف الشرطة المائلة النهائية تلقائيًا.

## Cloudflare Tunnel

بعد تشغيل الخادم، افتح جلسة Termux ثانية:

```bash
pkg install cloudflared -y
cloudflared tunnel --url http://127.0.0.1:8000
```

انسخ رابط `https://...trycloudflare.com` وضعه في:

```env
PUBLIC_BASE_URL=https://your-tunnel.trycloudflare.com
```

ثم أوقف الخادم بـ `Ctrl+C` وأعد تشغيله:

```bash
bash scripts/start-termux.sh
```

عند بدء التطبيق يحذف Webhook القديم ثم يسجل الرابط الجديد مع إعادة محاولة محدودة، دون طباعة التوكن في السجلات.

## الوضع المحلي

للتجربة دون Telegram Webhook:

```env
APP_MODE=local
ADMIN_PASSWORD=ضع-كلمة-مرور
PORT=8000
```

ثم:

```bash
bash scripts/start-termux.sh
```

المسارات المتاحة:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/dashboard`

## الفحص

```bash
python scripts/check-termux.py
```

يفحص المعمارية، Python، FFmpeg، yt-dlp، الاستيرادات، المجلدات، الإعدادات، المنفذ، Telegram API، وعدم وجود الاعتماديات المحظورة في `requirements.txt`.

## الاختبارات دون شبكة

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## التشغيل المباشر

الأمر الذي يستخدمه سكربت التشغيل:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

لا يستخدم المشروع `reload` أو `watchfiles` أو `uvloop` أو `httptools`.

## السجلات

تُكتب السجلات المنظمة في `logs/app.log` مع تدوير تلقائي، وتُخفى التوكنات من أخطاء Telegram. لا ترفع `.env` أو ملفات التنزيل إلى GitHub.

## قيود معروفة

- روابط Facebook وInstagram الخاصة أو المقيدة قد تحتاج Cookies، وهي غير مفعلة افتراضيًا لحماية الحسابات.
- حجم رفع Telegram للبوت يظل خاضعًا لحدود Telegram والخادم المستخدم.
- Cloudflare Quick Tunnel رابط مؤقت يتغير عند إعادة تشغيله؛ للإنتاج استخدم Tunnel ثابتًا أو نطاقًا دائمًا.
