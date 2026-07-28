from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    public_base_url: str
    webhook_secret: str
    admin_username: str = "admin"
    admin_password: str
    download_dir: Path = Path("./downloads")
    max_file_mb: int = 45
    max_duration_seconds: int = 7200
    allowed_domains: str = "youtube.com,youtu.be,facebook.com,fb.watch,instagram.com"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def domains(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_domains.split(",") if item.strip()}


settings = Settings()
settings.download_dir.mkdir(parents=True, exist_ok=True)
