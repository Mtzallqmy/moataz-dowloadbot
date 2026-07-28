import base64
import hmac
import json
import logging
import logging.handlers
from datetime import datetime, timezone

from app.bot import handle_update
from app.config import settings
from app.state import runtime_state
from app.telegram_api import TelegramClient

LOG_FILE = settings.log_dir / "app.log"
handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", handlers=[handler, logging.StreamHandler()])
logger = logging.getLogger(__name__)
client = TelegramClient(settings.bot_token) if settings.bot_token else None


def _json(status: int, payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return status, [(b"content-type", b"application/json; charset=utf-8")], body


def _html(status: int, body: str):
    return status, [(b"content-type", b"text/html; charset=utf-8")], body.encode("utf-8")


def _authorized(headers: dict[bytes, bytes]) -> bool:
    value = headers.get(b"authorization", b"").decode("latin1")
    if not value.startswith("Basic "):
        return False
    try:
        username, password = base64.b64decode(value[6:]).decode().split(":", 1)
    except Exception:
        return False
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(password, settings.admin_password)


def _dashboard() -> str:
    stats = runtime_state.snapshot()
    last_error = (stats["last_error"] or "لا توجد أخطاء مسجلة").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>لوحة بوت معتز</title><style>body{{font-family:system-ui;background:#0b1020;color:#eef2ff;margin:0;padding:24px}}.wrap{{max-width:980px;margin:auto}}header,.card{{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.13);border-radius:20px;padding:22px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:18px 0}}.num{{font-size:34px;font-weight:800}}small{{color:#a5b4fc}}code{{color:#fca5a5}}</style></head><body><div class='wrap'><header><h1>لوحة إدارة بوت معتز</h1><p>حالة الخدمة: تعمل ✅ — الوضع: {settings.app_mode}</p></header><div class='grid'><div class='card'>إجمالي الطلبات<div class='num'>{stats['total_jobs']}</div></div><div class='card'>الناجحة<div class='num'>{stats['successful_jobs']}</div></div><div class='card'>الفاشلة<div class='num'>{stats['failed_jobs']}</div></div><div class='card'>النشطة<div class='num'>{stats['active_jobs']}</div></div></div><div class='card'><h3>آخر خطأ</h3><code>{last_error}</code><p><small>بدأت الخدمة: {stats['started_at']}</small></p></div></div></body></html>"""


async def _receive_body(receive) -> bytes:
    chunks = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body"):
            return b"".join(chunks)


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    if settings.app_mode == "webhook":
                        if not client:
                            raise RuntimeError("BOT_TOKEN غير متوفر.")
                        await client.configure_webhook(settings.webhook_url, settings.webhook_secret)
                    else:
                        logger.info("وضع local مفعّل؛ لن يتم تسجيل Webhook")
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    logger.exception("فشل بدء التطبيق")
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
            elif message["type"] == "lifespan.shutdown":
                logger.info("تم إيقاف التطبيق بصورة منظمة")
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    method, path = scope["method"], scope["path"]
    headers = {k.lower(): v for k, v in scope.get("headers", [])}
    status, response_headers, body = _json(404, {"error": "المسار غير موجود"})
    if method == "GET" and path == "/":
        status, response_headers, body = _json(200, {"service": "moataz-download-bot", "status": "running", "mode": settings.app_mode, "dashboard": "/dashboard"})
    elif method == "GET" and path == "/health":
        status, response_headers, body = _json(200, {"status": "ok", "mode": settings.app_mode, "time": datetime.now(timezone.utc).isoformat(), "stats": runtime_state.snapshot()})
    elif method == "GET" and path == "/dashboard":
        if _authorized(headers):
            status, response_headers, body = _html(200, _dashboard())
        else:
            status, response_headers, body = _json(401, {"error": "بيانات لوحة الإدارة غير صحيحة"})
            response_headers.append((b"www-authenticate", b'Basic realm="Moataz Dashboard"'))
    elif method == "POST" and path == settings.webhook_path:
        secret = headers.get(b"x-telegram-bot-api-secret-token", b"").decode()
        if settings.app_mode != "webhook" or not hmac.compare_digest(secret, settings.webhook_secret):
            status, response_headers, body = _json(403, {"error": "Forbidden"})
        elif not client:
            status, response_headers, body = _json(503, {"error": "Telegram client unavailable"})
        else:
            try:
                update = json.loads((await _receive_body(receive)).decode("utf-8"))
                await handle_update(update, client)
                status, response_headers, body = _json(200, {"ok": True})
            except Exception:
                logger.exception("فشل معالجة تحديث Telegram")
                status, response_headers, body = _json(400, {"ok": False})
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})
