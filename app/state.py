from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock


@dataclass
class RuntimeState:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_jobs: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    active_jobs: int = 0
    last_error: str | None = None
    lock: Lock = field(default_factory=Lock)

    def start_job(self) -> None:
        with self.lock:
            self.total_jobs += 1
            self.active_jobs += 1

    def finish_job(self, success: bool, error: str | None = None) -> None:
        with self.lock:
            self.active_jobs = max(0, self.active_jobs - 1)
            if success:
                self.successful_jobs += 1
            else:
                self.failed_jobs += 1
                self.last_error = error

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "started_at": self.started_at.isoformat(),
                "total_jobs": self.total_jobs,
                "successful_jobs": self.successful_jobs,
                "failed_jobs": self.failed_jobs,
                "active_jobs": self.active_jobs,
                "last_error": self.last_error,
            }


runtime_state = RuntimeState()
