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
AUDIO_BITRATES = (48, 64, 96, 128, 160, 192, 256, 320)


@dataclass(slots=True)
class DownloadRequest:
    url: str
    mode: str = "video"
    quality: str = "best"
    audio_bitrate: str = "96"
    audio_codec: str = "mp3"
    format_selector: str | None = None
    output_ext: str | None = None
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True, slots=True)
class MediaOption:
    key: str
    label: str
    mode: str
    selector: str
    output_ext: str
    audio_codec: str = ""
    audio_bitrate: str = ""


@dataclass(frozen=True, slots=True)
class MediaInfo:
    title: str
    duration: int | None
    options: tuple[MediaOption, ...]


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


def _base_options() -> dict:
    options = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 10,
        "file_access_retries": 3,
        "concurrent_fragment_downloads": settings.concurrent_fragments,
        "continuedl": True,
        "js_runtimes": {"deno": {}},
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        },
        "extractor_args": {
            "youtube": {"player_client": ["web", "web_safari", "android_vr"]},
        },
    }
    if settings.cookies_file:
        if not settings.cookies_file.is_file():
            raise ValueError(f"ملف Cookies غير موجود: {settings.cookies_file}")
        options["cookiefile"] = str(settings.cookies_file)
    return options


def _size_text(size: int | float | None) -> str:
    if not size:
        return "حجم غير معروف"
    mb = float(size) / (1024 * 1024)
    return f"{mb:.1f}MB" if mb < 100 else f"{mb:.0f}MB"


def _estimate_size(fmt: dict, duration: int | None) -> int | None:
    value = fmt.get("filesize") or fmt.get("filesize_approx")
    if value:
        return int(value)
    tbr = fmt.get("tbr")
    if tbr and duration:
        return int(float(tbr) * 1000 / 8 * duration)
    return None


def _build_video_options(formats: list[dict], duration: int | None) -> list[MediaOption]:
    progressive: dict[tuple[int, str], tuple[dict, int | None]] = {}
    heights: set[int] = set()
    for fmt in formats:
        if fmt.get("vcodec") in {None, "none"}:
            continue
        height = int(fmt.get("height") or 0)
        if not height:
            continue
        heights.add(height)
        ext = str(fmt.get("ext") or "mp4").lower()
        if fmt.get("acodec") not in {None, "none"}:
            size = _estimate_size(fmt, duration)
            key = (height, ext)
            current = progressive.get(key)
            if current is None or (size or 10**18) < (current[1] or 10**18):
                progressive[key] = (fmt, size)

    options: list[MediaOption] = []
    for (height, ext), (fmt, size) in sorted(progressive.items(), key=lambda item: (item[0][0], item[0][1])):
        if ext not in {"mp4", "webm"}:
            continue
        fid = str(fmt.get("format_id"))
        options.append(MediaOption(
            key=f"vd{len(options)}",
            label=f"⚡ {height}p {ext.upper()} مباشر • {_size_text(size)}",
            mode="video",
            selector=fid,
            output_ext=ext,
        ))

    common_heights = sorted({h for h in heights if h in {144, 240, 360, 480, 720, 1080, 1440, 2160}})
    if not common_heights:
        common_heights = sorted(heights)[-8:]
    for height in common_heights:
        selector = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        )
        options.append(MediaOption(
            key=f"vm{len(options)}",
            label=f"🎬 {height}p MP4 مدمج • جودة كاملة",
            mode="video",
            selector=selector,
            output_ext="mp4",
        ))
    options.append(MediaOption(
        key="vbest",
        label="🏆 أفضل جودة متاحة • ثقيل",
        mode="video",
        selector="bestvideo+bestaudio/best",
        output_ext="mp4",
    ))
    return options[:30]


