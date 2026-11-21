"""Построение интерактивных графиков Plotly.

Фигуры собираются на сервере и отдаются клиенту в виде Plotly JSON:
браузер не выполняет расчёты, а только отрисовывает готовую фигуру.
"""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go

from src.services.catalog import AGGREGATION_TITLES

PALETTE = (
    "#4f46e5",
    "#0ea5e9",
    "#f59e0b",
    "#10b981",
    "#ef4444",
    "#8b5cf6",
    "#14b8a6",
    "#f97316",
    "#3b82f6",
    "#ec4899",
)

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "font": "#1f2937",
        "muted": "#6b7280",
        "grid": "#e5e7eb",
        "axis": "#cbd5e1",
        "bar": "#4f46e5",
        "line": "#94a3b8",
        "accent": "#0ea5e9",
    },
    "dark": {
        "font": "#e5e7eb",
        "muted": "#9ca3af",
        "grid": "#374151",
        "axis": "#4b5563",
        "bar": "#818cf8",
        "line": "#64748b",
        "accent": "#38bdf8",
    },
}

FONT_FAMILY = "Inter, 'Segoe UI', Roboto, Arial, sans-serif"


def _theme(name: str) -> dict[str, str]:
    return THEMES.get(name, THEMES["light"])


def _layout(theme: str, *, height: int = 340, show_legend: bool = True) -> dict[str, Any]:
    colors = _theme(theme)
    return {
        "template": "none",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": FONT_FAMILY, "size": 12, "color": colors["font"]},
        "margin": {"l": 8, "r": 30, "t": 8, "b": 38},
        "height": height,
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": "rgba(17, 24, 39, 0.92)" if theme == "light" else "rgba(243, 244, 246, 0.95)",
            "font": {"color": "#f9fafb" if theme == "light" else "#111827", "size": 12},
            "bordercolor": "rgba(0,0,0,0)",
        },
        "showlegend": show_legend,
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
        },
        "bargap": 0.35,
        "transition": {"duration": 0},
    }


def _axes(fig: go.Figure, theme: str, *, y2: bool = False) -> None:
    colors = _theme(theme)
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        nticks=12,
        tickangle=-32,
        linecolor=colors["axis"],
        tickfont={"size": 11, "color": colors["muted"]},
        automargin=True,
        ticks="outside",
        ticklen=4,
        tickcolor=colors["axis"],
    )
    fig.update_yaxes(
        gridcolor=colors["grid"],
        zeroline=False,
        linecolor=colors["axis"],
        tickfont={"size": 11, "color": colors["muted"]},
        automargin=True,
        title_font={"size": 11, "color": colors["muted"]},
    )
    if y2:
        fig.update_layout(
            yaxis2={
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "zeroline": False,
                "rangemode": "tozero",
                "automargin": True,
                "tickfont": {"size": 10, "color": colors["muted"]},
            }
        )


def _hover(value_fmt: str, unit: str) -> str:
    suffix = f" {unit}" if unit else ""
    return f"<b>%{{x}}</b><br>{value_fmt}{suffix}<extra></extra>"


def _to_dict(fig: go.Figure) -> dict[str, Any]:
    return json.loads(fig.to_json())


def numeric_figure(data: dict[str, Any], theme: str = "light") -> dict[str, Any]:
    """Столбцы по периодам + линия количества записей на второй оси."""
    metric = data["metric"]
    unit = metric.get("unit", "")
    labels = data["labels"]
    values = data["values"]
    counts = data["counts"]
    aggregation = data["aggregation"]

    fig = go.Figure()
    error_y = None
    if aggregation == "avg" and len(values) > 1:
        plus = []
        minus = []
        for value, high, low in zip(values, data["maxs"], data["mins"], strict=False):
            if value is None:
                plus.append(0)
                minus.append(0)
                continue
            plus.append(max(0.0, float(high or value) - float(value)))
            minus.append(max(0.0, float(value) - float(low or value)))
        error_y = {
            "type": "data",
            "array": plus,
            "arrayminus": minus,
            "visible": True,
            "color": _theme(theme)["muted"],
            "thickness": 1,
            "width": 3,
        }

    fig.add_bar(
        x=labels,
        y=values,
        name=AGGREGATION_TITLES.get(aggregation, aggregation),
        marker={"color": _theme(theme)["bar"], "line": {"width": 0}},
        error_y=error_y,
        hovertemplate=_hover("%{y:.2f}", unit),
        cliponaxis=False,
    )
    fig.add_scatter(
        x=labels,
        y=counts,
        name="Эпизодов",
        mode="lines+markers",
        yaxis="y2",
        line={"color": _theme(theme)["line"], "width": 1.5, "dash": "dot"},
        marker={"size": 5, "color": _theme(theme)["line"]},
        hovertemplate="<b>%{x}</b><br>записей: %{y}<extra></extra>",
    )
    layout = _layout(theme, height=340)
    layout["yaxis"] = {"title": {"text": unit or None}}
    fig.update_layout(**layout)
    _axes(fig, theme, y2=True)
    return _to_dict(fig)


