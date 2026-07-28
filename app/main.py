import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from telegram import Update

from app.bot import build_application
from app.config import settings
from app.state import runtime_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)
telegram_app = build_application()
security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    valid_user = secrets.compare_digest(credentials.username, settings.admin_username)
    valid_password = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (valid_user and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="بيانات الدخول غير صحيحة",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@asynccontextmanager
async def lifespan(_: FastAPI):
    await telegram_app.initialize()
    await telegram_app.start()
    webhook_url = f"{settings.public_base_url.rstrip('/')}/telegram/{settings.webhook_secret}"
    await telegram_app.bot.set_webhook(
        url=webhook_url,
        secret_token=settings.webhook_secret,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )
    logger.info("Webhook configured: %s", webhook_url)
    yield
    await telegram_app.stop()
    await telegram_app.shutdown()


app = FastAPI(title="Moataz Download Bot", version="1.0.0", lifespan=lifespan)


@app.get("/", response_class=JSONResponse)
async def root() -> dict:
    return {"service": "moataz-download-bot", "status": "running", "dashboard": "/dashboard"}


@app.get("/health", response_class=JSONResponse)
async def health() -> dict:
    me = await telegram_app.bot.get_me()
    return {
        "status": "ok",
        "telegram_bot": me.username,
        "time": datetime.now(timezone.utc).isoformat(),
        "stats": runtime_state.snapshot(),
    }


@app.post("/telegram/{path_secret}")
async def telegram_webhook(
    path_secret: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    valid_path = secrets.compare_digest(path_secret, settings.webhook_secret)
    valid_header = bool(x_telegram_bot_api_secret_token) and secrets.compare_digest(
        x_telegram_bot_api_secret_token, settings.webhook_secret
    )
    if not (valid_path and valid_header):
        raise HTTPException(status_code=403, detail="Forbidden")
    data = await request.json()
    update = Update.de_json(data=data, bot=telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(_: str = Depends(require_admin)) -> str:
    stats = runtime_state.snapshot()
    last_error = stats["last_error"] or "لا توجد أخطاء مسجلة"
    return f"""
<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>لوحة بوت معتز</title><style>
body{{font-family:system-ui;background:#0b1020;color:#eef2ff;margin:0;padding:24px}}.wrap{{max-width:980px;margin:auto}}
header,.card{{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.13);backdrop-filter:blur(16px);border-radius:20px;padding:22px;box-shadow:0 20px 60px rgba(0,0,0,.22)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:18px 0}}.num{{font-size:34px;font-weight:800}}small{{color:#a5b4fc}}code{{word-break:break-word;color:#fca5a5}}a{{color:#93c5fd}}
</style></head><body><div class='wrap'><header><h1>لوحة إدارة بوت معتز</h1><p>حالة الخدمة: تعمل ✅</p></header>
<div class='grid'><div class='card'><small>إجمالي الطلبات</small><div class='num'>{stats['total_jobs']}</div></div>
<div class='card'><small>الناجحة</small><div class='num'>{stats['successful_jobs']}</div></div>
<div class='card'><small>الفاشلة</small><div class='num'>{stats['failed_jobs']}</div></div>
<div class='card'><small>النشطة الآن</small><div class='num'>{stats['active_jobs']}</div></div></div>
<div class='card'><h3>آخر خطأ</h3><code>{last_error}</code><p><small>بدأت الخدمة: {stats['started_at']}</small></p><p><a href='/health'>فحص الصحة JSON</a></p></div>
</div></body></html>"""
