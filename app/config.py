import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent


class ConfigurationError(RuntimeError):
    pass


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for number, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ConfigurationError(f"السطر {number} في ملف .env غير صالح؛ استخدم KEY=VALUE.")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ConfigurationError(f"اسم المتغير في السطر {number} غير صالح.")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"متغير البيئة الإلزامي {name} غير موجود أو فارغ.")
    return value


def _positive_int(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"قيمة {name} يجب أن تكون رقمًا صحيحًا.") from exc
    if value < minimum or (maximum is not None and value > maximum):
        suffix = f" بين {minimum} و{maximum}" if maximum else f" أكبر من أو تساوي {minimum}"
        raise ConfigurationError(f"قيمة {name} يجب أن تكون{suffix}.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    public_base_url: str
    webhook_secret: str
    admin_username: str
    admin_password: str
    download_dir: Path
    log_dir: Path
    max_file_mb: int
    max_duration_seconds: int
    domains: frozenset[str]
    port: int
    app_mode: str

    @property
    def webhook_path(self) -> str:
        return f"/telegram/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url}{self.webhook_path}"


def get_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file)
    app_mode = os.getenv("APP_MODE", "webhook").strip().lower()
    if app_mode not in {"local", "webhook"}:
        raise ConfigurationError("APP_MODE يجب أن يكون local أو webhook.")

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "").strip()
    admin_password = _required("ADMIN_PASSWORD")

    if app_mode == "webhook":
        bot_token = _required("BOT_TOKEN")
        public_base_url = _required("PUBLIC_BASE_URL").rstrip("/")
        webhook_secret = _required("WEBHOOK_SECRET")
        parsed = urlparse(public_base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigurationError("PUBLIC_BASE_URL يجب أن يكون رابط HTTPS عامًا صالحًا.")
        if (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "0.0.0.0"}:
            raise ConfigurationError("PUBLIC_BASE_URL لا يقبل localhost في وضع webhook.")
    else:
        public_base_url = public_base_url or "http://127.0.0.1"
        webhook_secret = webhook_secret or "local-mode"

    raw_domains = os.getenv("ALLOWED_DOMAINS", "youtube.com,youtu.be,facebook.com,fb.watch,instagram.com")
    domains = frozenset(item.strip().lower() for item in raw_domains.split(",") if item.strip())
    if not domains:
        raise ConfigurationError("ALLOWED_DOMAINS لا يحتوي على أي نطاق صالح.")

    download_dir = Path(os.getenv("DOWNLOAD_DIR", "./downloads")).expanduser()
    if not download_dir.is_absolute():
        download_dir = (ROOT_DIR / download_dir).resolve()
    log_dir = (ROOT_DIR / "logs").resolve()
    download_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        bot_token=bot_token,
        public_base_url=public_base_url,
        webhook_secret=webhook_secret,
        admin_username=os.getenv("ADMIN_USERNAME", "admin").strip() or "admin",
        admin_password=admin_password,
        download_dir=download_dir,
        log_dir=log_dir,
        max_file_mb=_positive_int("MAX_FILE_MB", 45),
        max_duration_seconds=_positive_int("MAX_DURATION_SECONDS", 7200),
        domains=domains,
        port=_positive_int("PORT", 8000, 1, 65535),
        app_mode=app_mode,
    )


settings = get_settings()
