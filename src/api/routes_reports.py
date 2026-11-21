"""API отчётов: загрузка, список, удаление, скачивание исходника."""

from __future__ import annotations

import re
import sqlite3
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from src.api.deps import get_cache, get_db, get_settings
from src.api.schemas import DeleteOut, ReportListOut, ReportOut, UploadOut
from src.config import Settings
from src.services import repository
from src.services.ingest import import_report
from src.utils.cache import TTLCache
from src.utils.errors import NotFoundError, PayloadTooLarge, ValidationError
from src.utils.logging import get_logger

router = APIRouter(prefix="/api/reports", tags=["Отчёты"])
logger = get_logger(__name__)

CHUNK_SIZE = 1024 * 1024
ALLOWED_SUFFIXES = {".xlsx", ".xlsm"}


def _safe_filename(name: str) -> str:
    """Убирает опасные символы из имени файла."""
    base = Path(name or "report.xlsx").name
    cleaned = re.sub(r"[^\w.\-() ]+", "_", base, flags=re.UNICODE)
    return cleaned[:120] or "report.xlsx"


def _find_source_file(settings: Settings, report: dict) -> Path | None:
    """Ищет сохранённый исходный файл отчёта."""
    for candidate in settings.uploads_dir.glob(f"{report['id']}_*"):
        if candidate.is_file():
            return candidate
    raw = settings.raw_dir / str(report["filename"])
    return raw if raw.is_file() else None


@router.get("", response_model=ReportListOut, summary="Список загруженных отчётов")
def list_reports(conn: sqlite3.Connection = Depends(get_db)) -> ReportListOut:
    """Возвращает отчёты от новых к старым."""
    reports = repository.list_reports(conn)
    return ReportListOut(items=[ReportOut(**report) for report in reports], total=len(reports))


@router.post(
    "",
    response_model=UploadOut,
    status_code=201,
    summary="Загрузить и обработать отчёт",
)
async def upload_report(
    file: UploadFile = File(..., description="Файл отчёта .xlsx"),
    title: str | None = Form(None, description="Необязательное название отчёта"),
    settings: Settings = Depends(get_settings),
    cache: TTLCache = Depends(get_cache),
    conn: sqlite3.Connection = Depends(get_db),
) -> UploadOut:
    """Принимает Excel-отчёт, нормализует строки и сохраняет их в БД.

    Повторная загрузка идентичного файла (по SHA-256) не создаёт дубликат.
    """
    filename = _safe_filename(file.filename or "report.xlsx")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValidationError(
            "Поддерживаются только файлы .xlsx и .xlsm",
            details={"filename": filename},
        )

    settings.ensure_directories()
    temp_path = settings.uploads_dir / f".upload_{uuid.uuid4().hex}{suffix}"
    limit = settings.max_upload_mb * 1024 * 1024
    size = 0

    try:
        with open(temp_path, "wb") as handle:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > limit:
                    raise PayloadTooLarge(
                        f"Файл больше {settings.max_upload_mb} МБ",
                        details={"limit_mb": settings.max_upload_mb},
                    )
                handle.write(chunk)
        await file.close()

        if size == 0:
            raise ValidationError("Загружен пустой файл")

        result = await run_in_threadpool(
            import_report, conn, temp_path, filename=filename, title=title
        )
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    report = result.report
    if result.duplicate:
        temp_path.unlink(missing_ok=True)
        return UploadOut(
            report=ReportOut(**report),
            duplicate=True,
            message="Этот отчёт уже загружен — используется существующая копия",
        )

    final_path = settings.uploads_dir / f"{report['id']}_{filename}"
    temp_path.replace(final_path)
    cache.invalidate()
    logger.info("Загружен отчёт %s (%s байт)", report["id"], size)

    return UploadOut(
        report=ReportOut(**report),
        duplicate=False,
        message=(
            f"Обработано строк: Детали — {report['details_rows']}, "
            f"Трекеры — {report['trackers_rows']}"
        ),
    )


@router.get("/{report_id}", response_model=ReportOut, summary="Карточка отчёта")
def get_report(report_id: str, conn: sqlite3.Connection = Depends(get_db)) -> ReportOut:
    """Возвращает один отчёт по идентификатору."""
    report = repository.get_report(conn, report_id)
    if report is None:
        raise NotFoundError("Отчёт не найден", details={"id": report_id})
    return ReportOut(**report)


@router.get("/{report_id}/download", summary="Скачать исходный файл отчёта")
def download_report(
    report_id: str,
    settings: Settings = Depends(get_settings),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Отдаёт исходный Excel-файл, если он сохранён на диске."""
    report = repository.get_report(conn, report_id)
    if report is None:
        raise NotFoundError("Отчёт не найден", details={"id": report_id})
    path = _find_source_file(settings, report)
    if path is None:
        raise HTTPException(status_code=404, detail="Исходный файл не найден на диске")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=str(report["filename"]),
    )


@router.delete("/{report_id}", response_model=DeleteOut, summary="Удалить отчёт")
def delete_report(
    report_id: str,
    settings: Settings = Depends(get_settings),
    cache: TTLCache = Depends(get_cache),
    conn: sqlite3.Connection = Depends(get_db),
) -> DeleteOut:
    """Удаляет отчёт, связанные строки и сохранённый файл."""
    report = repository.get_report(conn, report_id)
    if report is None:
        raise NotFoundError("Отчёт не найден", details={"id": report_id})

    deleted = repository.delete_report(conn, report_id)
    for candidate in settings.uploads_dir.glob(f"{report_id}_*"):
        candidate.unlink(missing_ok=True)
    cache.invalidate()
    logger.info("Удалён отчёт %s", report_id)
    return DeleteOut(id=report_id, deleted=deleted, message="Отчёт удалён")
