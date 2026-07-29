import asyncio
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
os.environ.setdefault("MAX_FILE_MB", "500")

from app.bot import _format_keyboard, parse_user_request
from app.config import ConfigurationError, get_settings
from app.downloader import _build_audio_options, _build_video_options, cleanup_file, parse_time, validate_url
from app.file_delivery import DeliveryRegistry
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
        self.assertEqual(settings.max_file_mb, 500)
        self.assertLessEqual(settings.telegram_upload_limit_mb, 49)

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
        request = parse_user_request("https://youtu.be/test | 00:10 | 00:20", {"mode": "video"})
        self.assertEqual((request.start, request.end, request.mode), (10, 20, "video"))

    def test_dynamic_audio_profiles_include_light_and_heavy(self):
        formats = [{"format_id": "a1", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "abr": 128, "filesize": 1_000_000}]
        options = _build_audio_options(formats, 120)
        labels = " ".join(option.label for option in options)
        self.assertIn("MP3 48k", labels)
        self.assertIn("MP3 320k", labels)
        self.assertIn("M4A", labels)

    def test_dynamic_video_profiles_include_direct_and_merged(self):
        formats = [
            {"format_id": "v1", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 360, "filesize": 2_000_000},
            {"format_id": "v2", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 720, "filesize": 5_000_000},
        ]
        options = _build_video_options(formats, 120)
        labels = " ".join(option.label for option in options)
        self.assertIn("360p", labels)
        self.assertIn("720p", labels)
        self.assertIn("أفضل جودة", labels)

    def test_format_keyboard_callback_data_is_small(self):
        options = tuple(_build_audio_options([], 60))
        keyboard = _format_keyboard(options)
        callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
        self.assertTrue(all(len(value.encode()) <= 64 for value in callbacks))

    def test_cleanup_file_removes_job_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            job.mkdir()
            result = job / "video.mp4"
            result.write_bytes(b"data")
            cleanup_file(result)
            self.assertFalse(job.exists())

    def test_temporary_delivery_registry(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                job = Path(tmp) / "job"
                job.mkdir()
                result = job / "video.mp4"
                result.write_bytes(b"data")
                registry = DeliveryRegistry()
                token = await registry.register(result, 300)
                self.assertEqual(await registry.resolve(token), result)
                await registry.consume(token)
                self.assertIsNone(await registry.resolve(token))
                self.assertFalse(job.exists())
        asyncio.run(scenario())

    def test_secret_is_redacted(self):
        client = TelegramClient("very-secret-token")
        self.assertNotIn("very-secret-token", client._safe_error("error very-secret-token"))


if __name__ == "__main__":
    unittest.main()
