"""Импорт отчёта в базу сервиса без запуска HTTP-сервера.

Пример:
    python scripts/ingest_report.py data/raw/data_detail-report.xlsx
    python scripts/ingest_report.py report.xlsx --title "PT — октябрь"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.config import load_settings
from src.services.database import init_db, session
from src.services.ingest import import_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт Excel-отчёта в базу DataScope")
    parser.add_argument("path", type=Path, help="путь к файлу .xlsx")
    parser.add_argument("--title", default=None, help="название отчёта")
    parser.add_argument("--data-dir", default=None, help="каталог данных (по умолчанию ./data)")
    args = parser.parse_args()

    if not args.path.is_file():
        raise SystemExit(f"Файл не найден: {args.path}")

    settings = load_settings(data_dir=Path(args.data_dir)) if args.data_dir else load_settings()
    settings.ensure_directories()
    init_db(settings.database)

    with session(settings.database) as conn:
        result = import_report(conn, args.path, title=args.title)

    report = result.report
    status = "уже был загружен" if result.duplicate else "импортирован"
    print(f"Отчёт {report['id']} {status}")
    print(f"  Детали:  {report['details_rows']} строк")
    print(f"  Трекеры: {report['trackers_rows']} строк")
    print(f"  База:    {settings.database}")


if __name__ == "__main__":
    main()
