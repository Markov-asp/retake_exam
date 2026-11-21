"""Тесты парсера Excel-отчётов."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from src.services.parser import detect_sheet_key, parse_workbook
from src.utils.errors import ValidationError
from tests.conftest import build_report


def test_detect_sheet_key():
    assert detect_sheet_key("Детали") == "details"
    assert detect_sheet_key("Трекеры") == "trackers"
    assert detect_sheet_key("Сводка") is None
    assert detect_sheet_key(None) is None


def test_parse_workbook_reads_both_sheets(report_path):
    parsed = parse_workbook(report_path)

    assert set(parsed.sheets) == {"details", "trackers"}
    assert parsed.sheets["details"].rows == 5
    assert parsed.sheets["trackers"].rows == 4
    assert parsed.skipped >= 1
    assert "Сводка" in parsed.ignored_sheets


def test_parse_workbook_normalizes_values(report_path):
    parsed = parse_workbook(report_path)
    details = parsed.sheets["details"].records

    first = details[0]
    assert first["date"].isoformat() == "2026-09-01"
    assert first["duration_text"] == "1м 14с"
    assert first["duration_sec"] == pytest.approx(74.0)
    assert first["fps"] == pytest.approx(30.0)
    assert first["frames"] == 2220
    assert first["bitrate"] == pytest.approx(6.5)
    assert first["extra"] == {"Комментарий": "эталон"}
    assert "эталон" in first["search_text"]


def test_parser_infers_missing_values(report_path):
    parsed = parse_workbook(report_path)
    details = parsed.sheets["details"].records
    inferred = next(row for row in details if row["episode"] == "PT_003")

    assert inferred["date"].isoformat() == "2026-09-01"
    assert inferred["fps"] == pytest.approx(round(2200 / 73, 2))
    assert inferred["duration_sec"] == pytest.approx(73.0)


def test_parser_keeps_broken_tracking_rows(report_path):
    parsed = parse_workbook(report_path)
    trackers = parsed.sheets["trackers"].records
    broken = next(row for row in trackers if row["episode"] == "PT_005")

    assert broken["points"] == 0
    assert broken["avg_hz"] == pytest.approx(0.0)
    assert broken["category"] == "Не прочитан / битый"


def test_parser_reports_unknown_columns(report_path):
    parsed = parse_workbook(report_path)
    assert "Комментарий" in parsed.unknown_columns


def test_parse_workbook_rejects_file_without_required_sheets(tmp_path: Path):
    path = tmp_path / "empty.xlsx"
    workbook = Workbook()
    workbook.active.title = "Прочее"
    workbook.active.append(["что-то"])
    workbook.save(path)

    with pytest.raises(ValidationError):
        parse_workbook(path)


def test_parse_workbook_rejects_unknown_extension(tmp_path: Path):
    path = tmp_path / "report.csv"
    path.write_text("a;b", encoding="utf-8")
    with pytest.raises(ValidationError):
        parse_workbook(path)


def test_parse_workbook_derives_duration_for_custom_rows(tmp_path: Path):
    rows = [
        [
            "03.11.2026", "PT", "SCN-task", "PT_100", "pico_headset", "Pico",
            "CameraRecord_20261103_090000.mp4", "2160x810", "h264", 6.6, "30/1",
            30, 1800, "00:60", 0, 0, 21.0, "Идеально 30 fps", "",
        ]
    ]
    path = build_report(tmp_path / "custom.xlsx", detail_rows=rows, tracker_rows=[])
    parsed = parse_workbook(path)
    record = parsed.sheets["details"].records[0]
    assert record["duration_sec"] == pytest.approx(60.0)
