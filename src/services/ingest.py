"""Конвейер импорта отчётов: файл → нормализованные записи → SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src.services import repository
from src.services.parser import ParsedWorkbook, parse_workbook
from src.utils.errors import ValidationError
from src.utils.logging import get_logger

logger = get_logger(__name__)

CHUNK_SIZE = 2000


@dataclass
class IngestResult:
    """Итог импорта отчёта."""

    report: dict[str, Any]
    duplicate: bool = False
    parsed: ParsedWorkbook | None = None


def file_sha256(path: Path | str, chunk_size: int = 1024 * 1024) -> str:
    """Считает SHA-256 файла потоково, не загружая его в память."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _record_to_row(record: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    """Приводит запись парсера к набору колонок таблицы."""
    row: dict[str, Any] = {}
    for column in columns:
        if column == "extra":
            extra = record.get("extra")
            row["extra"] = json.dumps(extra, ensure_ascii=False) if extra else None
        elif column == "search_text":
            row["search_text"] = record.get("search_text")
        else:
            value = record.get(column)
            if isinstance(value, datetime):
                value = value.isoformat(sep=" ", timespec="seconds")
            elif isinstance(value, date):
                value = value.isoformat()
            row[column] = value
    return row


def import_report(
    conn: sqlite3.Connection,
    path: Path | str,
    *,
    filename: str | None = None,
    title: str | None = None,
) -> IngestResult:
    """Импортирует один отчёт и возвращает его карточку.

    Повторная загрузка того же файла (совпадает SHA-256) не создаёт
    дубликат: возвращается уже существующий отчёт с флагом ``duplicate``.
    """
    file_path = Path(path)
    filename = filename or file_path.name
    checksum = file_sha256(file_path)

    existing = repository.find_report_by_hash(conn, checksum)
    if existing is not None:
        logger.info("Отчёт уже загружен: %s (%s)", existing["title"], existing["id"])
        return IngestResult(report=existing, duplicate=True)

    parsed = parse_workbook(file_path)
    if parsed.total_rows == 0:
        raise ValidationError(
            "В отчёте нет строк с данными",
            details={"filename": filename},
        )

    report_id = f"rep_{uuid.uuid4().hex[:12]}"
    report_title = (title or filename.rsplit(".", 1)[0]).strip() or "Без названия"
    report_row = {
        "id": report_id,
        "title": report_title,
        "filename": filename,
        "uploaded_at": _utc_now(),
        "size_bytes": file_path.stat().st_size,
        "sha256": checksum,
        "details_rows": 0,
        "trackers_rows": 0,
        "skipped_rows": parsed.skipped,
        "status": "processing",
        "message": None,
    }
    repository.insert_report(conn, report_row)

    try:
        for sheet_key, sheet in parsed.sheets.items():
            table = repository.table_for(sheet_key)
            db_columns = repository.table_columns(conn, table)
            records = list(sheet.records)
            for start in range(0, len(records), CHUNK_SIZE):
                chunk = records[start : start + CHUNK_SIZE]
                rows = []
                for offset, record in enumerate(chunk):
                    row = _record_to_row(record, db_columns)
                    row["report_id"] = report_id
                    row["row_index"] = start + offset
                    rows.append(row)
                repository.insert_rows(conn, table, rows)

        details_rows = parsed.sheets.get("details").rows if "details" in parsed.sheets else 0
        trackers_rows = parsed.sheets.get("trackers").rows if "trackers" in parsed.sheets else 0
        repository.update_report_counts(
            conn, report_id, details_rows, trackers_rows, parsed.skipped
        )

        notes: list[str] = []
        if parsed.unknown_columns:
            notes.append("Новые колонки: " + ", ".join(parsed.unknown_columns[:5]))
        unexpected_sheets = [name for name in parsed.ignored_sheets if "свод" not in name.lower()]
        if unexpected_sheets:
            notes.append("Пропущены листы: " + ", ".join(unexpected_sheets[:5]))
        message = "; ".join(notes) if notes else None

        conn.execute(
            "UPDATE reports SET status = 'ready', message = ? WHERE id = ?",
            (message, report_id),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("Ошибка импорта отчёта %s", filename)
        repository.update_report_status(conn, report_id, "failed", str(exc))
        conn.commit()
        raise

    report = repository.get_report(conn, report_id)
    if report is None:  # pragma: no cover - теоретически недостижимо
        raise ValidationError("Не удалось сохранить отчёт")
    logger.info(
        "Импортирован отчёт %s: details=%s, trackers=%s",
        report_id,
        report["details_rows"],
        report["trackers_rows"],
    )
    return IngestResult(report=report, parsed=parsed)


def seed_sample(conn: sqlite3.Connection, raw_dir: Path) -> list[dict[str, Any]]:
    """Импортирует демонстрационный отчёт при первом запуске."""
    if repository.count_reports(conn) > 0:
        return []
    if not raw_dir.is_dir():
        return []

    imported: list[dict[str, Any]] = []
    for path in sorted(raw_dir.glob("*.xlsx")):
        try:
            result = import_report(conn, path, filename=path.name)
            imported.append(result.report)
        except ValidationError as exc:
            logger.warning("Не удалось импортировать %s: %s", path.name, exc.message)
    return imported
