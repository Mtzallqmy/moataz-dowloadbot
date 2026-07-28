import asyncio
import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.config import settings

logger = logging.getLogger(__name__)
TIME_RE = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]?\d)$|^(\d+)$")
MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".ogg", ".opus", ".aac"}


@dataclass(slots=True)
class DownloadRequest:
    url: str
    mode: str = "video"
    quality: str = "best"
    audio_bitrate: str = "96"
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


def _format_for(req: DownloadRequest) -> tuple[str, list[dict]]:
    if req.mode == "audio":
        bitrate = req.audio_bitrate if req.audio_bitrate in {"64", "96", "128", "192"} else "96"
        return "bestaudio[ext=m4a]/bestaudio/best", [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate},
            {"key": "FFmpegMetadata", "add_metadata": True},
        ]

    formats = {
        "360": "best[ext=mp4][height<=360]/best[height<=360]/bestvideo[height<=360]+bestaudio/best",
        "480": "best[ext=mp4][height<=480]/best[height<=480]/bestvideo[height<=480]+bestaudio/best",
        "720": "best[ext=mp4][height<=720]/best[height<=720]/bestvideo[height<=720]+bestaudio/best",
        "1080": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best",
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best",
    }
    return formats.get(req.quality, formats["best"]), []


def _candidate_files(job_dir: Path) -> list[Path]:
    return [
        path
        for path in job_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in MEDIA_SUFFIXES
        and not path.name.endswith((".part", ".ytdl", ".temp"))
        and path.stat().st_size > 0
    ]


def _friendly_download_error(exc: Exception) -> RuntimeError:
    text = str(exc)
    lowered = text.lower()
    if "403" in lowered or "forbidden" in lowered:
        return RuntimeError(
            "رفضت المنصة طلب التحميل مؤقتًا (HTTP 403). حدّث yt-dlp، ثم جرّب مجددًا. "
            "للمقاطع المقيدة أضف ملف Cookies صالحًا عبر COOKIES_FILE."
        )
    if "sign in" in lowered or "cookies" in lowered or "age" in lowered:
        return RuntimeError("المقطع يحتاج تسجيل دخول أو Cookies. حدّد COOKIES_FILE في ملف .env.")
    if "requested format is not available" in lowered:
        return RuntimeError("الجودة المطلوبة غير متاحة لهذا المقطع. جرّب جودة أقل أو أفضل جودة.")
    return RuntimeError(f"فشل yt-dlp في تحميل المقطع: {text[-500:]}")


def _download_sync(req: DownloadRequest) -> Path:
    validate_url(req.url)
    job_dir = settings.download_dir / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(job_dir / "%(title).120B-%(id)s.%(ext)s")
    fmt, postprocessors = _format_for(req)

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
        "retries": 5,
        "fragment_retries": 10,
        "file_access_retries": 3,
        "concurrent_fragment_downloads": settings.concurrent_fragments,
        "continuedl": True,
        "overwrites": False,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        },
        "extractor_args": {"youtube": {"player_client": ["android_vr", "web_safari", "web"]}},
    }
    if settings.cookies_file:
        if not settings.cookies_file.is_file():
            shutil.rmtree(job_dir, ignore_errors=True)
            raise ValueError(f"ملف Cookies غير موجود: {settings.cookies_file}")
        opts["cookiefile"] = str(settings.cookies_file)

    if req.start is not None or req.end is not None:
        start = req.start or 0
        end = req.end
        if end is not None and end <= start:
            raise ValueError("وقت النهاية يجب أن يكون بعد وقت البداية.")
        if end is not None and end - start > settings.max_duration_seconds:
            raise ValueError("مدة المقطع المطلوبة تتجاوز الحد المسموح.")
        opts["download_sections"] = f"*{start}-{'' if end is None else end}"
        opts["force_keyframes_at_cuts"] = False

    logger.info("بدء مهمة تنزيل: mode=%s quality=%s", req.mode, req.quality)
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            duration = info.get("duration") if isinstance(info, dict) else None
            if duration and duration > settings.max_duration_seconds and req.start is None and req.end is None:
                raise ValueError("مدة الفيديو تتجاوز الحد المسموح.")

        files = _candidate_files(job_dir)
        if not files:
            raise RuntimeError("اكتمل yt-dlp دون إنشاء ملف وسائط صالح. حدّث yt-dlp أو جرّب جودة أخرى.")
        result = max(files, key=lambda p: (p.stat().st_size, p.stat().st_mtime))
        size_mb = result.stat().st_size / (1024 * 1024)
        if size_mb > settings.max_file_mb:
            raise ValueError(f"حجم الملف {size_mb:.1f} MB ويتجاوز الحد {settings.max_file_mb} MB.")
        logger.info("انتهت مهمة التنزيل بنجاح: size_mb=%.2f suffix=%s", size_mb, result.suffix)
        return result
    except DownloadError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise _friendly_download_error(exc) from exc
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


async def download_media(req: DownloadRequest) -> Path:
    return await asyncio.to_thread(_download_sync, req)


def cleanup_file(path: Path) -> None:
    shutil.rmtree(path.parent, ignore_errors=True)
