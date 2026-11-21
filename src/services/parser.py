"""Парсер Excel-отчётов.

Чтение выполняется в потоковом режиме (``read_only=True``), поэтому файл
на сотни тысяч строк не загружается в память целиком. Строка заголовка
ищется автоматически: в отчёте над таблицей находится служебный заголовок
``data | Детали``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from src.services.catalog import SHEETS, Sheet
from src.services.normalization import (
    build_search_text,
    clean_text,
    human_duration,
    parse_duration,
    parse_filename_stamp,
    resolve_headers,
    value_for_column,
)
from src.utils.errors import ValidationError

HEADER_SCAN_ROWS = 15
MIN_HEADER_MATCHES = 2

SUPPORTED_SUFFIXES = {".xlsx", ".xlsm"}


@dataclass
class ParsedSheet:
    """Результат разбора одного листа."""

    key: str
    title: str
    records: list[dict[str, Any]] = field(default_factory=list)
    skipped: int = 0
    unknown_columns: list[str] = field(default_factory=list)
    header_row: int = 0

    @property
    def rows(self) -> int:
        return len(self.records)


@dataclass
class ParsedWorkbook:
    """Результат разбора книги целиком."""

    path: Path
    title: str
    sheets: dict[str, ParsedSheet] = field(default_factory=dict)
    ignored_sheets: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(sheet.rows for sheet in self.sheets.values())

    @property
    def skipped(self) -> int:
        return sum(sheet.skipped for sheet in self.sheets.values())

    @property
    def unknown_columns(self) -> list[str]:
        seen: list[str] = []
        for sheet in self.sheets.values():
            for column in sheet.unknown_columns:
                if column not in seen:
                    seen.append(column)
        return seen


def detect_sheet_key(name: str | None) -> str | None:
    """Определяет назначение листа по его названию."""
    if not name:
        return None
    text = str(name).strip().lower().replace("ё", "е")
    if "детал" in text or "detail" in text:
        return "details"
    if "трекер" in text or "track" in text:
        return "trackers"
    return None


def _iter_rows(worksheet: Worksheet) -> Iterator[Sequence[Any]]:
    yield from worksheet.iter_rows(values_only=True)


def _detect_header(
    buffer: list[Sequence[Any]], sheet: Sheet
) -> tuple[int, dict[int, str], dict[int, str]]:
    """Ищет строку заголовка с максимальным числом распознанных колонок."""
    best_index = -1
    best_mapping: dict[int, str] = {}
    best_unknown: dict[int, str] = {}
    for index, row in enumerate(buffer):
        mapping, unknown = resolve_headers(sheet, row)
        if len(mapping) > len(best_mapping):
            best_index = index
            best_mapping = mapping
            best_unknown = unknown
    if best_index < 0 or len(best_mapping) < MIN_HEADER_MATCHES:
        return -1, {}, {}
    return best_index, best_mapping, best_unknown


def _cell(row: Sequence[Any], position: int) -> Any:
    if position < len(row):
        return row[position]
    return None


def _row_to_record(
    row: Sequence[Any],
    mapping: dict[int, str],
    unknown: dict[int, str],
    sheet: Sheet,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record: dict[str, Any] = {}
    for position, key in mapping.items():
        column = sheet.column(key)
        if column is None:  # pragma: no cover - защита от рассинхронизации каталога
            continue
        record[key] = value_for_column(column, _cell(row, position))

    extra: dict[str, Any] = {}
    for position, header in unknown.items():
        value = clean_text(_cell(row, position))
        if value is not None:
            extra[str(header)] = value
    return record, extra


def _finalize_details(record: dict[str, Any]) -> dict[str, Any]:
    """Достраивает производные поля видеоэпизода."""
    duration = record.get("duration_sec")
    if duration is None:
        duration = parse_duration(record.get("duration_text"))
    if duration is not None:
        record["duration_sec"] = round(float(duration), 3)
        record.setdefault("duration_text", human_duration(duration))
    elif record.get("duration_text"):
        record["duration_text"] = str(record["duration_text"]).strip()

    if record.get("date") is None:
        inferred_date, started_at = parse_filename_stamp(record.get("file"))
        if inferred_date is not None:
            record["date"] = inferred_date
        if started_at is not None and not record.get("started_at"):
            record["started_at"] = started_at.isoformat(sep=" ", timespec="seconds")
    elif not record.get("started_at"):
        _, started_at = parse_filename_stamp(record.get("file"))
        if started_at is not None:
            record["started_at"] = started_at.isoformat(sep=" ", timespec="seconds")

    frames = record.get("frames")
    duration = record.get("duration_sec")
    if record.get("fps") is None and frames and duration:
        record["fps"] = round(float(frames) / float(duration), 2)
    if record.get("frames") is None and record.get("fps") and duration:
        record["frames"] = int(round(float(record["fps"]) * float(duration)))
    return record


def _finalize_trackers(record: dict[str, Any]) -> dict[str, Any]:
    """Достраивает производные поля телеметрии."""
    duration = record.get("duration_sec")
    if duration is None:
        duration = parse_duration(record.get("duration_text"))
    if duration is not None:
        record["duration_sec"] = round(float(duration), 3)
        record.setdefault("duration_text", human_duration(duration))

    if record.get("date") is None:
        inferred_date, started_at = parse_filename_stamp(record.get("file"))
        if inferred_date is not None:
            record["date"] = inferred_date
        if started_at is not None and not record.get("started_at"):
            record["started_at"] = started_at.isoformat(sep=" ", timespec="seconds")

    points = record.get("points")
    duration = record.get("duration_sec")
    if record.get("avg_hz") is None and points and duration:
        record["avg_hz"] = round(float(points) / float(duration), 2)
    if record.get("points") is None and record.get("avg_hz") and duration:
        record["points"] = int(round(float(record["avg_hz"]) * float(duration)))
    return record


def _prepare_row(record: dict[str, Any], sheet_key: str) -> dict[str, Any]:
    if sheet_key == "details":
        return _finalize_details(record)
    return _finalize_trackers(record)


def parse_sheet(
    worksheet: Worksheet,
    sheet_key: str,
) -> ParsedSheet:
    """Разбирает один лист отчёта."""
    sheet = SHEETS[sheet_key]
    rows = _iter_rows(worksheet)

    buffer: list[Sequence[Any]] = []
    for _ in range(HEADER_SCAN_ROWS):
        try:
            buffer.append(next(rows))
        except StopIteration:
            break

    header_index, mapping, unknown = _detect_header(buffer, sheet)
    if header_index < 0:
        raise ValidationError(
            f"Не удалось найти строку заголовка на листе «{worksheet.title}»",
            details={"sheet": worksheet.title},
        )

    parsed = ParsedSheet(
        key=sheet_key,
        title=str(worksheet.title),
        unknown_columns=list(unknown.values()),
        header_row=header_index + 1,
    )

    def consume(row: Sequence[Any]) -> None:
        record, extra = _row_to_record(row, mapping, unknown, sheet)
        if not any(value not in (None, "") for value in record.values()):
            if any(value not in (None, "") for value in extra.values()):
                pass  # строка целиком из неизвестных колонок — сохраняем ниже
            else:
                parsed.skipped += 1
                return
        record = _prepare_row(record, sheet_key)
        record.setdefault("extra", None)
        if extra:
            record["extra"] = extra
        record["search_text"] = build_search_text(record)
        parsed.records.append(record)

    for row in buffer[header_index + 1 :]:
        consume(row)
    for row in rows:
        consume(row)

    return parsed


def parse_workbook(path: Path | str) -> ParsedWorkbook:
    """Разбирает книгу целиком, отбирая листы «Детали» и «Трекеры»."""
    file_path = Path(path)
    if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValidationError(
            "Поддерживаются только файлы .xlsx и .xlsm",
            details={"filename": file_path.name},
        )
    if not file_path.is_file():
        raise ValidationError("Файл отчёта не найден", details={"filename": file_path.name})

    try:
        workbook = openpyxl.load_workbook(
            filename=str(file_path), read_only=True, data_only=True
        )
    except Exception as exc:  # noqa: BLE001 - сообщение пользователю важнее типа
        raise ValidationError(
            "Не удалось открыть файл Excel. Проверьте, что это корректный .xlsx",
            details={"reason": str(exc)},
        ) from exc

    result = ParsedWorkbook(path=file_path, title=file_path.stem)
    seen_sheets: list[str] = []
    try:
        for worksheet in workbook.worksheets:
            seen_sheets.append(str(worksheet.title))
            key = detect_sheet_key(worksheet.title)
            if key is None:
                result.ignored_sheets.append(str(worksheet.title))
                continue
            if key in result.sheets:
                continue
            result.sheets[key] = parse_sheet(worksheet, key)
    finally:
        workbook.close()

    if not result.sheets:
        raise ValidationError(
            "В файле не найдены листы «Детали» или «Трекеры»",
            details={"sheets": seen_sheets},
        )
    return result


def iter_summary_rows(path: Path | str) -> Iterable[tuple[str, Any]]:
    """Возвращает пары «показатель — значение» из листа «Сводка»."""
    workbook = openpyxl.load_workbook(filename=str(path), read_only=True, data_only=True)
    try:
        for worksheet in workbook.worksheets:
            title = str(worksheet.title).lower()
            if "свод" not in title:
                continue
            for row in worksheet.iter_rows(values_only=True):
                if not row or row[0] is None:
                    continue
                label = str(row[0]).strip()
                if re.search(r"[A-Za-zА-Яа-я]", label) and len(row) > 1 and row[1] is not None:
                    yield label, row[1]
    finally:
        workbook.close()
