"""Тесты нормализации заголовков и значений."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.services.catalog import get_sheet
from src.services.normalization import (
    build_search_text,
    clean_text,
    human_duration,
    normalize_header,
    parse_date,
    parse_duration,
    parse_filename_stamp,
    parse_number,
    resolve_headers,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Дата", "дата"),
        ("«Плохих» интерв., %", "плохих интерв %"),
        ("Битрейт, Мбит/с", "битрейт мбит с"),
        ("r_frame_rate", "r frame rate"),
        ("  FPS факт.  ", "fps факт"),
        ("Длительность", "длительность"),
    ],
)
def test_normalize_header(raw, expected):
    assert normalize_header(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6,55", 6.55),
        ("1 234,5", 1234.5),
        ("99,9%", 99.9),
        ("—", None),
        ("", None),
        (None, None),
        (7, 7.0),
        (3.5, 3.5),
    ],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


def test_parse_number_rejects_nan_and_broken_values():
    assert parse_number("n/a") is None
    assert parse_number("12abc") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("13.10.2026", date(2026, 10, 13)),
        ("13.10.26", date(2026, 10, 13)),
        ("2026-10-13", date(2026, 10, 13)),
        ("13.10.2026 12:22:28", date(2026, 10, 13)),
        (datetime(2026, 10, 13, 10, 0), date(2026, 10, 13)),
        ("", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_from_excel_serial():
    serial = (date(2026, 10, 13) - date(1899, 12, 30)).days
    assert parse_date(serial) == date(2026, 10, 13)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1м 14с", 74.0),
        ("01:14", 74.0),
        ("1:02:03", 3723.0),
        ("1ч 2м 3с", 3723.0),
        ("500 мс", 0.5),
        ("74", 74.0),
        (74, 74.0),
        ("—", None),
    ],
)
def test_parse_duration(raw, expected):
    assert parse_duration(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(74, "1м 14с"), (3723, "1ч 02м 03с"), (0, "0м 00с"), (None, None)],
)
def test_human_duration(seconds, expected):
    assert human_duration(seconds) == expected


def test_parse_filename_stamp():
    moment_date, moment = parse_filename_stamp("CameraRecord_20261012_122228.mp4")
    assert moment_date == date(2026, 10, 12)
    assert moment == datetime(2026, 10, 12, 12, 22, 28)


def test_resolve_headers_maps_aliases_and_detects_unknown():
    sheet = get_sheet("details")
    mapping, unknown = resolve_headers(sheet, ["Дата", "Эпизод", "FPS факт.", "Комментарий"])
    assert mapping == {0: "date", 1: "episode", 2: "fps"}
    assert list(unknown.values()) == ["Комментарий"]


def test_clean_text_and_search_text():
    assert clean_text("  Pico  ") == "Pico"
    assert clean_text("—") is None
    assert "pt_001" in build_search_text({"episode": "PT_001", "device": "Pico"})
