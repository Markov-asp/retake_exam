"""Тесты импорта, агрегаций и KPI."""

from __future__ import annotations

import pytest

from src.services import aggregator
from src.services.database import connect, init_db
from src.services.ingest import import_report
from src.services.repository import Filters, fetch_page, numeric_histogram, numeric_series


@pytest.fixture()
def conn(settings, report_path):
    init_db(settings.database)
    connection = connect(settings.database)
    result = import_report(connection, report_path)
    connection.commit()
    assert result.report["details_rows"] == 5
    assert result.report["trackers_rows"] == 4
    yield connection
    connection.close()


def test_numeric_series_by_day(conn):
    rows = numeric_series(conn, "details", "fps", "day", "avg", Filters())
    assert [row["n"] for row in rows] == [3, 2]
    assert rows[0]["period"] == "2026-09-01"
    assert rows[0]["value"] == pytest.approx((30 + 29.9 + 2200 / 73) / 3, rel=1e-3)


def test_numeric_series_by_month(conn):
    rows = numeric_series(conn, "details", "fps", "month", "sum", Filters())
    assert [row["period"] for row in rows] == ["2026-09", "2026-10"]
    assert rows[0]["n"] == 3


def test_numeric_series_all_and_filters(conn):
    rows = numeric_series(conn, "details", "fps", "all", "avg", Filters())
    assert len(rows) == 1
    assert rows[0]["n"] == 5

    filtered = numeric_series(
        conn, "details", "fps", "day", "avg", Filters(date_from="2026-10-01")
    )
    assert len(filtered) == 1
    assert filtered[0]["n"] == 2


def test_numeric_series_rejects_unknown_column(conn):
    with pytest.raises(ValueError):
        numeric_series(conn, "details", "drop table", "day", "avg", Filters())


def test_categorical_series(conn):
    rows = aggregator.categorical_data(conn, "details", _metric("details", "category"), "all", Filters())
    assert rows["kind"] == "categorical"
    assert rows["overall"]["count"] == 5
    names = {item["name"] for item in rows["categories"]}
    assert "Идеально 30 fps" in names


def test_histogram(conn):
    buckets = numeric_histogram(conn, "details", "fps", Filters(), bins=5)
    assert buckets
    assert sum(bucket["count"] for bucket in buckets) == 5


def test_positive_only_filters_zero_values(conn):
    default = numeric_series(conn, "trackers", "avg_hz", "all", "avg", Filters())
    positive = numeric_series(
        conn, "trackers", "avg_hz", "all", "avg", Filters(), positive=True
    )
    assert default[0]["n"] == 4
    assert positive[0]["n"] == 3
    assert positive[0]["value"] > 89


def test_period_labels():
    assert aggregator.period_label("2026-09-01", "day") == "01.09.2026"
    assert aggregator.period_label("2026-09", "month") == "сен 2026"
    assert aggregator.period_label("all", "all") == "Весь объём"


def test_plural_ru():
    assert aggregator.plural_ru(1, "эпизод", "эпизода", "эпизодов") == "эпизод"
    assert aggregator.plural_ru(2, "эпизод", "эпизода", "эпизодов") == "эпизода"
    assert aggregator.plural_ru(5, "эпизод", "эпизода", "эпизодов") == "эпизодов"
    assert aggregator.plural_ru(11, "эпизод", "эпизода", "эпизодов") == "эпизодов"


def test_build_kpis(conn):
    cards = {card["id"]: card for card in aggregator.build_kpis(conn, Filters())}
    assert cards["episodes"]["value"] == 5
    assert cards["days"]["value"] == 2
    assert cards["fps"]["display"] == "29,01"
    assert cards["tracking_hz"]["display"] == "89,96"
    assert cards["problems"]["value"] == pytest.approx(40.0)


def test_table_search_and_pagination(conn):
    page = fetch_page(conn, "details", Filters(search="PT_004"), limit=10, offset=0)
    assert len(page) == 1
    assert page[0]["episode"] == "PT_004"

    page = fetch_page(conn, "details", Filters(), limit=2, offset=0, sort="fps", order="asc")
    assert len(page) == 2
    assert page[0]["fps"] <= page[1]["fps"]


def _metric(sheet: str, key: str):
    from src.services.catalog import get_metric

    return get_metric(sheet, key)
