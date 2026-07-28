#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "ملف .env غير موجود. انسخه من .env.example وعدّله."; exit 1; }
source .venv/bin/activate
set -a
source .env
set +a

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
