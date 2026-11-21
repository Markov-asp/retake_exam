"""Сборка данных дашборда: KPI, графики по каждой метрике, метаданные."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from src.services import aggregator, repository
from src.services.aggregator import plural_ru
from src.services.catalog import get_sheet
from src.services.charts import build_figure
from src.services.normalization import human_duration
from src.services.repository import Filters

# Порядок групп графиков: сначала содержательные метрики, затем справочные.
GROUP_ORDER: dict[str, tuple[str, ...]] = {
    "details": ("Видео", "Время", "Качество", "Идентификация"),
    "trackers": ("Трекинг", "Качество", "Время", "Идентификация"),
}


def _format(value: float | None, decimals: int, fmt: str = "") -> str:
    if value is None:
        return "—"
    if fmt == "duration":
        return human_duration(value) or "—"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",")


def _card_meta(column, data: dict[str, Any], granularity: str) -> dict[str, Any]:
    """Краткая статистика под заголовком карточки."""
    overall = data.get("overall", {})
    unit = column.unit
    if data["kind"] == "categorical":
        unique = int(overall.get("unique", 0) or 0)
        total = int(overall.get("count", 0) or 0)
        return {
            "summary": (
                f"{unique} {plural_ru(unique, 'категория', 'категории', 'категорий')} · "
                f"{total} {plural_ru(total, 'запись', 'записи', 'записей')}"
            ),
            "overall": overall,
        }

    count = int(overall.get("count", 0))
    if data["kind"] == "histogram":
        if not count:
            return {"summary": "нет данных", "overall": overall}
        return {
            "summary": (
                f"мин {_format(overall.get('min'), column.decimals, column.fmt)} · "
                f"ср {_format(overall.get('avg'), column.decimals, column.fmt)} · "
                f"макс {_format(overall.get('max'), column.decimals, column.fmt)}"
            ),
            "overall": overall,
        }

    aggregation = data.get("aggregation", "avg")
    if not count:
        return {"summary": "нет данных", "overall": overall}

    if aggregation == "sum":
        summary = f"сумма {_format(overall.get('sum'), column.decimals, column.fmt)}"
    elif aggregation == "min":
        summary = f"минимум {_format(overall.get('min'), column.decimals, column.fmt)}"
    elif aggregation == "max":
        summary = f"максимум {_format(overall.get('max'), column.decimals, column.fmt)}"
    else:
        summary = f"среднее {_format(overall.get('avg'), column.decimals, column.fmt)}"
    if unit:
        summary += f" {unit}"
    summary += f" · {count} {plural_ru(count, 'эпизод', 'эпизода', 'эпизодов')}"
    if granularity != "all" and len(data.get("periods", [])) > 1:
        periods = len(data["periods"])
        summary += f" · {periods} {plural_ru(periods, 'период', 'периода', 'периодов')}"
    return {"summary": summary, "overall": overall}


def build_dashboard(
    conn: sqlite3.Connection,
    *,
    sheet_key: str,
    granularity: str,
    aggregation: str,
    filters: Filters,
    theme: str = "light",
) -> dict[str, Any]:
    """Формирует полный ответ дашборда для выбранного листа."""
    sheet = get_sheet(sheet_key)
    charts: list[dict[str, Any]] = []

    for column in sheet.metrics:
        if column.kind == "category":
            data = aggregator.categorical_data(conn, sheet_key, column, granularity, filters)
        elif granularity == "all":
            data = aggregator.histogram_data(conn, sheet_key, column, filters)
        else:
            data = aggregator.numeric_data(
                conn, sheet_key, column, granularity, aggregation, filters
            )
        figure = build_figure(data, theme)
        charts.append(
            {
                "metric": column.key,
                "title": column.title,
                "unit": column.unit,
                "group": column.group,
                "kind": "categorical" if column.kind == "category" else "numeric",
                "figure": figure,
                "meta": _card_meta(column, data, granularity),
            }
        )

    date_from, date_to = repository.date_bounds(conn, sheet_key, filters)
    total_rows = repository.count_rows(conn, sheet_key, filters)
    kpis = aggregator.build_kpis(conn, filters)

    order = {group: index for index, group in enumerate(GROUP_ORDER.get(sheet_key, ()))}
    charts.sort(key=lambda card: order.get(str(card.get("group")), len(order)))

    return {
        "sheet": sheet.key,
        "sheet_title": sheet.title,
        "description": sheet.description,
        "granularity": granularity,
        "aggregation": aggregation,
        "theme": theme,
        "total_rows": total_rows,
        "period": {"date_from": date_from, "date_to": date_to},
        "kpis": kpis,
        "charts": charts,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
