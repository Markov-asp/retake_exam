"""Слой хранения: подключение к SQLite и схема данных.

Схема нормализована: каждая строка отчёта превращается в запись таблицы
``details`` или ``trackers``. Такой подход позволяет агрегировать миллионы
строк средствами SQL, не загружая весь отчёт в память.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    filename      TEXT NOT NULL,
    uploaded_at   TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    sha256        TEXT,
    details_rows  INTEGER NOT NULL DEFAULT 0,
    trackers_rows INTEGER NOT NULL DEFAULT 0,
    skipped_rows  INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'ready',
    message       TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_sha256 ON reports (sha256);
CREATE INDEX IF NOT EXISTS idx_reports_uploaded ON reports (uploaded_at DESC);

CREATE TABLE IF NOT EXISTS details (
    report_id          TEXT NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
    row_index          INTEGER NOT NULL,
    date               TEXT,
    started_at         TEXT,
    setup              TEXT,
    scenario           TEXT,
    episode            TEXT,
    camera_role        TEXT,
    device             TEXT,
    file               TEXT,
    resolution         TEXT,
    codec              TEXT,
    bitrate            REAL,
    r_frame_rate       TEXT,
    fps                REAL,
    frames             INTEGER,
    duration_text      TEXT,
    duration_sec       REAL,
    bad_intervals      INTEGER,
    bad_intervals_pct  REAL,
    max_gap_ms         REAL,
    category           TEXT,
    extra              TEXT,
    search_text        TEXT,
    PRIMARY KEY (report_id, row_index)
);

CREATE TABLE IF NOT EXISTS trackers (
    report_id     TEXT NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
    row_index     INTEGER NOT NULL,
    date          TEXT,
    started_at    TEXT,
    setup         TEXT,
    scenario      TEXT,
    episode       TEXT,
    file          TEXT,
    points        INTEGER,
    duration_text TEXT,
    duration_sec  REAL,
    avg_hz        REAL,
    start_hz      REAL,
    mid_hz        REAL,
    end_hz        REAL,
    uniformity   REAL,
    gaps          INTEGER,
    max_gap_ms    REAL,
    category      TEXT,
    extra         TEXT,
    search_text   TEXT,
    PRIMARY KEY (report_id, row_index)
);

CREATE INDEX IF NOT EXISTS idx_details_date ON details (date);
CREATE INDEX IF NOT EXISTS idx_details_report ON details (report_id);
CREATE INDEX IF NOT EXISTS idx_details_category ON details (category);
CREATE INDEX IF NOT EXISTS idx_trackers_date ON trackers (date);
CREATE INDEX IF NOT EXISTS idx_trackers_report ON trackers (report_id);
CREATE INDEX IF NOT EXISTS idx_trackers_category ON trackers (category);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Открывает соединение с нужными PRAGMA."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def init_db(db_path: Path | str) -> None:
    """Создаёт схему при первом запуске и обновляет версию."""
    with session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


@contextmanager
def session(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """Контекстный менеджер соединения с автоматическим коммитом."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
