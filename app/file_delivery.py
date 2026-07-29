import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from app.downloader import cleanup_file

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DeliveryEntry:
    path: Path
    expires_at: float


class DeliveryRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, DeliveryEntry] = {}
        self._lock = asyncio.Lock()

    async def register(self, path: Path, ttl_seconds: int) -> str:
        token = secrets.token_urlsafe(32)
        async with self._lock:
            self._purge_expired_locked()
            self._entries[token] = DeliveryEntry(path=path, expires_at=time.time() + ttl_seconds)
        asyncio.create_task(self._expire_later(token, ttl_seconds))
        return token

    async def resolve(self, token: str) -> Path | None:
        async with self._lock:
            self._purge_expired_locked()
            entry = self._entries.get(token)
            if not entry or not entry.path.is_file():
                return None
            return entry.path

    async def consume(self, token: str) -> None:
        async with self._lock:
            entry = self._entries.pop(token, None)
        if entry:
            cleanup_file(entry.path)

    async def _expire_later(self, token: str, ttl_seconds: int) -> None:
        await asyncio.sleep(ttl_seconds)
        await self.consume(token)

    def _purge_expired_locked(self) -> None:
        now = time.time()
        expired = [token for token, entry in self._entries.items() if entry.expires_at <= now]
        for token in expired:
            entry = self._entries.pop(token)
            cleanup_file(entry.path)
            logger.info("تم تنظيف ملف تنزيل مؤقت منتهي الصلاحية")


delivery_registry = DeliveryRegistry()
