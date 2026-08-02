from datetime import date, datetime

import pytest

from utils.date import to_iso_date


def test_none_returns_none():
    assert to_iso_date(None) is None


def test_datetime_object():
    assert to_iso_date(datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02 03:04:05"


def test_date_object():
    assert to_iso_date(date(2024, 1, 2)) == "2024-01-02"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2024-01-02 03:04:05", "2024-01-02 03:04:05"),
        ("2024-01-02 03:04", "2024-01-02 03:04:00"),
        ("2024/01/02 03:04:05", "2024-01-02 03:04:05"),
        ("2024/01/02 03:04", "2024-01-02 03:04:00"),
        ("20240102030405", "2024-01-02 03:04:05"),
    ],
)
def test_datetime_string_formats(raw, expected):
    assert to_iso_date(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2024-01-02", "2024-01-02"),
        ("2024/01/02", "2024-01-02"),
        ("20240102", "2024-01-02"),
    ],
)
def test_date_only_string_formats(raw, expected):
    assert to_iso_date(raw) == expected


def test_iso_t_separator_and_timezone_offset_is_normalized():
    assert to_iso_date("2024-01-02T03:04:05+08:00") == "2024-01-02 03:04:05"


def test_fractional_seconds_are_stripped():
    assert to_iso_date("2024-01-02 03:04:05.123456") == "2024-01-02 03:04:05"


def test_empty_string_returns_none():
    assert to_iso_date("") is None
    assert to_iso_date("   ") is None


def test_unparseable_string_returns_none():
    assert to_iso_date("not-a-date") is None


def test_non_string_value_is_coerced_via_str():
    assert to_iso_date(20240102) == "2024-01-02"
