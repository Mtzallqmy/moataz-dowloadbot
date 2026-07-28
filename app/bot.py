import html
import logging
from pathlib import Path

from app.downloader import DownloadRequest, cleanup_file, download_media, parse_time
from app.state import runtime_state
from app.telegram_api import TelegramClient

logger = logging.getLogger(__name__)
HELP_TEXT = "أرسل رابطًا من YouTube أو Facebook أو Instagram، ثم اختر الصيغة والجودة.\n\nللتقطيع: الرابط | البداية | النهاية\nمثال: https://youtu.be/example | 00:30 | 01:10"
USER_STATE: dict[int, dict[str, str]] = {}


def main_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "🎬 تحميل فيديو", "callback_data": "mode:video"}, {"text": "🎵 تحميل MP3", "callback_data": "mode:audio"}], [{"text": "✂️ شرح التقطيع", "callback_data": "help:cut"}, {"text": "ℹ️ المساعدة", "callback_data": "help:main"}]]}


def quality_keyboard() -> dict:
    return {"inline_keyboard": [[{"text": "360p", "callback_data": "quality:360"}, {"text": "480p", "callback_data": "quality:480"}], [{"text": "720p", "callback_data": "quality:720"}, {"text": "1080p", "callback_data": "quality:1080"}], [{"text": "أفضل جودة", "callback_data": "quality:best"}, {"text": "↩️ رجوع", "callback_data": "home"}]]}


def parse_user_request(text: str, state: dict[str, str] | None = None) -> DownloadRequest:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) not in {1, 3}:
        raise ValueError("أرسل الرابط فقط، أو الرابط | البداية | النهاية.")
    state = state or {}
    return DownloadRequest(url=parts[0], mode=state.get("mode", "video"), quality=state.get("quality", "best"), start=parse_time(parts[1]) if len(parts) == 3 else None, end=parse_time(parts[2]) if len(parts) == 3 else None)


async def handle_update(update: dict, client: TelegramClient) -> None:
    if callback := update.get("callback_query"):
        await client.answer_callback(callback["id"])
        message = callback.get("message", {})
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        state = USER_STATE.setdefault(chat_id, {})
        data = callback.get("data", "")
        if data == "home":
            state.clear(); await client.edit_message(chat_id, message_id, "اختر العملية:", main_keyboard())
        elif data == "help:main": await client.edit_message(chat_id, message_id, HELP_TEXT, main_keyboard())
        elif data == "help:cut": await client.edit_message(chat_id, message_id, "أرسل: الرابط | البداية | النهاية\nمثال: الرابط | 00:30 | 01:10", main_keyboard())
        elif data.startswith("mode:"):
            state["mode"] = data.split(":", 1)[1]
            await client.edit_message(chat_id, message_id, "أرسل الرابط، أو الرابط | البداية | النهاية." if state["mode"] == "audio" else "اختر جودة الفيديو:", None if state["mode"] == "audio" else quality_keyboard())
        elif data.startswith("quality:"):
            state["quality"] = data.split(":", 1)[1]; state.setdefault("mode", "video")
            await client.edit_message(chat_id, message_id, "أرسل الرابط، أو الرابط | البداية | النهاية للتقطيع.")
        return

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    if not text:
        return
    chat_id = message["chat"]["id"]
    if text.startswith("/start"):
        USER_STATE.pop(chat_id, None); await client.send_message(chat_id, "مرحبًا بك في بوت معتز لتحميل وتقطيع المقاطع. اختر العملية:", main_keyboard()); return
    if text.startswith("/help"):
        await client.send_message(chat_id, HELP_TEXT, main_keyboard()); return
    status = await client.send_message(chat_id, "⏳ جارٍ فحص الرابط وتجهيز الملف...")
    status_id = status["message_id"]
    runtime_state.start_job(); path: Path | None = None
    try:
        request = parse_user_request(text, USER_STATE.get(chat_id))
        path = await download_media(request)
        await client.edit_message(chat_id, status_id, "📤 اكتمل التجهيز، جارٍ الإرسال...")
        await client.send_file(chat_id, path, request.mode)
        runtime_state.finish_job(True)
        await client.delete_message(chat_id, status_id)
    except Exception as exc:
        logger.exception("فشلت مهمة التنزيل")
        runtime_state.finish_job(False, str(exc))
        await client.edit_message(chat_id, status_id, f"❌ تعذر تنفيذ الطلب:\n{html.escape(str(exc))[:900]}")
    finally:
        if path:
            cleanup_file(path)
