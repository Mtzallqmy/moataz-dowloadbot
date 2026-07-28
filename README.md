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
- صوت MP3 بخيارات 64k و96k و128k و192k.
- تقطيع حر: `الرابط | البداية | النهاية`.
- قبول الثواني أو `MM:SS` أو `HH:MM:SS`.
- حد معالجة يصل إلى 500 MB.
- رفع الملفات الصغيرة مباشرة إلى Telegram بطريقة متدفقة دون تحميل الملف كاملًا في الذاكرة.
- تسليم الملفات الأكبر من حد Telegram عبر رابط HTTPS مؤقت وآمن من خلال Cloudflare Tunnel.
- تنزيل أجزاء الفيديو المتعددة بالتوازي عبر `CONCURRENT_FRAGMENTS`.
- دعم ملف Cookies اختياري للمقاطع المقيدة أو التي تعيد HTTP 403.
- تنظيف الملفات المؤقتة بعد الرفع أو عند انتهاء رابط التنزيل.
- لوحة إدارة محمية بـ HTTP Basic Auth على `/dashboard`.
- فحص صحة على `/health` وإحصاءات تشغيل.

## التثبيت على Termux

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

## إعداد `.env`

```env
APP_MODE=webhook
BOT_TOKEN=
PUBLIC_BASE_URL=
WEBHOOK_SECRET=
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
DOWNLOAD_DIR=./downloads
MAX_FILE_MB=500
TELEGRAM_UPLOAD_LIMIT_MB=49
DOWNLOAD_LINK_TTL_SECONDS=3600
MAX_DURATION_SECONDS=7200
CONCURRENT_FRAGMENTS=4
COOKIES_FILE=
ALLOWED_DOMAINS=youtube.com,youtu.be,facebook.com,fb.watch,instagram.com
PORT=8000
```

### إعدادات الحجم والسرعة

- `MAX_FILE_MB=500`: أقصى حجم يسمح للبوت بتنزيله ومعالجته.
- `TELEGRAM_UPLOAD_LIMIT_MB=49`: الملفات الأصغر تُرفع مباشرة إلى Telegram. لا ترفع القيمة فوق 49 مع Bot API السحابي.
- الملفات الأكبر تُسلّم عبر رابط مؤقت من نفس `PUBLIC_BASE_URL`.
- `DOWNLOAD_LINK_TTL_SECONDS=3600`: صلاحية رابط الملف الكبير بالثواني.
- `CONCURRENT_FRAGMENTS=4`: تنزيل متوازٍ لأجزاء HLS/DASH. يمكن رفعه حتى 8 إذا كان الهاتف والاتصال مستقرين.
- الصوت الافتراضي الخفيف هو 96k، ويمكن اختيار 64k أو 128k أو 192k من أزرار البوت.

## Cloudflare Tunnel

افتح جلسة Termux ثانية:

```bash
pkg install cloudflared -y
cloudflared tunnel --url http://127.0.0.1:8000
```

انسخ رابط `https://...trycloudflare.com` وضعه في:

```env
PUBLIC_BASE_URL=https://your-tunnel.trycloudflare.com
```

ثم أعد تشغيل الخادم:

```bash
bash scripts/start-termux.sh
```

يجب إبقاء جلسة Uvicorn وجلسة Cloudflare Tunnel تعملان أثناء تنزيل الملفات الكبيرة من الرابط المؤقت.

## معالجة HTTP 403 من YouTube

ابدأ دائمًا بتحديث yt-dlp داخل البيئة الافتراضية:

```bash
.venv/bin/python -m pip install -U yt-dlp
```

المشروع يستخدم عدة عملاء YouTube وUser-Agent مناسبًا ويدعم استكمال التنزيل وإعادة المحاولة. بعض المقاطع المقيدة أو التي تطلب تسجيل الدخول تحتاج ملف Cookies.

أنشئ ملف Cookies بصيغة Netscape من متصفح موثوق، ثم ضعه داخل المشروع مثلًا:

```text
cookies.txt
```

وأضف إلى `.env`:

```env
COOKIES_FILE=./cookies.txt
```

لا ترفع ملف Cookies إلى GitHub ولا تشاركه مع أي شخص. استخدام Cookies الحساب قد يعرّض الحساب لتقييد مؤقت، لذلك استخدمها فقط عند الضرورة.

## الوضع المحلي

```env
APP_MODE=local
ADMIN_PASSWORD=ضع-كلمة-مرور
PORT=8000
```

ثم:

```bash
bash scripts/start-termux.sh
```

المسارات:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/dashboard`

## الفحص والاختبارات

```bash
python scripts/check-termux.py
.venv/bin/python -m unittest discover -s tests -v
```

## التشغيل المباشر

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

لا يستخدم المشروع `reload` أو `watchfiles` أو `uvloop` أو `httptools`.

## السجلات

تُكتب السجلات في `logs/app.log` مع تدوير تلقائي. لا تُطبع التوكنات، ولا يجب رفع `.env` أو Cookies أو ملفات التنزيل إلى GitHub.

## قيود معروفة

- Telegram Bot API السحابي لا يقبل رفع ملفات bot multipart أكبر من 50 MB، لذلك يستخدم المشروع روابط HTTPS مؤقتة للملفات الأكبر.
- Cloudflare Quick Tunnel رابط مؤقت يتغير عند إعادة تشغيله؛ للإنتاج استخدم Tunnel ثابتًا أو نطاقًا دائمًا.
- روابط Facebook وInstagram الخاصة والمقاطع المحمية قد تحتاج Cookies صالحة.
- بعض تغييرات YouTube قد تتطلب تحديث `yt-dlp` باستمرار.
