import asyncio
import json
import logging
import mimetypes
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)


class TelegramAPIError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, timeout: int = 60) -> None:
        self._token = token
        self._base = f"https://api.telegram.org/bot{token}"
        self.timeout = timeout

    def _safe_error(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def _request_sync(self, method: str, data: dict | None = None) -> dict:
        encoded = urllib.parse.urlencode(data or {}).encode()
        request = urllib.request.Request(f"{self._base}/{method}", data=encoded)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TelegramAPIError(self._safe_error(f"تعذر الاتصال بواجهة Telegram: {exc}")) from exc
        if not payload.get("ok"):
            raise TelegramAPIError(self._safe_error(str(payload.get("description", "Telegram API error"))))
        return payload["result"]

    async def request(self, method: str, data: dict | None = None) -> dict:
        return await asyncio.to_thread(self._request_sync, method, data)

    async def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
        data = {"chat_id": chat_id, "text": text}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        return await self.request("sendMessage", data)

    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup: dict | None = None) -> dict:
        data = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        return await self.request("editMessageText", data)

    async def answer_callback(self, callback_query_id: str) -> dict:
        return await self.request("answerCallbackQuery", {"callback_query_id": callback_query_id})

    async def delete_message(self, chat_id: int, message_id: int) -> dict:
        return await self.request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

    async def send_chat_action(self, chat_id: int, action: str) -> dict:
        return await self.request("sendChatAction", {"chat_id": chat_id, "action": action})

    def _multipart_sync(self, method: str, chat_id: int, path: Path, field: str, caption: str) -> dict:
        boundary = f"----moataz{secrets.token_hex(12)}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks = []
        for name, value in {"chat_id": str(chat_id), "caption": caption}.items():
            chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{path.name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode()
        )
        chunks.append(path.read_bytes())
        chunks.append(f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(
            f"{self._base}/{method}",
            data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=max(self.timeout, 180)) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise TelegramAPIError(self._safe_error(f"تعذر رفع الملف إلى Telegram: {exc}")) from exc
        if not payload.get("ok"):
            raise TelegramAPIError(self._safe_error(str(payload.get("description", "Telegram upload error"))))
        return payload["result"]

    async def send_file(self, chat_id: int, path: Path, mode: str) -> dict:
        if mode == "audio" and path.suffix.lower() == ".mp3":
            method, field = "sendAudio", "audio"
        elif mode == "video" and path.suffix.lower() in {".mp4", ".mkv", ".webm"}:
            method, field = "sendVideo", "video"
        else:
            method, field = "sendDocument", "document"
        return await asyncio.to_thread(self._multipart_sync, method, chat_id, path, field, "✅ تم التحميل بنجاح")

    async def configure_webhook(self, url: str, secret: str, retries: int = 3) -> None:
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                await self.request("deleteWebhook", {"drop_pending_updates": "false"})
                await self.request("setWebhook", {"url": url, "secret_token": secret, "allowed_updates": json.dumps(["message", "callback_query"])})
                logger.info("تم تسجيل Webhook بنجاح على Telegram")
                return
            except Exception as exc:
                last_error = exc
                logger.warning("فشلت محاولة تسجيل Webhook رقم %s من %s: %s", attempt, retries, self._safe_error(str(exc)))
                if attempt < retries:
                    await asyncio.sleep(attempt * 2)
        raise TelegramAPIError(f"فشل تسجيل Webhook بعد {retries} محاولات: {last_error}")