def histogram_figure(data: dict[str, Any], theme: str = "light") -> dict[str, Any]:
    """Распределение метрики на всём объёме данных."""
    metric = data["metric"]
    unit = metric.get("unit", "")
    bins = data["bins"]
    colors = _theme(theme)

    centers = [round((bucket["x0"] + bucket["x1"]) / 2, 4) for bucket in bins]
    widths = [max(bucket["x1"] - bucket["x0"], 0.0001) for bucket in bins]
    counts = [bucket["count"] for bucket in bins]

    fig = go.Figure()
    fig.add_bar(
        x=centers,
        y=counts,
        width=widths,
        name="Эпизодов",
        marker={"color": colors["bar"], "line": {"width": 0}},
        hovertemplate=f"<b>%{{x:.2f}}{(' ' + unit) if unit else ''}</b><br>эпизодов: %{{y}}<extra></extra>",
    )

    overall = data["overall"]
    if overall.get("count"):
        mean = overall.get("avg", 0.0)
        fig.add_shape(
            type="line",
            x0=mean,
            x1=mean,
            y0=0,
            y1=max(counts) * 1.05 if counts else 1,
            line={"color": colors["accent"], "width": 2, "dash": "dash"},
        )
        fig.add_annotation(
            x=mean,
            y=max(counts) * 1.05 if counts else 1,
            text=f"среднее {mean:.2f} {unit}".strip(),
            showarrow=False,
            font={"size": 10, "color": colors["accent"]},
            xanchor="left",
            yanchor="bottom",
        )

    layout = _layout(theme, height=340, show_legend=False)
    layout["bargap"] = 0.05
    fig.update_layout(**layout)
    fig.update_xaxes(title_text=unit or None)
    fig.update_yaxes(title_text="Эпизодов")
    _axes(fig, theme)
    return _to_dict(fig)


def categorical_figure(data: dict[str, Any], theme: str = "light") -> dict[str, Any]:
    """Столбцы распределения категорий: стопкой по периодам или рейтингом."""
    series = data["series"]
    labels = data["labels"]
    granularity = data["granularity"]

    fig = go.Figure()
    if granularity == "all":
        ordered = sorted(series, key=lambda item: item["total"])
        names = [item["name"] for item in ordered]
        totals = [item["total"] for item in ordered]
        fig.add_bar(
            x=totals,
            y=names,
            orientation="h",
            marker={"color": _theme(theme)["bar"], "line": {"width": 0}},
            hovertemplate="<b>%{y}</b><br>эпизодов: %{x}<extra></extra>",
            text=[str(value) for value in totals],
            textposition="outside",
            cliponaxis=False,
        )
        height = max(300, min(560, 90 + 30 * len(names)))
        layout = _layout(theme, height=height, show_legend=False)
        fig.update_layout(**layout)
        fig.update_xaxes(title_text="Эпизодов")
        fig.update_yaxes(showgrid=False)
        _axes(fig, theme)
        return _to_dict(fig)

    for index, item in enumerate(series):
        fig.add_bar(
            x=labels,
            y=item["values"],
            name=item["name"],
            marker={"color": PALETTE[index % len(PALETTE)], "line": {"width": 0}},
            hovertemplate=f"<b>%{{x}}</b><br>{item['name']}: %{{y}}<extra></extra>",
        )

    layout = _layout(theme, height=360, show_legend=True)
    layout["barmode"] = "stack"
    layout["bargap"] = 0.3
    fig.update_layout(**layout)
    fig.update_yaxes(title_text="Эпизодов")
    _axes(fig, theme)
    return _to_dict(fig)


def build_figure(data: dict[str, Any], theme: str = "light") -> dict[str, Any]:
    """Выбирает тип визуализации по виду данных."""
    kind = data.get("kind")
    if kind == "histogram":
        return histogram_figure(data, theme)
    if kind == "categorical":
        return categorical_figure(data, theme)
    return numeric_figure(data, theme)
