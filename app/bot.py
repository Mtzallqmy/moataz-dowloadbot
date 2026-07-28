import html
import logging
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import settings
from app.downloader import DownloadRequest, cleanup_file, download_media, parse_time
from app.state import runtime_state

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "أرسل رابطًا من YouTube أو Facebook أو Instagram، ثم اختر الصيغة والجودة.\n\n"
    "للتقطيع الحر أرسل الرابط بهذه الصيغة:\n"
    "الرابط | البداية | النهاية\n"
    "مثال: https://youtu.be/example | 00:30 | 01:10\n\n"
    "يمكن استخدام عدد الثواني أو MM:SS أو HH:MM:SS. حمّل فقط المحتوى الذي تملك حق تنزيله."
)


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 تحميل فيديو", callback_data="mode:video"), InlineKeyboardButton("🎵 تحميل MP3", callback_data="mode:audio")],
        [InlineKeyboardButton("✂️ شرح التقطيع", callback_data="help:cut"), InlineKeyboardButton("ℹ️ المساعدة", callback_data="help:main")],
    ])


def quality_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("360p", callback_data="quality:360"), InlineKeyboardButton("480p", callback_data="quality:480")],
        [InlineKeyboardButton("720p", callback_data="quality:720"), InlineKeyboardButton("1080p", callback_data="quality:1080")],
        [InlineKeyboardButton("أفضل جودة", callback_data="quality:best"), InlineKeyboardButton("↩️ رجوع", callback_data="home")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.effective_message.reply_text("مرحبًا بك في بوت معتز لتحميل وتقطيع المقاطع. اختر العملية:", reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(HELP_TEXT, reply_markup=main_keyboard())


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data == "home":
        context.user_data.clear()
        await query.edit_message_text("اختر العملية:", reply_markup=main_keyboard())
    elif data == "help:main":
        await query.edit_message_text(HELP_TEXT, reply_markup=main_keyboard())
    elif data == "help:cut":
        await query.edit_message_text("أرسل: الرابط | البداية | النهاية\nمثال: الرابط | 00:30 | 01:10", reply_markup=main_keyboard())
    elif data.startswith("mode:"):
        mode = data.split(":", 1)[1]
        context.user_data["mode"] = mode
        if mode == "audio":
            await query.edit_message_text("أرسل الرابط، أو الرابط | البداية | النهاية لتحميل MP3 مقصوص.")
        else:
            await query.edit_message_text("اختر جودة الفيديو:", reply_markup=quality_keyboard())
    elif data.startswith("quality:"):
        context.user_data["quality"] = data.split(":", 1)[1]
        context.user_data.setdefault("mode", "video")
        await query.edit_message_text("أرسل الرابط، أو الرابط | البداية | النهاية للتقطيع.")


def parse_user_request(text: str, context: ContextTypes.DEFAULT_TYPE) -> DownloadRequest:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) not in {1, 3}:
        raise ValueError("أرسل الرابط فقط، أو الرابط | البداية | النهاية.")
    start = parse_time(parts[1]) if len(parts) == 3 else None
    end = parse_time(parts[2]) if len(parts) == 3 else None
    return DownloadRequest(
        url=parts[0],
        mode=context.user_data.get("mode", "video"),
        quality=context.user_data.get("quality", "best"),
        start=start,
        end=end,
    )


async def send_result(update: Update, path: Path, mode: str) -> None:
    await update.effective_chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    with path.open("rb") as media:
        if mode == "audio" and path.suffix.lower() == ".mp3":
            await update.effective_message.reply_audio(audio=media, caption="✅ تم التحميل بنجاح")
        elif mode == "video" and path.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            await update.effective_message.reply_video(video=media, caption="✅ تم التحميل بنجاح", supports_streaming=True)
        else:
            await update.effective_message.reply_document(document=media, caption="✅ تم التحميل بنجاح")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return
    status = await message.reply_text("⏳ جارٍ فحص الرابط وتجهيز الملف...")
    runtime_state.start_job()
    path: Path | None = None
    try:
        request = parse_user_request(message.text, context)
        path = await download_media(request)
        await status.edit_text("📤 اكتمل التجهيز، جارٍ الإرسال...")
        await send_result(update, path, request.mode)
        runtime_state.finish_job(True)
        await status.delete()
    except Exception as exc:
        logger.exception("Download job failed")
        runtime_state.finish_job(False, str(exc))
        safe_error = html.escape(str(exc))[:900]
        await status.edit_text(f"❌ تعذر تنفيذ الطلب:\n{safe_error}\n\nجرّب رابطًا عامًا أو جودة أقل.")
    finally:
        if path:
            cleanup_file(path)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram error", exc_info=context.error)


def build_application() -> Application:
    app = Application.builder().token(settings.bot_token).updater(None).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(error_handler)
    return app
