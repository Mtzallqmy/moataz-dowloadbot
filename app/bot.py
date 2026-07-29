import asyncio
import html
import logging
from pathlib import Path
from urllib.parse import quote

from app.config import settings
from app.downloader import DownloadRequest, MediaInfo, MediaOption, cleanup_file, download_media, inspect_media, parse_time
from app.file_delivery import delivery_registry
from app.state import runtime_state
from app.telegram_api import TelegramClient

logger = logging.getLogger(__name__)
HELP_TEXT = (
    "1) اختر فيديو أو صوت.\n"
    "2) أرسل الرابط، أو: الرابط | البداية | النهاية.\n"
    "3) سيعرض البوت الصيغ المتاحة فعليًا قبل التحميل.\n\n"
    "مثال: https://youtu.be/example | 00:30 | 01:10\n\n"
    "الفيديو: صيغ مباشرة سريعة وصيغ مدمجة عالية الجودة.\n"
    "الصوت: MP3 من 48k حتى 320k، إضافة إلى M4A وOpus الأصليين عند توفرهما."
)
USER_STATE: dict[int, dict] = {}
BACKGROUND_TASKS: set[asyncio.Task] = set()
OPTIONS_PER_PAGE = 8


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)


def main_keyboard() -> dict:
    return {"inline_keyboard": [
        [{"text": "🎬 فيديو", "callback_data": "mode:video"}, {"text": "🎵 صوت", "callback_data": "mode:audio"}],
        [{"text": "✂️ التقطيع", "callback_data": "help:cut"}, {"text": "ℹ️ المساعدة", "callback_data": "help:main"}],
    ]}


def _format_keyboard(options: tuple[MediaOption, ...], page: int = 0) -> dict:
    pages = max(1, (len(options) + OPTIONS_PER_PAGE - 1) // OPTIONS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    start = page * OPTIONS_PER_PAGE
    rows = [[{"text": option.label[:60], "callback_data": f"fmt:{option.key}"}] for option in options[start:start + OPTIONS_PER_PAGE]]
    nav = []
    if page > 0:
        nav.append({"text": "⬅️ السابق", "callback_data": f"page:{page - 1}"})
    nav.append({"text": f"{page + 1}/{pages}", "callback_data": "noop"})
    if page + 1 < pages:
        nav.append({"text": "التالي ➡️", "callback_data": f"page:{page + 1}"})
    rows.append(nav)
    rows.append([{"text": "🔄 رابط آخر", "callback_data": "retry"}, {"text": "🏠 الرئيسية", "callback_data": "home"}])
    return {"inline_keyboard": rows}


def _parse_input(text: str) -> tuple[str, int | None, int | None]:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) not in {1, 3}:
        raise ValueError("أرسل الرابط فقط، أو الرابط | البداية | النهاية.")
    return parts[0], parse_time(parts[1]) if len(parts) == 3 else None, parse_time(parts[2]) if len(parts) == 3 else None


def parse_user_request(text: str, state: dict | None = None) -> DownloadRequest:
    url, start, end = _parse_input(text)
    state = state or {}
    return DownloadRequest(url=url, mode=state.get("mode", "video"), start=start, end=end)


def _duration_text(seconds: int | None) -> str:
    if not seconds:
        return "غير معروفة"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


async def _deliver_result(client: TelegramClient, chat_id: int, path: Path, mode: str) -> bool:
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb <= settings.telegram_upload_limit_mb:
        await client.send_file(chat_id, path, mode)
        return True
    if settings.app_mode != "webhook" or not settings.public_base_url.startswith("https://"):
        raise RuntimeError(f"الملف {size_mb:.1f}MB أكبر من حد Telegram المباشر، ويلزم رابط HTTPS عام لتسليمه.")
    token = await delivery_registry.register(path, settings.download_link_ttl_seconds)
    url = f"{settings.public_base_url}/download/{quote(token)}"
    await client.send_message(chat_id, f"✅ الملف جاهز ({size_mb:.1f}MB).\nرابط مؤقت لمدة {settings.download_link_ttl_seconds // 60} دقيقة:\n{url}")
    return False


async def _inspect_and_show(client: TelegramClient, chat_id: int, message_id: int, text: str, mode: str) -> None:
    try:
        url, start, end = _parse_input(text)
        await client.edit_message(chat_id, message_id, "🔎 جارٍ قراءة الصيغ المتاحة من المنصة...")
        info = await inspect_media(url, mode)
        state = USER_STATE.setdefault(chat_id, {})
        state.update({"mode": mode, "url": url, "start": start, "end": end, "media_info": info, "options": {o.key: o for o in info.options}})
        await client.edit_message(
            chat_id,
            message_id,
            f"✅ {html.escape(info.title)}\n⏱ المدة: {_duration_text(info.duration)}\n📦 الصيغ المتاحة: {len(info.options)}\n\nاختر الصيغة لبدء التحميل:",
            _format_keyboard(info.options),
        )
    except Exception as exc:
        logger.exception("فشل فحص الصيغ")
        await client.edit_message(chat_id, message_id, f"❌ تعذر قراءة الصيغ:\n{html.escape(str(exc))[:900]}\n\nأرسل رابطًا آخر أو جرّب Cookies للمقاطع المقيدة.", main_keyboard())


