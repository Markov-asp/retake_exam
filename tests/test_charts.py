"""Тесты построения Plotly-фигур."""

from __future__ import annotations

import json

from src.services.charts import build_figure, categorical_figure, histogram_figure, numeric_figure


def _numeric():
    return {
        "kind": "numeric",
        "granularity": "day",
        "aggregation": "avg",
        "metric": {"title": "FPS", "unit": "fps"},
        "periods": ["2026-09-01", "2026-09-02"],
        "labels": ["01.09.2026", "02.09.2026"],
        "values": [30.0, 29.5],
        "counts": [3, 2],
        "mins": [29.0, 28.0],
        "maxs": [31.0, 30.0],
        "overall": {"count": 5, "value": 29.8, "avg": 29.8, "min": 28.0, "max": 31.0, "sum": 149.0},
    }


def _categorical():
    return {
        "kind": "categorical",
        "granularity": "all",
        "metric": {"title": "Кодек", "unit": ""},
        "periods": ["all"],
        "labels": ["Весь объём"],
        "series": [
            {"name": "h264", "total": 4, "values": [4]},
            {"name": "hevc", "total": 1, "values": [1]},
        ],
        "categories": [{"name": "h264", "count": 4}, {"name": "hevc", "count": 1}],
        "overall": {"count": 5, "unique": 2},
    }


def _histogram():
    return {
        "kind": "histogram",
        "granularity": "all",
        "metric": {"title": "FPS", "unit": "fps"},
        "bins": [
            {"x0": 28.0, "x1": 29.0, "count": 1},
            {"x0": 29.0, "x1": 30.0, "count": 2},
            {"x0": 30.0, "x1": 31.0, "count": 2},
        ],
        "overall": {"count": 5, "avg": 29.8, "min": 28.0, "max": 31.0},
    }


def test_numeric_figure_has_bars_and_count_line():
    figure = numeric_figure(_numeric(), "light")
    assert len(figure["data"]) == 2
    assert figure["data"][0]["type"] == "bar"
    assert figure["data"][0]["error_y"]["type"] == "data"
    assert figure["data"][1]["yaxis"] == "y2"
    assert figure["layout"]["height"] == 340
    json.dumps(figure)


def test_numeric_figure_theme_changes_font_color():
    light = numeric_figure(_numeric(), "light")
    dark = numeric_figure(_numeric(), "dark")
    assert light["layout"]["font"]["color"] != dark["layout"]["font"]["color"]


def test_numeric_figure_handles_missing_values():
    data = _numeric()
    data["values"] = [None, 29.5]
    data["mins"] = [None, 28.0]
    data["maxs"] = [None, 30.0]
    figure = numeric_figure(data, "light")
    assert figure["data"][0]["y"] == [None, 29.5]


def test_histogram_figure_draws_mean_line():
    figure = histogram_figure(_histogram(), "light")
    assert figure["data"][0]["type"] == "bar"
    assert figure["layout"]["shapes"][0]["type"] == "line"
    assert "среднее" in figure["layout"]["annotations"][0]["text"]


def test_categorical_all_is_horizontal():
    figure = categorical_figure(_categorical(), "light")
    assert figure["data"][0]["orientation"] == "h"
    assert figure["layout"]["showlegend"] is False


def test_categorical_by_period_is_stacked():
    data = _categorical()
    data["granularity"] = "day"
    data["periods"] = ["2026-09-01", "2026-09-02"]
    data["labels"] = ["01.09.2026", "02.09.2026"]
    data["series"] = [
        {"name": "h264", "total": 4, "values": [3, 1]},
        {"name": "hevc", "total": 1, "values": [0, 1]},
    ]
    figure = categorical_figure(data, "dark")
    assert figure["layout"]["barmode"] == "stack"
    assert len(figure["data"]) == 2


def test_build_figure_dispatches_by_kind():
    assert build_figure(_histogram())["data"][0]["type"] == "bar"
    assert build_figure(_categorical())["data"][0]["orientation"] == "h"
    assert build_figure(_numeric())["data"][0]["type"] == "bar"
