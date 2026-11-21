"""Репозиторий: SQL-запросы к отчётам, записям и агрегатам.

Все идентификаторы таблиц и колонок проходят через белые списки,
значения передаются только параметрами — это исключает SQL-инъекции.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

SHEET_TABLES: dict[str, str] = {"details": "details", "trackers": "trackers"}

AGGREGATIONS: dict[str, str] = {
    "avg": "AVG",
    "sum": "SUM",
    "min": "MIN",
    "max": "MAX",
}

GRANULARITIES: dict[str, str] = {
    "day": "date",
    "month": "substr(date, 1, 7)",
    "all": "'all'",
}

_REPORT_FIELDS = (
    "id",
    "title",
    "filename",
    "uploaded_at",
    "size_bytes",
    "sha256",
    "details_rows",
    "trackers_rows",
    "skipped_rows",
    "status",
    "message",
)


def table_for(sheet: str) -> str:
    """Возвращает имя таблицы для листа отчёта."""
    try:
        return SHEET_TABLES[sheet]
    except KeyError as exc:  # pragma: no cover - защита от опечаток
        raise ValueError(f"Неизвестный лист: {sheet!r}") from exc


@dataclass(frozen=True)
class Filters:
    """Набор фильтров, применяемых к выборкам."""

    report_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    search: str | None = None


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped.lower()}%"


def _where(filters: Filters, extra: Sequence[str] = ()) -> tuple[str, list[Any]]:
    """Собирает SQL-условие и параметры для фильтров."""
    clauses: list[str] = []
    params: list[Any] = []

    if filters.report_id:
        clauses.append("report_id = ?")
        params.append(filters.report_id)
    if filters.date_from:
        clauses.append("date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        clauses.append("date <= ?")
        params.append(filters.date_to)
    if filters.search:
        clauses.append("search_text LIKE ? ESCAPE '\\'")
        params.append(_like(filters.search))

    clauses.extend(extra)
    sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return sql, params


def where_clause(filters: Filters, extra: Sequence[str] = ()) -> tuple[str, list[Any]]:
    """Публичный построитель условий для сервисных запросов."""
    return _where(filters, extra)


# --------------------------------------------------------------------------- #
# Отчёты
# --------------------------------------------------------------------------- #
def insert_report(conn: sqlite3.Connection, report: dict[str, Any]) -> None:
    """Регистрирует отчёт в таблице ``reports``."""
    columns = ", ".join(_REPORT_FIELDS)
    placeholders = ", ".join("?" for _ in _REPORT_FIELDS)
    conn.execute(
        f"INSERT INTO reports ({columns}) VALUES ({placeholders})",
        [report.get(field) for field in _REPORT_FIELDS],
    )


def update_report_status(conn: sqlite3.Connection, report_id: str, status: str, message: str | None = None) -> None:
    """Обновляет статус обработки отчёта."""
    conn.execute(
        "UPDATE reports SET status = ?, message = ? WHERE id = ?",
        (status, message, report_id),
    )


def update_report_counts(
    conn: sqlite3.Connection,
    report_id: str,
    details_rows: int,
    trackers_rows: int,
    skipped_rows: int,
) -> None:
    """Фиксирует количество разобранных строк."""
    conn.execute(
        "UPDATE reports SET details_rows = ?, trackers_rows = ?, skipped_rows = ? WHERE id = ?",
        (details_rows, trackers_rows, skipped_rows, report_id),
    )


def find_report_by_hash(conn: sqlite3.Connection, sha256: str) -> dict[str, Any] | None:
    """Ищет уже загруженный отчёт по контрольной сумме."""
    row = conn.execute("SELECT * FROM reports WHERE sha256 = ?", (sha256,)).fetchone()
    return dict(row) if row else None


def get_report(conn: sqlite3.Connection, report_id: str) -> dict[str, Any] | None:
    """Возвращает отчёт по идентификатору."""
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def list_reports(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Список отчётов от новых к старым."""
    rows = conn.execute("SELECT * FROM reports ORDER BY uploaded_at DESC").fetchall()
    return [dict(row) for row in rows]


def delete_report(conn: sqlite3.Connection, report_id: str) -> bool:
    """Удаляет отчёт вместе со строками (каскадно)."""
    cursor = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    return cursor.rowcount > 0


def count_reports(conn: sqlite3.Connection) -> int:
    """Общее количество загруженных отчётов."""
    row = conn.execute("SELECT COUNT(*) AS n FROM reports").fetchone()
    return int(row["n"]) if row else 0


