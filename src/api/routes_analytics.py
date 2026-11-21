"""Аналитическое API: каталог, дашборд, графики, таблицы, экспорт."""

from __future__ import annotations

import csv
import io
import sqlite3
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill

from src.api.deps import get_cache, get_db, get_settings
from src.api.schemas import (
    AggregationOut,
    CatalogOut,
    ChartCardOut,
    ColumnOut,
    DashboardOut,
    GranularityOut,
    HealthOut,
    SheetOut,
    TableOut,
)
from src.config import Settings
from src.services import aggregator, repository
from src.services.catalog import (
    AGGREGATION_TITLES,
    DEFAULT_METRICS,
    GRANULARITY_TITLES,
    SHEETS,
    get_metric,
    get_sheet,
)
from src.services.charts import build_figure
from src.services.dashboard import build_dashboard
from src.services.repository import Filters
from src.utils.cache import TTLCache, make_key

router = APIRouter(prefix="/api", tags=["Аналитика"])

SheetName = Literal["details", "trackers"]
Granularity = Literal["day", "month", "all"]
Aggregation = Literal["avg", "sum", "min", "max"]
Theme = Literal["light", "dark"]


def _filters(
    report_id: str | None,
    date_from: date | None,
    date_to: date | None,
) -> Filters:
    return Filters(
        report_id=report_id or None,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
    )


@router.get("/catalog", response_model=CatalogOut, summary="Каталог листов и метрик")
def catalog(settings: Settings = Depends(get_settings)) -> CatalogOut:
    """Отдаёт описание всех листов, колонок и вариантов агрегации."""
    return CatalogOut(
        app=settings.app_name,
        version=settings.version,
        default_sheet="details",
        default_metrics=DEFAULT_METRICS,
        sheets=[SheetOut(**sheet.to_dict()) for sheet in SHEETS.values()],
        granularities=[
            GranularityOut(key=key, title=title) for key, title in GRANULARITY_TITLES.items()
        ],
        aggregations=[
            AggregationOut(key=key, title=title) for key, title in AGGREGATION_TITLES.items()
        ],
    )


@router.get("/dashboard", response_model=DashboardOut, summary="Данные дашборда")
def dashboard(
    sheet: SheetName = "details",
    granularity: Granularity = "day",
    aggregation: Aggregation = "avg",
    date_from: date | None = None,
    date_to: date | None = None,
    report_id: str | None = None,
    theme: Theme = "light",
    cache: TTLCache = Depends(get_cache),
    conn: sqlite3.Connection = Depends(get_db),
) -> DashboardOut:
    """KPI и графики по каждой метрике выбранного листа.

    ``granularity=all`` строит распределения на всём объёме данных.
    """
    filters = _filters(report_id, date_from, date_to)
    key = make_key("dashboard", sheet, granularity, aggregation, filters, theme)
    payload = cache.get_or_set(
        key,
        lambda: build_dashboard(
            conn,
            sheet_key=sheet,
            granularity=granularity,
            aggregation=aggregation,
            filters=filters,
            theme=theme,
        ),
    )
    return DashboardOut(**payload)


@router.get(
    "/charts/{sheet}/{metric}",
    response_model=ChartCardOut,
    summary="График одной метрики",
)
def metric_chart(
    sheet: SheetName,
    metric: str,
    granularity: Granularity = "day",
    aggregation: Aggregation = "avg",
    date_from: date | None = None,
    date_to: date | None = None,
    report_id: str | None = None,
    theme: Theme = "light",
    cache: TTLCache = Depends(get_cache),
    conn: sqlite3.Connection = Depends(get_db),
) -> ChartCardOut:
    """Возвращает Plotly-фигуру и сводку по одной метрике."""
    column = get_metric(sheet, metric)
    filters = _filters(report_id, date_from, date_to)

    def build() -> dict:
        if column.kind == "category":
            data = aggregator.categorical_data(conn, sheet, column, granularity, filters)
        elif granularity == "all":
            data = aggregator.histogram_data(conn, sheet, column, filters)
        else:
            data = aggregator.numeric_data(
                conn, sheet, column, granularity, aggregation, filters
            )
        from src.services.dashboard import _card_meta  # локальный импорт во избежание цикла

        return {
            "metric": column.key,
            "title": column.title,
            "unit": column.unit,
            "group": column.group,
            "kind": "categorical" if column.kind == "category" else "numeric",
            "figure": build_figure(data, theme),
            "meta": _card_meta(column, data, granularity),
        }

    key = make_key("chart", sheet, metric, granularity, aggregation, filters, theme)
    return ChartCardOut(**cache.get_or_set(key, build))


