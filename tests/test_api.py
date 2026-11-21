"""Тесты REST API через FastAPI TestClient."""

from __future__ import annotations

from pathlib import Path

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload(client, path: Path):
    return client.post(
        "/api/reports",
        files={"file": ("report.xlsx", path.read_bytes(), XLSX_MIME)},
        data={"title": "Тестовый отчёт"},
    )


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["reports"] == 0


def test_catalog(client):
    response = client.get("/api/catalog")
    assert response.status_code == 200
    payload = response.json()

    assert [sheet["key"] for sheet in payload["sheets"]] == ["details", "trackers"]
    details = payload["sheets"][0]
    assert len(details["columns"]) == 19
    assert len(details["metrics"]) == 14
    assert len(payload["sheets"][1]["metrics"]) == 12
    assert {item["key"] for item in payload["granularities"]} == {"day", "month", "all"}


def test_upload_list_and_duplicate(client, report_path):
    response = _upload(client, report_path)
    assert response.status_code == 201
    payload = response.json()
    assert payload["duplicate"] is False
    assert payload["report"]["details_rows"] == 5
    assert payload["report"]["trackers_rows"] == 4

    listing = client.get("/api/reports").json()
    assert listing["total"] == 1

    duplicate = _upload(client, report_path)
    assert duplicate.status_code == 201
    assert duplicate.json()["duplicate"] is True
    assert client.get("/api/reports").json()["total"] == 1


def test_upload_rejects_non_excel(client):
    response = client.post(
        "/api/reports",
        files={"file": ("report.txt", b"not excel", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_dashboard_payload(client, report_path):
    _upload(client, report_path)

    response = client.get("/api/dashboard", params={"sheet": "details", "granularity": "month"})
    assert response.status_code == 200
    payload = response.json()

    assert payload["sheet"] == "details"
    assert payload["total_rows"] == 5
    assert len(payload["kpis"]) == 8
    assert len(payload["charts"]) == 14
    assert payload["charts"][0]["metric"] == "resolution"  # группа «Видео» идёт первой
    assert payload["charts"][0]["group"] == "Видео"
    assert "data" in payload["charts"][0]["figure"]
    assert "layout" in payload["charts"][0]["figure"]

    trackers = client.get("/api/dashboard", params={"sheet": "trackers"}).json()
    assert len(trackers["charts"]) == 12


def test_dashboard_all_granularity_builds_histograms(client, report_path):
    _upload(client, report_path)
    payload = client.get("/api/dashboard", params={"granularity": "all"}).json()
    bars = [
        trace
        for chart in payload["charts"]
        for trace in chart["figure"]["data"]
        if trace["type"] == "bar"
    ]
    assert bars


def test_single_chart_endpoint(client, report_path):
    _upload(client, report_path)
    response = client.get("/api/charts/details/fps", params={"granularity": "day"})
    assert response.status_code == 200
    chart = response.json()
    assert chart["metric"] == "fps"
    assert chart["figure"]["data"][0]["type"] == "bar"


def test_chart_unknown_metric(client):
    response = client.get("/api/charts/details/unknown")
    assert response.status_code == 422


def test_table_pagination_and_search(client, report_path):
    _upload(client, report_path)

    page = client.get("/api/table/details", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 5
    assert len(page["rows"]) == 2
    assert len(page["columns"]) == 19

    found = client.get("/api/table/details", params={"search": "PT_004"}).json()
    assert found["total"] == 1
    assert found["rows"][0]["episode"] == "PT_004"

    sorted_page = client.get(
        "/api/table/details", params={"sort": "bitrate", "order": "asc", "limit": 5}
    ).json()
    values = [row["bitrate"] for row in sorted_page["rows"]]
    assert values == sorted(values)


def test_export_csv(client, report_path):
    _upload(client, report_path)
    response = client.get("/api/export/details.csv")
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    assert "Дата" in text.splitlines()[0]
    assert len(text.splitlines()) == 6  # заголовок + 5 строк


def test_export_xlsx(client, report_path):
    _upload(client, report_path)
    response = client.get("/api/export/details.xlsx")
    assert response.status_code == 200
    assert response.content[:2] == b"PK"


def test_delete_report_clears_data(client, report_path):
    report_id = _upload(client, report_path).json()["report"]["id"]

    deleted = client.delete(f"/api/reports/{report_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    assert client.get("/api/reports").json()["total"] == 0
    assert client.get("/api/dashboard").json()["total_rows"] == 0


def test_missing_report_returns_404(client):
    response = client.get("/api/reports/rep_missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "DataScope" in response.text
    assert "plotly.min.js" in response.text
