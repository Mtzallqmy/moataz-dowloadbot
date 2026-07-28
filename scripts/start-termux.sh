#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

[ -x .venv/bin/python ] || { echo "❌ البيئة .venv غير موجودة. نفّذ: bash scripts/setup-termux.sh"; exit 1; }
[ -f .env ] || { echo "❌ ملف .env غير موجود. انسخه من .env.example ثم عدّله."; exit 1; }

PYTHON="$ROOT/.venv/bin/python"
PORT_VALUE="$($PYTHON -c 'from app.config import settings; print(settings.port)' 2>&1)" || { echo "❌ فشل تحميل الإعدادات: $PORT_VALUE"; exit 1; }
MODE_VALUE="$($PYTHON -c 'from app.config import settings; print(settings.app_mode)' 2>&1)" || { echo "❌ فشل التحقق من وضع التشغيل: $MODE_VALUE"; exit 1; }

echo "✅ الإعدادات صالحة"
echo "الوضع: $MODE_VALUE"
echo "الرابط المحلي: http://127.0.0.1:$PORT_VALUE"
echo "للإيقاف المنظم اضغط Ctrl+C"

trap 'echo; echo "تم طلب إيقاف الخادم..."' INT TERM
exec "$PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT_VALUE" --no-access-log
