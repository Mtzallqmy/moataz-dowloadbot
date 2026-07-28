import html
import logging
from pathlib import Path
from urllib.parse import quote

from app.config import settings
from app.downloader import DownloadRequest, cleanup_file, download_media, parse_time
from app.file_delivery import delivery_registry
from app.state import runtime_state
from app.telegram_api import TelegramClient

logger = logging.getLogger(__name__)
HELP_TEXT = (
    "أرسل رابطًا من YouTube أو Facebook أو Instagram، ثم اختر الصيغة والجودة.\n\n"
    "للتقطيع: الرابط | البداية | النهاية\n"
    "مثال: https://youtu.be/example | 00:30 | 01:10\n\n"
    "الملفات الصغيرة تُرسل داخل Telegram، والكبيرة تُسلَّم عبر رابط HTTPS مؤقت وآمن."
)
USER_STATE: dict[int, dict[str, str]] = {}


def main_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🎬 تحميل فيديو", "callback_data": "mode:video"},
                {"text": "🎵 تحميل صوت", "callback_data": "mode:audio"},
            ],
            [
                {"text": "✂️ شرح التقطيع", "callback_data": "help:cut"},
                {"text": "ℹ️ المساعدة", "callback_data": "help:main"},
            ],
        ]
    }


def quality_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "360p خفيف", "callback_data": "quality:360"}, {"text": "480p", "callback_data": "quality:480"}],
            [{"text": "720p", "callback_data": "quality:720"}, {"text": "1080p", "callback_data": "quality:1080"}],
            [{"text": "أفضل جودة", "callback_data": "quality:best"}, {"text": "↩️ رجوع", "callback_data": "home"}],
        ]
    }


def audio_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "64k صغير جدًا", "callback_data": "audio:64"}, {"text": "96k خفيف", "callback_data": "audio:96"}],
            [{"text": "128k متوازن", "callback_data": "audio:128"}, {"text": "192k عالي", "callback_data": "audio:192"}],
            [{"text": "↩️ رجوع", "callback_data": "home"}],
        ]
    }


def parse_user_request(text: str, state: dict[str, str] | None = None) -> DownloadRequest:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) not in {1, 3}:
        raise ValueError("أرسل الرابط فقط، أو الرابط | البداية | النهاية.")
    state = state or {}
    return DownloadRequest(
        url=parts[0],
        mode=state.get("mode", "video"),
        quality=state.get("quality", "best"),
        audio_bitrate=state.get("audio_bitrate", "96"),
        start=parse_time(parts[1]) if len(parts) == 3 else None,
        end=parse_time(parts[2]) if len(parts) == 3 else None,
    )


async def _deliver_result(client: TelegramClient, chat_id: int, path: Path, mode: str) -> bool:
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb <= settings.telegram_upload_limit_mb:
        await client.send_file(chat_id, path, mode)
        return True

    if settings.app_mode != "webhook" or not settings.public_base_url.startswith("https://"):
        raise RuntimeError(
            f"حجم الملف {size_mb:.1f} MB أكبر من حد رفع Telegram المباشر. "
            "شغّل وضع webhook مع PUBLIC_BASE_URL عام لتسليمه عبر رابط مؤقت."
        )
    token = await delivery_registry.register(path, settings.download_link_ttl_seconds)
    url = f"{settings.public_base_url}/download/{quote(token)}"
    ttl_minutes = settings.download_link_ttl_seconds // 60
    await client.send_message(
        chat_id,
        f"✅ اكتمل تجهيز الملف ({size_mb:.1f} MB).\n"
        f"حمّله من الرابط المؤقت التالي خلال {ttl_minutes} دقيقة:\n{url}\n\n"
        "احتفظ بالبوت وCloudflare Tunnel يعملان حتى اكتمال التنزيل.",
    )
    return False


async def handle_update(update: dict, client: TelegramClient) -> None:
    if callback := update.get("callback_query"):
        await client.answer_callback(callback["id"])
        message = callback.get("message", {})
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        state = USER_STATE.setdefault(chat_id, {})
        data = callback.get("data", "")
        if data == "home":
            state.clear()
            await client.edit_message(chat_id, message_id, "اختر العملية:", main_keyboard())
        elif data == "help:main":
            await client.edit_message(chat_id, message_id, HELP_TEXT, main_keyboard())
        elif data == "help:cut":
            await client.edit_message(
                chat_id,
                message_id,
                "أرسل: الرابط | البداية | النهاية\nمثال: الرابط | 00:30 | 01:10",
                main_keyboard(),
            )
        elif data.startswith("mode:"):
            state["mode"] = data.split(":", 1)[1]
            if state["mode"] == "audio":
                await client.edit_message(chat_id, message_id, "اختر حجم وجودة الصوت:", audio_keyboard())
            else:
                await client.edit_message(chat_id, message_id, "اختر جودة الفيديو:", quality_keyboard())
        elif data.startswith("audio:"):
            state["audio_bitrate"] = data.split(":", 1)[1]
            state["mode"] = "audio"
            await client.edit_message(chat_id, message_id, "أرسل الرابط، أو الرابط | البداية | النهاية.")
        elif data.startswith("quality:"):
            state["quality"] = data.split(":", 1)[1]
            state.setdefault("mode", "video")
            await client.edit_message(chat_id, message_id, "أرسل الرابط، أو الرابط | البداية | النهاية للتقطيع.")
        return

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    if not text:
        return
    chat_id = message["chat"]["id"]
    if text.startswith("/start"):
        USER_STATE.pop(chat_id, None)
        await client.send_message(chat_id, "مرحبًا بك في بوت معتز لتحميل وتقطيع المقاطع. اختر العملية:", main_keyboard())
        return
    if text.startswith("/help"):
        await client.send_message(chat_id, HELP_TEXT, main_keyboard())
        return

    status = await client.send_message(chat_id, "⏳ جارٍ فحص الرابط وتجهيز الملف...")
    status_id = status["message_id"]
    runtime_state.start_job()
    path: Path | None = None
    cleanup_now = True
    try:
        request = parse_user_request(text, USER_STATE.get(chat_id))
        path = await download_media(request)
        await client.edit_message(chat_id, status_id, "📤 اكتمل التجهيز، جارٍ التسليم...")
        cleanup_now = await _deliver_result(client, chat_id, path, request.mode)
        runtime_state.finish_job(True)
        await client.delete_message(chat_id, status_id)
    except Exception as exc:
        logger.exception("فشلت مهمة التنزيل")
        runtime_state.finish_job(False, str(exc))
        safe_error = html.escape(str(exc))[:900]
        await client.edit_message(
            chat_id,
            status_id,
            f"❌ تعذر تنفيذ الطلب:\n{safe_error}\n\nجرّب جودة أقل، أو حدّث yt-dlp، أو استخدم Cookies للمقاطع المقيدة.",
        )
    finally:
        if path and cleanup_now:
            cleanup_file(path)
