import asyncio
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from app.config import settings

TIME_RE = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]?\d)$|^(\d+)$")


@dataclass(slots=True)
class DownloadRequest:
    url: str
    mode: str = "video"
    quality: str = "best"
    start: int | None = None
    end: int | None = None


def parse_time(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    match = TIME_RE.match(value)
    if not match:
        raise ValueError("صيغة الوقت غير صحيحة. استخدم HH:MM:SS أو MM:SS أو عدد الثواني.")
    if match.group(4):
        return int(match.group(4))
    return int(match.group(1) or 0) * 3600 + int(match.group(2)) * 60 + int(match.group(3))


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("الرابط يجب أن يبدأ بـ http أو https.")
    host = (parsed.hostname or "").lower()
    if not any(host == domain or host.endswith(f".{domain}") for domain in settings.domains):
        raise ValueError("هذا النطاق غير مدعوم حاليًا.")


def _download_sync(req: DownloadRequest) -> Path:
    validate_url(req.url)
    job_dir = settings.download_dir / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(job_dir / "%(title).120B-%(id)s.%(ext)s")

    if req.mode == "audio":
        fmt = "bestaudio/best"
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        formats = {
            "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
            "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "best": "bestvideo+bestaudio/best",
        }
        fmt = formats.get(req.quality, formats["best"])
        postprocessors = []

    opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": postprocessors,
        "max_filesize": settings.max_file_mb * 1024 * 1024,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }

    if req.start is not None or req.end is not None:
        start = req.start or 0
        end = req.end
        if end is not None and end <= start:
            raise ValueError("وقت النهاية يجب أن يكون بعد وقت البداية.")
        if end is not None and end - start > settings.max_duration_seconds:
            raise ValueError("مدة المقطع المطلوبة تتجاوز الحد المسموح.")
        opts["download_sections"] = f"*{start}-{'' if end is None else end}"
        opts["force_keyframes_at_cuts"] = True

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            duration = info.get("duration")
            if duration and duration > settings.max_duration_seconds and req.start is None and req.end is None:
                raise ValueError("مدة الفيديو تتجاوز الحد المسموح.")
        files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not files:
            raise RuntimeError("لم يتم إنشاء ملف صالح بعد التحميل.")
        result = max(files, key=lambda p: p.stat().st_mtime)
        if result.stat().st_size > settings.max_file_mb * 1024 * 1024:
            raise ValueError("حجم الملف أكبر من الحد المسموح للإرسال عبر البوت.")
        return result
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


async def download_media(req: DownloadRequest) -> Path:
    return await asyncio.to_thread(_download_sync, req)


def cleanup_file(path: Path) -> None:
    shutil.rmtree(path.parent, ignore_errors=True)
