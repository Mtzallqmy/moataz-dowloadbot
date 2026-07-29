# Moataz Download Bot

بوت Telegram عربي لتحميل وتقطيع المقاطع العامة من YouTube وFacebook وInstagram، مصمم للعمل مباشرة داخل Termux الرسمي على Android ARM64 دون Debian أو Docker أو Rust.

> استخدم البوت فقط للمحتوى الذي تملكه أو لديك إذن قانوني لتنزيله، والتزم بحقوق النشر وشروط المنصات.

## البنية الخفيفة

- خادم ASGI مباشر يعمل عبر `uvicorn` العادي دون extras أو reload.
- عميل Telegram Bot API مباشر باستخدام مكتبة Python القياسية.
- لا يستخدم FastAPI أو Pydantic أو pydantic-core أو python-telegram-bot.
- الاعتماديات الخارجية الأساسية فقط: `uvicorn` و`yt-dlp`.
- المعالجة عبر FFmpeg المثبت من مستودعات Termux.

## تجربة التنزيل

1. اختر فيديو أو صوت.
2. أرسل الرابط، أو أرسل `الرابط | البداية | النهاية` للتقطيع.
3. يفحص البوت الرابط دون تنزيل ويعرض الصيغ المتاحة فعليًا.
4. اختر الصيغة من الأزرار، وعندها فقط يبدأ التنزيل.

يعرض البوت عنوان المقطع ومدته وعدد الصيغ، ويقسم القوائم الطويلة إلى صفحات.

## صيغ الفيديو

- صيغ مباشرة ⚡ عندما تكون الصورة والصوت داخل ملف واحد؛ وهي الأسرع والأخف على الهاتف لأنها لا تحتاج دمجًا.
- MP4 وWebM بحسب المتاح فعليًا.
- دقات من 144p و240p و360p و480p و720p و1080p و1440p حتى 2160p عند توفرها.
- صيغ مدمجة للصورة والصوت للحصول على جودة أعلى.
- خيار أفضل جودة متاحة للملفات الثقيلة.
- إظهار الحجم المتوقع للصيغ المباشرة عندما توفره المنصة.

## صيغ الصوت

- MP3: `48k` و`64k` و`96k` و`128k` و`160k` و`192k` و`256k` و`320k`.
- M4A الأصلي دون تحويل عند توفره.
- Opus/WebM الأصلي دون تحويل عند توفره.
- الصيغ الأصلية دون تحويل هي الأسرع لأنها تتجنب إعادة ترميز FFmpeg.

## الوظائف

- Webhook محمي بـ `WEBHOOK_SECRET` وترويسة Telegram السرية.
- فحص الصيغ قبل التحميل وعدم بدء العمل قبل اختيار المستخدم.
- تنفيذ فحص الصيغ والتنزيل في مهام خلفية حتى يرد Webhook بسرعة ولا يكرر Telegram الطلب.
- معالجة عربية لأخطاء 403 و429 والمقاطع الخاصة والمقيدة والصيغ المنتهية.
- تقطيع حر بصيغة `الرابط | البداية | النهاية`.
- قبول الثواني أو `MM:SS` أو `HH:MM:SS`.
- حد معالجة يصل إلى 500 MB.
- رفع الملفات الصغيرة مباشرة إلى Telegram بطريقة متدفقة.
- تسليم الملفات الأكبر من حد Telegram عبر رابط HTTPS مؤقت وآمن.
- تنزيل أجزاء HLS/DASH بالتوازي عبر `CONCURRENT_FRAGMENTS`.
- دعم Cookies اختياري للمقاطع المقيدة.
- تنظيف الملفات المؤقتة بعد الرفع أو انتهاء الرابط.
- لوحة إدارة محمية على `/dashboard` وفحص صحة على `/health`.

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

- `MAX_FILE_MB=500`: أقصى حجم للتنزيل والمعالجة.
- `TELEGRAM_UPLOAD_LIMIT_MB=49`: الملفات الأصغر تُرفع مباشرة، والأكبر تُسلّم برابط مؤقت.
- `DOWNLOAD_LINK_TTL_SECONDS=3600`: صلاحية رابط الملف الكبير.
- `CONCURRENT_FRAGMENTS=4`: تنزيل متوازٍ. يمكن تجربة `6` أو `8` على اتصال وهاتف قويين، لكن القيم الأعلى قد تسبب تقييدًا أو حرارة واستهلاكًا أكبر.
- اختر الصيغ المعلّمة `⚡ مباشر` أو الصوت الأصلي M4A/Opus للحصول على أعلى سرعة.
- الصيغ المدمجة والدقات العالية وMP3 تتطلب FFmpeg وقد تكون أبطأ.

## Cloudflare Tunnel

افتح جلسة Termux ثانية:

```bash
pkg install cloudflared -y
cloudflared tunnel --url http://127.0.0.1:8000
```

ضع الرابط الناتج في:

```env
PUBLIC_BASE_URL=https://your-tunnel.trycloudflare.com
```

ثم أعد تشغيل الخادم:

```bash
bash scripts/start-termux.sh
```

يجب إبقاء جلسة Uvicorn وجلسة Cloudflare Tunnel تعملان أثناء تنزيل الملفات الكبيرة.

## معالجة أخطاء YouTube

حدّث yt-dlp أولًا:

```bash
.venv/bin/python -m pip install -U yt-dlp
```

- `HTTP 403`: حدّث yt-dlp، ثم جرّب رابطًا عامًا أو Cookies صالحة.
- `HTTP 429`: انتظر قليلًا وخفّض عدد الطلبات المتكررة.
- «الصيغة لم تعد متاحة»: أرسل الرابط مجددًا ليعيد البوت جلب قائمة حديثة.
- المقاطع الخاصة أو المقيدة تحتاج حسابًا مخولًا وCookies صالحة.

لـCookies، ضع ملف Netscape مثل `cookies.txt` ثم:

```env
COOKIES_FILE=./cookies.txt
```

لا ترفع ملف Cookies إلى GitHub ولا تشاركه.

## الوضع المحلي

```env
APP_MODE=local
ADMIN_PASSWORD=ضع-كلمة-مرور
PORT=8000
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

تُكتب السجلات في `logs/app.log` مع تدوير تلقائي وإخفاء الأسرار.

## قيود معروفة

- Telegram Bot API السحابي لا يقبل رفع ملفات bot multipart أكبر من 50 MB؛ لذلك تستخدم الملفات الأكبر روابط HTTPS مؤقتة.
- Cloudflare Quick Tunnel رابط مؤقت يتغير عند إعادة تشغيله.
- روابط Facebook وInstagram الخاصة والمقاطع المحمية قد تحتاج Cookies.
- سرعة التنزيل النهائية تعتمد على المنصة والاتصال والهاتف والصيغة؛ الصيغ التي تحتاج دمجًا أو تحويلًا ستكون أبطأ من الصيغ المباشرة.
