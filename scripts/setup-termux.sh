#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

pkg update -y
pkg upgrade -y
pkg install -y python git ffmpeg openssl libxml2 libxslt clang make pkg-config

python -m pip install --upgrade pip setuptools wheel
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p downloads logs
[ -f .env ] || cp .env.example .env

echo "تم تجهيز المشروع. عدّل ملف .env ثم شغّل: bash scripts/start-termux.sh"
