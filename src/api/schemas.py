"""Pydantic-схемы REST API (используются в OpenAPI-документации)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReportOut(BaseModel):
    """Карточка загруженного отчёта."""

    id: str
    title: str
    filename: str
    uploaded_at: str
    size_bytes: int = 0
    sha256: str | None = None
    details_rows: int = 0
    trackers_rows: int = 0
    skipped_rows: int = 0
    status: str = "ready"
    message: str | None = None


class ReportListOut(BaseModel):
    """Список отчётов."""

    items: list[ReportOut]
    total: int


class UploadOut(BaseModel):
    """Результат загрузки отчёта."""

    report: ReportOut
    duplicate: bool = False
    message: str


class ColumnOut(BaseModel):
    """Метаданные колонки отчёта."""

    key: str
    title: str
    kind: str
    unit: str = ""
    group: str = ""
    chartable: bool = False
    aggregation: str = "avg"
    aggregations: list[str] = Field(default_factory=list)
    decimals: int = 2
    description: str = ""
    format: str = ""


class SheetOut(BaseModel):
    """Лист отчёта с колонками и метриками."""

    key: str
    title: str
    description: str
    columns: list[ColumnOut]
    metrics: list[ColumnOut]


class GranularityOut(BaseModel):
    key: str
    title: str


class AggregationOut(BaseModel):
    key: str
    title: str


class CatalogOut(BaseModel):
    """Каталог листов, метрик и вариантов агрегации."""

    app: str
    version: str
    default_sheet: str
    default_metrics: dict[str, str]
    sheets: list[SheetOut]
    granularities: list[GranularityOut]
    aggregations: list[AggregationOut]


class ChartCardOut(BaseModel):
    """Карточка графика одной метрики."""

    metric: str
    title: str
    unit: str = ""
    group: str = ""
    kind: str
    figure: dict[str, Any]
    meta: dict[str, Any]


class PeriodOut(BaseModel):
    date_from: str | None = None
    date_to: str | None = None


class DashboardOut(BaseModel):
    """Полный ответ дашборда."""

    sheet: str
    sheet_title: str
    description: str
    granularity: str
    aggregation: str
    theme: str
    total_rows: int
    period: PeriodOut
    kpis: list[dict[str, Any]]
    charts: list[ChartCardOut]
    generated_at: str


class TableOut(BaseModel):
    """Страница таблицы с данными."""

    sheet: str
    columns: list[ColumnOut]
    rows: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    sort: str | None = None
    order: str = "desc"


class HealthOut(BaseModel):
    """Состояние сервиса."""

    status: str
    version: str
    database: str
    reports: int
    details_rows: int
    trackers_rows: int
    cache: dict[str, Any]


class DeleteOut(BaseModel):
    """Результат удаления отчёта."""

    id: str
    deleted: bool
    message: str
