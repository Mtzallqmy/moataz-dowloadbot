#!/usr/bin/env python3
import importlib
import importlib.util
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[bool, str]] = []


def check(name: str, func) -> None:
    try:
        detail = func()
        RESULTS.append((True, f"{name}: {detail or 'ناجح'}"))
    except Exception as exc:
        RESULTS.append((False, f"{name}: {exc}"))


def architecture():
    machine = platform.machine().lower()
    if machine not in {"aarch64", "arm64", "x86_64", "amd64"}:
        raise RuntimeError(f"معمارية غير مختبرة: {machine}")
    return machine


def python_version():
    version = sys.version_info
    if version < (3, 11):
        raise RuntimeError("يلزم Python 3.11 أو أحدث")
    return platform.python_version()


def command_version(command: str, args: list[str]):
    path = shutil.which(command)
    if not path:
        raise RuntimeError(f"الأمر {command} غير مثبت")
    result = subprocess.run([path, *args], capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "فشل التشغيل")
    return (result.stdout or result.stderr).splitlines()[0]


def imports():
    for module in ("uvicorn", "yt_dlp", "app.config", "app.downloader", "app.telegram_api", "app.bot", "app.main"):
        importlib.import_module(module)
    return "جميع المكتبات قابلة للاستيراد"


def forbidden_dependencies():
    forbidden = {"pydantic", "pydantic_core", "watchfiles", "uvloop", "httptools", "maturin"}
    installed = {name for name in forbidden if importlib.util.find_spec(name) is not None}
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    declared = {name for name in forbidden if name.replace("_", "-") in requirements or name in requirements}
    if declared:
        raise RuntimeError("اعتماديات ممنوعة في requirements: " + ", ".join(sorted(declared)))
    return "لا توجد اعتماديات ممنوعة مصرح بها" + (f"؛ توجد عالميًا فقط: {', '.join(sorted(installed))}" if installed else "")


def directories():
    from app.config import settings
    for path in (settings.download_dir, settings.log_dir):
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    return "مجلدا downloads وlogs صالحان للكتابة"


def environment():
    from app.config import settings
    return f"الإعدادات صالحة؛ APP_MODE={settings.app_mode}"


def port_available():
    from app.config import settings
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", settings.port))
    return f"المنفذ {settings.port} متاح"


def telegram_access():
    from app.config import settings
    if settings.app_mode == "local" or not settings.bot_token:
        return "تم التجاوز في الوضع المحلي"
    request = urllib.request.Request(f"https://api.telegram.org/bot{settings.bot_token}/getMe")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"تعذر الوصول إلى Telegram API: {exc.reason}") from exc
    return "Telegram API متاح والتوكن مقبول"


def internal_app():
    from app.main import app
    if not callable(app):
        raise RuntimeError("كائن ASGI غير قابل للتشغيل")
    return "تطبيق ASGI جاهز"


def main():
    setup_mode = "--setup" in sys.argv
    print("فحص توافق المشروع مع Termux\n")
    check("المعمارية", architecture)
    check("إصدار Python", python_version)
    check("FFmpeg", lambda: command_version("ffmpeg", ["-version"]))
    check("yt-dlp", lambda: command_version(sys.executable, ["-m", "yt_dlp", "--version"]))
    check("الاعتماديات الممنوعة", forbidden_dependencies)
    check("استيراد المكتبات", imports)
    check("الإعدادات", environment)
    check("المجلدات", directories)
    check("المنفذ", port_available)
    check("تطبيق ASGI", internal_app)
    if not setup_mode:
        check("Telegram API", telegram_access)
    for ok, message in RESULTS:
        print(("✅" if ok else "❌"), message)
    failed = [message for ok, message in RESULTS if not ok]
    print()
    if failed:
        print(f"❌ فشل {len(failed)} فحص/فحوص. أصلح الرسائل أعلاه ثم أعد المحاولة.")
        return 1
    print("✅ جميع فحوص Termux نجحت")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
