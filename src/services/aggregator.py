"""Агрегация данных для дашборда: ряды, распределения и KPI."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.services import repository
from src.services.catalog import Column, Sheet, get_sheet
from src.services.repository import Filters

MONTHS_SHORT = (
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)


def plural_ru(count: int, one: str, few: str, many: str) -> str:
    """Русская форма множественного числа для подписей."""
    value = abs(int(count)) % 100
    if 11 <= value <= 14:
        return many
    tail = value % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def period_label(period: str, granularity: str) -> str:
    """Человекочитаемая подпись периода."""
    if granularity == "month" and len(period) == 7:
        year, month = period.split("-")
        index = int(month) - 1
        if 0 <= index < 12:
            return f"{MONTHS_SHORT[index]} {year}"
        return period
    if granularity == "day" and len(period) == 10:
        year, month, day = period.split("-")
        return f"{day}.{month}.{year}"
    return "Весь объём"


def numeric_data(
    conn: sqlite3.Connection,
    sheet: str,
    column: Column,
    granularity: str,
    aggregation: str,
    filters: Filters,
) -> dict[str, Any]:
    """Готовит ряд числовой метрики для графика."""
    positive = column.positive_only
    rows = repository.numeric_series(
        conn, sheet, column.key, granularity, aggregation, filters, positive=positive
    )
    overall_rows = repository.numeric_series(
        conn, sheet, column.key, "all", aggregation, filters, positive=positive
    )
    overall_row = overall_rows[0] if overall_rows else {}

    periods = [str(row["period"]) for row in rows]
    return {
        "kind": "numeric",
        "granularity": granularity,
        "aggregation": aggregation,
        "metric": column.to_dict(),
        "periods": periods,
        "labels": [period_label(period, granularity) for period in periods],
        "values": [round(float(row["value"]), 4) if row["value"] is not None else None for row in rows],
        "counts": [int(row["n"]) for row in rows],
        "mins": [float(row["min_value"]) if row["min_value"] is not None else None for row in rows],
        "maxs": [float(row["max_value"]) if row["max_value"] is not None else None for row in rows],
        "overall": {
            "count": int(overall_row.get("n") or 0),
            "value": float(overall_row.get("value") or 0.0),
            "avg": float(overall_row.get("avg_value") or 0.0),
            "min": float(overall_row.get("min_value") or 0.0),
            "max": float(overall_row.get("max_value") or 0.0),
            "sum": float(overall_row.get("sum_value") or 0.0),
        },
    }


def categorical_data(
    conn: sqlite3.Connection,
    sheet: str,
    column: Column,
    granularity: str,
    filters: Filters,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """Готовит распределение категориальной метрики по периодам."""
    rows = repository.categorical_series(conn, sheet, column.key, granularity, filters)

    totals: dict[str, int] = {}
    for row in rows:
        value = str(row["value"])
        totals[value] = totals.get(value, 0) + int(row["n"])

    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    top = [value for value, _ in ordered[:limit]]
    rest = [value for value, _ in ordered[limit:]]
    other_label = f"Другие ({len(rest)})" if rest else None

    periods: list[str] = []
    seen: set[str] = set()
    matrix: dict[str, dict[str, int]] = {}
    for row in rows:
        period = str(row["period"])
        if period not in seen:
            seen.add(period)
            periods.append(period)
        value = str(row["value"])
        value = value if value in top else (other_label or value)
        bucket = matrix.setdefault(value, {})
        bucket[period] = bucket.get(period, 0) + int(row["n"])

    series = []
    for value, total in ordered:
        label = value if value in top else other_label
        if label is None:
            continue
        if any(item["name"] == label for item in series):
            continue
        series.append(
            {
                "name": label,
                "total": totals.get(value, total) if value in top else sum(
                    totals.get(item, 0) for item in rest
                ),
                "values": [int(matrix.get(label, {}).get(period, 0)) for period in periods],
            }
        )

    return {
        "kind": "categorical",
        "granularity": granularity,
        "metric": column.to_dict(),
        "periods": periods,
        "labels": [period_label(period, granularity) for period in periods],
        "series": series,
        "categories": [
            {"name": value, "count": count} for value, count in ordered
        ],
        "overall": {
            "count": sum(totals.values()),
            "unique": len(totals),
        },
    }


def histogram_data(
    conn: sqlite3.Connection,
    sheet: str,
    column: Column,
    filters: Filters,
    *,
    bins: int = 20,
) -> dict[str, Any]:
    """Готовит гистограмму распределения метрики."""
    positive = column.positive_only
    buckets = repository.numeric_histogram(
        conn, sheet, column.key, filters, bins=bins, positive=positive
    )
    overall_rows = repository.numeric_series(
        conn, sheet, column.key, "all", "avg", filters, positive=positive
    )
    overall_row = overall_rows[0] if overall_rows else {}
    return {
        "kind": "histogram",
        "granularity": "all",
        "metric": column.to_dict(),
        "bins": buckets,
        "overall": {
            "count": int(overall_row.get("n") or 0),
            "avg": float(overall_row.get("avg_value") or 0.0),
            "min": float(overall_row.get("min_value") or 0.0),
            "max": float(overall_row.get("max_value") or 0.0),
        },
    }


def _scalar(conn: sqlite3.Connection, sql: str, filters: Filters, extra: Sequence[str] = ()) -> Any:
    where, params = repository.where_clause(filters, extra=extra)
    return repository.scalar(conn, f"{sql}{where}", params)


def _format_number(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def build_kpis(conn: sqlite3.Connection, filters: Filters) -> list[dict[str, Any]]:
    """Формирует карточки KPI для верхней панели дашборда."""
    details_sheet = get_sheet("details")
    trackers_sheet = get_sheet("trackers")
    details_table = details_sheet.table
    trackers_table = trackers_sheet.table

    episodes = repository.count_rows(conn, "details", filters)
    tracking_files = repository.count_rows(conn, "trackers", filters)
    date_from, date_to = repository.date_bounds(conn, "details", filters)
    days = _scalar(
        conn,
        f"SELECT COUNT(DISTINCT date) FROM {details_table}",
        filters,
        extra=["date IS NOT NULL"],
    )
    total_seconds = _scalar(
        conn,
        f"SELECT COALESCE(SUM(duration_sec), 0) FROM {details_table}",
        filters,
        extra=["duration_sec IS NOT NULL"],
    )
    avg_fps = _scalar(conn, f"SELECT AVG(fps) FROM {details_table}", filters, extra=["fps IS NOT NULL"])
    avg_bitrate = _scalar(
        conn, f"SELECT AVG(bitrate) FROM {details_table}", filters, extra=["bitrate IS NOT NULL"]
    )
    problem_episodes = _scalar(
        conn,
        f"SELECT COUNT(*) FROM {details_table}",
        filters,
        extra=["bad_intervals > 0"],
    )
    avg_hz = _scalar(
        conn, f"SELECT AVG(avg_hz) FROM {trackers_table}", filters, extra=["avg_hz > 0"]
    )
    avg_uniformity = _scalar(
        conn,
        f"SELECT AVG(uniformity) FROM {trackers_table}",
        filters,
        extra=["uniformity > 0"],
    )
    total_gaps = _scalar(
        conn, f"SELECT COALESCE(SUM(gaps), 0) FROM {trackers_table}", filters, extra=["gaps IS NOT NULL"]
    )

    problem_share = (problem_episodes / episodes * 100.0) if episodes else 0.0
    hours = float(total_seconds or 0) / 3600.0

    period_hint = (
        f"{_format_date(date_from)} — {_format_date(date_to)}"
        if date_from or date_to
        else "нет данных"
    )

    cards = [
        {
            "id": "episodes",
            "label": "Эпизодов",
            "value": episodes,
            "display": _format_number(episodes, 0),
            "unit": "шт.",
            "hint": f"{tracking_files} {plural_ru(tracking_files, 'файл трекинга', 'файла трекинга', 'файлов трекинга')}",
            "tone": "primary",
        },
        {
            "id": "days",
            "label": "Дней наблюдения",
            "value": days or 0,
            "display": _format_number(days, 0),
            "unit": plural_ru(int(days or 0), "день", "дня", "дней"),
            "hint": period_hint,
            "tone": "neutral",
        },
        {
            "id": "duration",
            "label": "Суммарная длительность",
            "value": round(hours, 2),
            "display": _format_number(hours, 1),
            "unit": "ч",
            "hint": f"{_format_number(float(total_seconds or 0), 0)} с записи",
            "tone": "neutral",
        },
        {
            "id": "fps",
            "label": "Средний FPS",
            "value": round(avg_fps, 2) if avg_fps is not None else None,
            "display": _format_number(avg_fps, 2) if avg_fps is not None else "—",
            "unit": "fps",
            "hint": "фактическая частота кадров",
            "tone": "accent",
        },
        {
            "id": "bitrate",
            "label": "Средний битрейт",
            "value": round(avg_bitrate, 2) if avg_bitrate is not None else None,
            "display": _format_number(avg_bitrate, 2) if avg_bitrate is not None else "—",
            "unit": "Мбит/с",
            "hint": "по всем эпизодам",
            "tone": "neutral",
        },
        {
            "id": "problems",
            "label": "Проблемные эпизоды",
            "value": round(problem_share, 2),
            "display": _format_number(problem_share, 1),
            "unit": "%",
            "hint": f"{problem_episodes} из {episodes}",
            "tone": "warning",
        },
        {
            "id": "tracking_hz",
            "label": "Средняя частота трекинга",
            "value": round(avg_hz, 2) if avg_hz is not None else None,
            "display": _format_number(avg_hz, 2) if avg_hz is not None else "—",
            "unit": "Гц",
            "hint": "целевая частота ~90 Гц",
            "tone": "accent",
        },
        {
            "id": "uniformity",
            "label": "Равномерность трекинга",
            "value": round(avg_uniformity, 2) if avg_uniformity is not None else None,
            "display": _format_number(avg_uniformity, 2) if avg_uniformity is not None else "—",
            "unit": "%",
            "hint": (
                f"{_format_number(total_gaps, 0)} "
                f"{plural_ru(int(total_gaps or 0), 'пропуск', 'пропуска', 'пропусков')} всего"
            ),
            "tone": "neutral",
        },
    ]
    return cards


def _format_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        year, month, day = value.split("-")
        return f"{day}.{month}.{year}"
    except ValueError:
        return value


@dataclass(frozen=True)
class DashboardContext:
    """Параметры запроса дашборда."""

    sheet: Sheet
    filters: Filters
    granularity: str
    aggregation: str