async def _download_selected(client: TelegramClient, chat_id: int, message_id: int, option: MediaOption, state: dict) -> None:
    runtime_state.start_job()
    path: Path | None = None
    cleanup_now = True
    try:
        await client.edit_message(chat_id, message_id, f"⏳ بدأ التحميل:\n{option.label}\n\nقد تستغرق الصيغ المدمجة وقتًا أطول من الصيغ المباشرة ⚡")
        request = DownloadRequest(
            url=state["url"], mode=option.mode, format_selector=option.selector,
            output_ext=option.output_ext, audio_codec=option.audio_codec,
            audio_bitrate=option.audio_bitrate or "96", start=state.get("start"), end=state.get("end"),
        )
        path = await download_media(request)
        await client.edit_message(chat_id, message_id, "📤 اكتمل التحميل والمعالجة، جارٍ التسليم...")
        cleanup_now = await _deliver_result(client, chat_id, path, request.mode)
        runtime_state.finish_job(True)
        await client.edit_message(chat_id, message_id, "✅ تم تنفيذ الطلب بنجاح.", main_keyboard())
    except Exception as exc:
        logger.exception("فشلت مهمة التنزيل")
        runtime_state.finish_job(False, str(exc))
        await client.edit_message(chat_id, message_id, f"❌ تعذر تنفيذ الطلب:\n{html.escape(str(exc))[:900]}\n\nأرسل الرابط مجددًا لتحديث الصيغ، أو اختر صيغة مباشرة أخف.", main_keyboard())
    finally:
        if path and cleanup_now:
            cleanup_file(path)


async def handle_update(update: dict, client: TelegramClient) -> None:
    if callback := update.get("callback_query"):
        await client.answer_callback(callback["id"])
        message = callback.get("message", {})
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        state = USER_STATE.setdefault(chat_id, {})
        data = callback.get("data", "")
        if data == "noop":
            return
        if data == "home":
            state.clear()
            await client.edit_message(chat_id, message_id, "اختر نوع التنزيل:", main_keyboard())
        elif data == "help:main":
            await client.edit_message(chat_id, message_id, HELP_TEXT, main_keyboard())
        elif data == "help:cut":
            await client.edit_message(chat_id, message_id, "أرسل: الرابط | البداية | النهاية\nمثال: الرابط | 00:30 | 01:10", main_keyboard())
        elif data.startswith("mode:"):
            state.clear()
            state["mode"] = data.split(":", 1)[1]
            kind = "الصوت" if state["mode"] == "audio" else "الفيديو"
            await client.edit_message(chat_id, message_id, f"أرسل رابط {kind}. سأفحصه وأعرض جميع الصيغ المتاحة قبل التحميل.")
        elif data.startswith("page:"):
            info: MediaInfo | None = state.get("media_info")
            if info:
                await client.edit_message(chat_id, message_id, f"✅ {html.escape(info.title)}\nاختر الصيغة:", _format_keyboard(info.options, int(data.split(":", 1)[1])))
        elif data == "retry":
            state.pop("url", None); state.pop("options", None); state.pop("media_info", None)
            await client.edit_message(chat_id, message_id, "أرسل الرابط الجديد لفحص صيغه.")
        elif data.startswith("fmt:"):
            option = (state.get("options") or {}).get(data.split(":", 1)[1])
            if not option or not state.get("url"):
                await client.edit_message(chat_id, message_id, "انتهت صلاحية قائمة الصيغ. أرسل الرابط مجددًا.", main_keyboard())
            else:
                _spawn(_download_selected(client, chat_id, message_id, option, dict(state)))
        return

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    if not text:
        return
    chat_id = message["chat"]["id"]
    if text.startswith("/start"):
        USER_STATE.pop(chat_id, None)
        await client.send_message(chat_id, "مرحبًا بك. اختر فيديو أو صوت، ثم أرسل الرابط لعرض الصيغ المتاحة:", main_keyboard())
        return
    if text.startswith("/help"):
        await client.send_message(chat_id, HELP_TEXT, main_keyboard())
        return
    state = USER_STATE.setdefault(chat_id, {})
    mode = state.get("mode", "video")
    status = await client.send_message(chat_id, "🔎 استلمت الرابط، جارٍ جلب الصيغ المتاحة...")
    _spawn(_inspect_and_show(client, chat_id, status["message_id"], text, mode))