# --------------------------------------------------------------------------- #
# Записи
# --------------------------------------------------------------------------- #
def insert_rows(conn: sqlite3.Connection, table: str, rows: Iterable[dict[str, Any]]) -> int:
    """Пакетно вставляет нормализованные строки отчёта."""
    rows = list(rows)
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    payload = [tuple(row.get(column) for column in columns) for row in rows]
    conn.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        payload,
    )
    return len(payload)


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Колонки таблицы (для проверки сортировки)."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row["name"] for row in rows]


def count_rows(conn: sqlite3.Connection, sheet: str, filters: Filters) -> int:
    """Количество записей листа с учётом фильтров."""
    table = table_for(sheet)
    where, params = _where(filters)
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}{where}", params).fetchone()
    return int(row["n"]) if row else 0


def fetch_page(
    conn: sqlite3.Connection,
    sheet: str,
    filters: Filters,
    *,
    limit: int = 50,
    offset: int = 0,
    sort: str | None = None,
    order: str = "desc",
    columns: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Страница записей листа с сортировкой и поиском."""
    table = table_for(sheet)
    allowed = set(table_columns(conn, table))
    order = "ASC" if str(order).lower() == "asc" else "DESC"
    sort_column = sort if sort in allowed else "date"
    if sort_column == "date":
        order = "DESC" if order == "DESC" else "ASC"

    where, params = _where(filters)
    select_columns = [column for column in (columns or allowed) if column in allowed]
    if not select_columns:
        select_columns = sorted(allowed)
    sql = (
        f"SELECT {', '.join(select_columns)} FROM {table}{where} "
        f"ORDER BY {sort_column} {order}, row_index ASC LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, [*params, max(1, limit), max(0, offset)]).fetchall()
    result = []
    for row in rows:
        record = dict(row)
        extra = record.pop("extra", None)
        record.pop("search_text", None)
        if extra:
            try:
                record["extra"] = json.loads(extra)
            except (TypeError, ValueError):
                record["extra"] = {}
        result.append(record)
    return result


def iter_records(
    conn: sqlite3.Connection,
    sheet: str,
    filters: Filters,
    *,
    columns: Sequence[str] | None = None,
    batch_size: int = 1000,
):
    """Потоково перебирает записи листа (для экспорта без нагрузки на память)."""
    table = table_for(sheet)
    allowed = set(table_columns(conn, table))
    select_columns = [column for column in (columns or sorted(allowed)) if column in allowed]
    if not select_columns:
        select_columns = sorted(allowed)

    where, params = _where(filters)
    sql = (
        f"SELECT {', '.join(select_columns)} FROM {table}{where} "
        f"ORDER BY date ASC, row_index ASC"
    )
    cursor = conn.execute(sql, params)
    while True:
        batch = cursor.fetchmany(batch_size)
        if not batch:
            break
        for row in batch:
            record = dict(row)
            extra = record.pop("extra", None)
            record.pop("search_text", None)
            if extra:
                try:
                    record["extra"] = json.loads(extra)
                except (TypeError, ValueError):
                    record["extra"] = {}
            yield record


def distinct_values(conn: sqlite3.Connection, sheet: str, column: str, limit: int = 200) -> list[str]:
    """Уникальные значения колонки для фильтров интерфейса."""
    table = table_for(sheet)
    if column not in set(table_columns(conn, table)):
        return []
    rows = conn.execute(
        f"SELECT DISTINCT {column} AS value FROM {table} "
        f"WHERE {column} IS NOT NULL AND TRIM({column}) <> '' "
        f"ORDER BY value LIMIT ?",
        (limit,),
    ).fetchall()
    return [str(row["value"]) for row in rows]


# --------------------------------------------------------------------------- #
# Агрегации
# --------------------------------------------------------------------------- #
def numeric_series(
    conn: sqlite3.Connection,
    sheet: str,
    column: str,
    granularity: str,
    aggregation: str,
    filters: Filters,
    *,
    positive: bool = False,
) -> list[dict[str, Any]]:
    """Ряд значений числовой метрики по дням/месяцам или целиком."""
    table = table_for(sheet)
    if column not in set(table_columns(conn, table)):
        raise ValueError(f"Неизвестная колонка: {column!r}")
    if granularity not in GRANULARITIES:
        raise ValueError(f"Неизвестная гранулярность: {granularity!r}")
    if aggregation not in AGGREGATIONS:
        raise ValueError(f"Неизвестная агрегация: {aggregation!r}")

    period_expr = GRANULARITIES[granularity]
    agg_func = AGGREGATIONS[aggregation]
    conditions = [f"{column} IS NOT NULL"]
    if positive:
        conditions.append(f"{column} > 0")
    where, params = _where(filters, extra=conditions)

    if granularity == "all":
        sql = (
            f"SELECT {period_expr} AS period, COUNT(*) AS n, "
            f"{agg_func}({column}) AS value, AVG({column}) AS avg_value, "
            f"MIN({column}) AS min_value, MAX({column}) AS max_value, "
            f"SUM({column}) AS sum_value "
            f"FROM {table}{where}"
        )
        group_by = ""
    else:
        sql = (
            f"SELECT {period_expr} AS period, COUNT(*) AS n, "
            f"{agg_func}({column}) AS value, AVG({column}) AS avg_value, "
            f"MIN({column}) AS min_value, MAX({column}) AS max_value, "
            f"SUM({column}) AS sum_value "
            f"FROM {table}{where} GROUP BY period ORDER BY period"
        )
        group_by = "GROUP BY"

    rows = conn.execute(sql, params).fetchall()
    _ = group_by
    return [dict(row) for row in rows]


def categorical_series(
    conn: sqlite3.Connection,
    sheet: str,
    column: str,
    granularity: str,
    filters: Filters,
) -> list[dict[str, Any]]:
    """Распределение категориальной метрики по периодам."""
    table = table_for(sheet)
    if column not in set(table_columns(conn, table)):
        raise ValueError(f"Неизвестная колонка: {column!r}")
    if granularity not in GRANULARITIES:
        raise ValueError(f"Неизвестная гранулярность: {granularity!r}")

    period_expr = GRANULARITIES[granularity]
    where, params = _where(
        filters,
        extra=[f"{column} IS NOT NULL", f"TRIM({column}) <> ''"],
    )
    sql = (
        f"SELECT {period_expr} AS period, {column} AS value, COUNT(*) AS n "
        f"FROM {table}{where} GROUP BY period, {column} ORDER BY period, n DESC"
    )
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def numeric_histogram(
    conn: sqlite3.Connection,
    sheet: str,
    column: str,
    filters: Filters,
    bins: int = 20,
    *,
    positive: bool = False,
) -> list[dict[str, Any]]:
    """Гистограмма распределения, посчитанная на стороне SQLite."""
    table = table_for(sheet)
    if column not in set(table_columns(conn, table)):
        raise ValueError(f"Неизвестная колонка: {column!r}")

    conditions = [f"{column} IS NOT NULL"]
    if positive:
        conditions.append(f"{column} > 0")
    where, params = _where(filters, extra=conditions)
    stats = conn.execute(
        f"SELECT COUNT(*) AS n, MIN({column}) AS mn, MAX({column}) AS mx FROM {table}{where}",
        params,
    ).fetchone()
    if not stats or not stats["n"]:
        return []

    count, low, high = int(stats["n"]), float(stats["mn"]), float(stats["mx"])
    bins = max(5, min(int(bins), 60))
    if high <= low:
        return [{"x0": low, "x1": high, "count": count}]

    width = (high - low) / bins
    bucket = f"CAST(({column} - ?) / ? AS INTEGER)"
    rows = conn.execute(
        f"SELECT {bucket} AS bucket, COUNT(*) AS n FROM {table}{where} "
        f"GROUP BY bucket ORDER BY bucket",
        [low, width, *params],
    ).fetchall()

    result = []
    for row in rows:
        index = max(0, min(int(row["bucket"]), bins - 1))
        result.append(
            {
                "x0": round(low + index * width, 6),
                "x1": round(low + (index + 1) * width, 6),
                "count": int(row["n"]),
            }
        )
    return result


def date_bounds(conn: sqlite3.Connection, sheet: str, filters: Filters) -> tuple[str | None, str | None]:
    """Минимальная и максимальная дата в выборке."""
    table = table_for(sheet)
    where, params = _where(filters, extra=["date IS NOT NULL"])
    row = conn.execute(
        f"SELECT MIN(date) AS mn, MAX(date) AS mx FROM {table}{where}", params
    ).fetchone()
    if not row:
        return None, None
    return row["mn"], row["mx"]


def scalar(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    """Выполняет запрос и возвращает первое значение первой строки."""
    row = conn.execute(sql, list(params)).fetchone()
    if row is None:
        return None
    return row[0]
