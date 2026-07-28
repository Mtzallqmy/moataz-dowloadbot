#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
trap 'echo "❌ فشل تجهيز المشروع عند السطر $LINENO. راجع الرسالة السابقة لتحديد المرحلة أو الحزمة."' ERR

echo "[1/7] تحديث فهرس حزم Termux"
pkg update -y

echo "[2/7] تثبيت الحزم الضرورية"
pkg install -y python git ffmpeg openssl

echo "[3/7] إنشاء البيئة الافتراضية"
[ -d .venv ] || python -m venv .venv
PYTHON="$ROOT/.venv/bin/python"

echo "[4/7] تثبيت اعتماديات Python الخفيفة"
"$PYTHON" -m pip install -r requirements.txt

echo "[5/7] إنشاء المجلدات وملف البيئة"
mkdir -p downloads logs
[ -f .env ] || cp .env.example .env

echo "[6/7] عرض الإصدارات"
python --version
ffmpeg -version | head -n 1

echo "[7/7] تشغيل الفحص الداخلي"
APP_MODE=local ADMIN_PASSWORD=setup-check "$PYTHON" scripts/check-termux.py --setup

echo "✅ تم تجهيز المشروع بنجاح"
echo "عدّل .env ثم نفّذ: python scripts/check-termux.py && bash scripts/start-termux.sh"