@router.get("/table/{sheet}", response_model=TableOut, summary="Таблица записей")
def table(
    sheet: SheetName,
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    search: str | None = Query(None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    report_id: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> TableOut:
    """Постраничная выдача нормализованных записей с поиском."""
    definition = get_sheet(sheet)
    filters = Filters(
        report_id=report_id or None,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        search=(search or "").strip() or None,
    )
    total = repository.count_rows(conn, sheet, filters)
    rows = repository.fetch_page(
        conn,
        sheet,
        filters,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
        columns=[column.key for column in definition.columns],
    )
    return TableOut(
        sheet=sheet,
        columns=[ColumnOut(**column.to_dict()) for column in definition.columns],
        rows=rows,
        total=total,
        limit=limit,
        offset=offset,
        sort=sort or "date",
        order=order,
    )


@router.get("/health", response_model=HealthOut, summary="Состояние сервиса")
def health(
    settings: Settings = Depends(get_settings),
    cache: TTLCache = Depends(get_cache),
    conn: sqlite3.Connection = Depends(get_db),
) -> HealthOut:
    """Проверка живости, счётчики данных и статистика кэша."""
    empty = Filters()
    return HealthOut(
        status="ok",
        version=settings.version,
        database=str(settings.database),
        reports=repository.count_reports(conn),
        details_rows=repository.count_rows(conn, "details", empty),
        trackers_rows=repository.count_rows(conn, "trackers", empty),
        cache=cache.stats(),
    )


def _export_value(value: Any, fmt: str) -> Any:
    """Приводит значение к удобному для Excel виду (даты — DD.MM.YYYY)."""
    if value is None or value == "":
        return ""
    if fmt == "date":
        text = str(value)[:10]
        parts = text.split("-")
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return value


def _csv_chunks(
    records: Iterator[dict],
    columns: list[tuple[str, str, str]],
) -> Iterator[bytes]:
    """Потоково формирует CSV с BOM и разделителем «;» (для Excel)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([title for _, title, _ in columns])
    yield b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)

    row_count = 0
    for record in records:
        writer.writerow([_export_value(record.get(key, ""), fmt) for key, _, fmt in columns])
        row_count += 1
        if row_count % 500 == 0:
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)
    if buffer.tell():
        yield buffer.getvalue().encode("utf-8")


@router.get("/export/{sheet}.csv", summary="Экспорт выборки в CSV")
def export_csv(
    sheet: SheetName,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    report_id: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Выгружает отфильтрованные записи в CSV (UTF-8 с BOM)."""
    definition = get_sheet(sheet)
    filters = Filters(
        report_id=report_id or None,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        search=(search or "").strip() or None,
    )
    columns = [(column.key, column.title, column.fmt) for column in definition.columns]
    keys = [key for key, _, _ in columns]
    records = repository.iter_records(conn, sheet, filters, columns=keys)
    filename = f"{sheet}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.csv"
    return StreamingResponse(
        _csv_chunks(records, columns),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/{sheet}.xlsx", summary="Экспорт выборки в Excel")
def export_xlsx(
    sheet: SheetName,
    background: BackgroundTasks,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    report_id: str | None = None,
    settings: Settings = Depends(get_settings),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Формирует .xlsx с заголовками и всеми записями выборки."""
    definition = get_sheet(sheet)
    filters = Filters(
        report_id=report_id or None,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        search=(search or "").strip() or None,
    )
    columns = [(column.key, column.title, column.fmt) for column in definition.columns]

    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title=definition.title[:31])
    header = []
    for _, title, _ in columns:
        cell = WriteOnlyCell(worksheet, value=title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="312E81")
        header.append(cell)
    worksheet.append(header)

    for record in repository.iter_records(
        conn, sheet, filters, columns=[key for key, _, _ in columns]
    ):
        worksheet.append(
            [_export_value(record.get(key), fmt) for key, _, fmt in columns]
        )

    exports_dir = settings.data_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    path = exports_dir / f"{sheet}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.xlsx"
    workbook.save(path)
    background.add_task(Path(path).unlink, missing_ok=True)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )
