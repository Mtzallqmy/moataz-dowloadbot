import pytest

from app.downloader import parse_time, validate_url


def test_parse_time_formats():
    assert parse_time("90") == 90
    assert parse_time("01:30") == 90
    assert parse_time("01:02:03") == 3723


def test_parse_time_rejects_invalid_value():
    with pytest.raises(ValueError):
        parse_time("99:99")


def test_allowed_url():
    validate_url("https://www.youtube.com/watch?v=test")


def test_disallowed_url():
    with pytest.raises(ValueError):
        validate_url("https://example.com/video")