def _build_audio_options(formats: list[dict], duration: int | None) -> list[MediaOption]:
    options: list[MediaOption] = []
    for bitrate in AUDIO_BITRATES:
        options.append(MediaOption(
            key=f"mp3{bitrate}",
            label=f"🎵 MP3 {bitrate}k" + (" • صغير جدًا" if bitrate <= 64 else " • خفيف" if bitrate <= 96 else " • متوازن" if bitrate <= 160 else " • عالي"),
            mode="audio",
            selector="bestaudio[ext=m4a]/bestaudio/best",
            output_ext="mp3",
            audio_codec="mp3",
            audio_bitrate=str(bitrate),
        ))

    source_by_ext: dict[str, tuple[dict, int | None]] = {}
    for fmt in formats:
        if fmt.get("vcodec") not in {None, "none"} or fmt.get("acodec") in {None, "none"}:
            continue
        ext = str(fmt.get("ext") or "").lower()
        if ext not in {"m4a", "opus", "webm", "aac"}:
            continue
        size = _estimate_size(fmt, duration)
        current = source_by_ext.get(ext)
        abr = float(fmt.get("abr") or fmt.get("tbr") or 0)
        if current is None or abr > float(current[0].get("abr") or current[0].get("tbr") or 0):
            source_by_ext[ext] = (fmt, size)
    for ext, (fmt, size) in source_by_ext.items():
        label_ext = "OPUS" if ext in {"opus", "webm"} else ext.upper()
        options.append(MediaOption(
            key=f"as{len(options)}",
            label=f"⚡ {label_ext} أصلي بلا تحويل • {_size_text(size)}",
            mode="audio",
            selector=str(fmt.get("format_id")),
            output_ext="opus" if ext == "webm" else ext,
        ))
    return options[:20]


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _friendly_download_error(exc: Exception) -> RuntimeError:
    text = re.sub(r"\s+", " ", str(exc)).strip()
    lowered = text.lower()
    logger.warning("yt-dlp error: %s", text[-1200:])

    if _contains_any(lowered, ("http error 429", "status code 429", "too many requests")):
        return RuntimeError("المنصة قيّدت عنوان IP الخاص بالخادم مؤقتًا (HTTP 429). انتظر أو استخدم خادمًا/عنوان IP آخر.")
    if _contains_any(lowered, ("http error 403", "status code 403", "403 forbidden")):
        return RuntimeError("رفضت المنصة الطلب من الخادم (HTTP 403). حدّث الحاوية أولًا، وقد يكون عنوان IP السحابي مقيّدًا.")
    if _contains_any(lowered, ("private video", "this video is private", "private account")):
        return RuntimeError("هذا المقطع أو الحساب خاص ولا يمكن الوصول إليه دون حساب مخوّل.")
    if _contains_any(lowered, (
        "sign in to confirm your age",
        "age-restricted",
        "age restricted",
        "login required",
        "authentication required",
        "use --cookies",
        "use --cookies-from-browser",
        "cookies are required",
        "this video is only available to registered users",
        "members-only",
    )):
        return RuntimeError("هذا المحتوى نفسه يتطلب تسجيل دخول. أضف Cookies صالحة فقط لهذا النوع من المقاطع.")
    if _contains_any(lowered, (
        "javascript runtime",
        "no supported javascript runtime",
        "external javascript",
        "challenge solver",
        "signature solving failed",
        "nsig extraction failed",
        "requested format is not available",
        "only images are available",
    )):
        return RuntimeError("تعذر حل حماية JavaScript أو استخراج صيغ الفيديو. أعد بناء الحاوية لتثبيت Deno وملحقات yt-dlp الحديثة.")
    if _contains_any(lowered, ("unsupported url", "url could not be parsed")):
        return RuntimeError("الرابط غير مدعوم أو غير مكتمل.")
    if _contains_any(lowered, ("unable to download webpage", "failed to resolve", "name or service not known", "network is unreachable", "timed out", "timeout")):
        return RuntimeError("تعذر اتصال الخادم بالمنصة. تحقق من DNS والاتصال الخارجي وسجلات الحاوية.")
    if "requested format is not available" in lowered:
        return RuntimeError("الصيغة المختارة لم تعد متاحة. أرسل الرابط مجددًا لتحديث قائمة الصيغ.")
    return RuntimeError(f"فشل yt-dlp: {text[-700:]}")


