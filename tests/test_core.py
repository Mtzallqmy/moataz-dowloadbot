import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("APP_MODE", "webhook")
os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("PUBLIC_BASE_URL", "https://example.test/")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")

from app.bot import parse_user_request
from app.config import ConfigurationError, get_settings
from app.downloader import cleanup_file, parse_time, validate_url
from app.telegram_api import TelegramClient


class CoreTests(unittest.TestCase):
    def test_parse_time_formats(self):
        self.assertEqual(parse_time("90"), 90)
        self.assertEqual(parse_time("01:30"), 90)
        self.assertEqual(parse_time("01:02:03"), 3723)

    def test_parse_time_rejects_invalid_value(self):
        with self.assertRaises(ValueError):
            parse_time("99:99")

    def test_allowed_and_disallowed_domains(self):
        validate_url("https://www.youtube.com/watch?v=test")
        validate_url("https://sub.instagram.com/p/test")
        with self.assertRaises(ValueError):
            validate_url("https://example.com/video")
        with self.assertRaises(ValueError):
            validate_url("https://youtube.com.example.org/video")

    def test_settings_and_webhook_url(self):
        settings = get_settings(Path("/definitely/missing/.env"))
        self.assertEqual(settings.public_base_url, "https://example.test")
        self.assertEqual(settings.webhook_url, "https://example.test/telegram/test-secret")

    def test_missing_required_variable_has_arabic_error(self):
        env = {"APP_MODE": "webhook", "BOT_TOKEN": "x", "PUBLIC_BASE_URL": "https://example.test", "WEBHOOK_SECRET": "secret"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "ADMIN_PASSWORD"):
                get_settings(Path("/definitely/missing/.env"))

    def test_invalid_public_url(self):
        env = {"APP_MODE": "webhook", "BOT_TOKEN": "x", "PUBLIC_BASE_URL": "http://localhost:8000", "WEBHOOK_SECRET": "secret", "ADMIN_PASSWORD": "pass"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigurationError):
                get_settings(Path("/definitely/missing/.env"))

    def test_request_parsing(self):
        request = parse_user_request("https://youtu.be/test | 00:10 | 00:20", {"mode": "video", "quality": "720"})
        self.assertEqual((request.start, request.end, request.quality), (10, 20, "720"))

    def test_cleanup_file_removes_job_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            result = job / "video.mp4"
            result.write_bytes(b"data")
            cleanup_file(result)
            self.assertFalse(job.exists())

    def test_secret_is_redacted(self):
        client = TelegramClient("very-secret-token")
        self.assertNotIn("very-secret-token", client._safe_error("error very-secret-token"))


if __name__ == "__main__":
    unittest.main()