def _inspect_sync(url: str, mode: str) -> MediaInfo:
    validate_url(url)
    opts = _base_options()
    opts["skip_download"] = True
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise _friendly_download_error(exc) from exc
    if not isinstance(info, dict):
        raise RuntimeError("تعذر قراءة معلومات المقطع.")
    if info.get("entries"):
        info = next((entry for entry in info["entries"] if entry), info)
    title = str(info.get("title") or "مقطع بلا عنوان")[:180]
    duration = int(info.get("duration")) if info.get("duration") else None
    formats = list(info.get("formats") or [])
    options = _build_audio_options(formats, duration) if mode == "audio" else _build_video_options(formats, duration)
    if not options:
        raise RuntimeError("لم تعثر المنصة على صيغ قابلة للتنزيل لهذا الرابط.")
    return MediaInfo(title=title, duration=duration, options=tuple(options))


async def inspect_media(url: str, mode: str) -> MediaInfo:
    return await asyncio.to_thread(_inspect_sync, url, mode)


def _candidate_files(job_dir: Path) -> list[Path]:
    return [p for p in job_dir.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES and not p.name.endswith((".part", ".ytdl", ".temp")) and p.stat().st_size > 0]


def _download_sync(req: DownloadRequest) -> Path:
    validate_url(req.url)
    job_dir = settings.download_dir / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    selector = req.format_selector or ("bestaudio/best" if req.mode == "audio" else "bestvideo+bestaudio/best")
    postprocessors: list[dict] = []
    if req.mode == "audio" and req.audio_codec == "mp3":
        bitrate = req.audio_bitrate if req.audio_bitrate in {str(v) for v in AUDIO_BITRATES} else "96"
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate}, {"key": "FFmpegMetadata", "add_metadata": True}]

    opts = _base_options()
    opts.update({
        "format": selector,
        "outtmpl": str(job_dir / "%(title).120B-%(id)s.%(ext)s"),
        "merge_output_format": req.output_ext if req.output_ext in {"mp4", "mkv", "webm"} else "mp4",
        "restrictfilenames": True,
        "postprocessors": postprocessors,
        "max_filesize": settings.max_file_mb * 1024 * 1024,
        "overwrites": False,
    })
    if req.start is not None or req.end is not None:
        start = req.start or 0
        if req.end is not None and req.end <= start:
            raise ValueError("وقت النهاية يجب أن يكون بعد وقت البداية.")
        if req.end is not None and req.end - start > settings.max_duration_seconds:
            raise ValueError("مدة المقطع المطلوبة تتجاوز الحد المسموح.")
        opts["download_sections"] = f"*{start}-{'' if req.end is None else req.end}"
        opts["force_keyframes_at_cuts"] = False

    logger.info("بدء تنزيل: mode=%s selector=%s", req.mode, selector[:100])
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(req.url, download=True)
            duration = info.get("duration") if isinstance(info, dict) else None
            if duration and duration > settings.max_duration_seconds and req.start is None and req.end is None:
                raise ValueError("مدة الفيديو تتجاوز الحد المسموح.")
        files = _candidate_files(job_dir)
        if not files:
            raise RuntimeError("اكتمل yt-dlp دون إنشاء ملف صالح. أرسل الرابط مجددًا واختر صيغة أخرى.")
        result = max(files, key=lambda p: (p.stat().st_size, p.stat().st_mtime))
        size_mb = result.stat().st_size / (1024 * 1024)
        if size_mb > settings.max_file_mb:
            raise ValueError(f"حجم الملف {size_mb:.1f} MB ويتجاوز الحد {settings.max_file_mb} MB.")
        logger.info("اكتمل التنزيل: size_mb=%.2f ext=%s", size_mb, result.suffix)
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
