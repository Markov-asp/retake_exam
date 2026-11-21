"""Генератор демонстрационного отчёта на несколько месяцев.

Скрипт создаёт синтетический .xlsx с теми же листами и колонками, что и
реальный отчёт («Детали», «Трекеры», «Сводка»). Он нужен, чтобы проверить
агрегации по дням и месяцам на объёме, превышающем один съёмочный день.

Пример:
    python scripts/generate_demo_report.py --output data/raw/demo_report_90d.xlsx
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

DETAIL_HEADERS = [
    "Дата",
    "Сетап",
    "Сценарий",
    "Эпизод",
    "Камера/роль",
    "Устройство",
    "Файл",
    "Разрешение",
    "Кодек",
    "Битрейт, Мбит/с",
    "r_frame_rate",
    "FPS факт.",
    "Кадров",
    "Длит.",
    "«Плохих» интерв.",
    "«Плохих» интерв., %",
    "Макс. разрыв, мс",
    "Категория",
]

TRACKER_HEADERS = [
    "Дата",
    "Сетап",
    "Сценарий",
    "Эпизод",
    "Файл",
    "Точек",
    "Длит.",
    "Ср. Гц",
    "Старт, Гц",
    "Середина, Гц",
    "Конец, Гц",
    "Равномерность, %",
    "Пропусков",
    "Макс. разрыв, мс",
    "Категория",
]

DEVICES = [("pico_headset", "Pico"), ("pico_headset", "Pico"), ("quest3", "Meta Quest 3")]
RESOLUTIONS = ["2160x810", "2160x810", "1920x1080", "3840x1920"]
CODECS = ["h264", "h264", "hevc"]


def human_duration(seconds: int) -> str:
    """Форматирует секунды как «1м 14с»."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}м {secs:02d}с"


def pick(seq, rng: random.Random):
    return seq[rng.randrange(len(seq))]


def build_rows(days: int, per_day: int, start: date, seed: int) -> tuple[list, list]:
    rng = random.Random(seed)
    details: list[list] = []
    trackers: list[list] = []
    episode = 0
    current = start
    generated = 0

    while generated < days:
        # Пропускаем часть выходных — так датасет выглядит как реальный график съёмок.
        if current.weekday() >= 5 and rng.random() < 0.7:
            current += timedelta(days=1)
            continue

        count = max(2, per_day + rng.randint(-2, 2))
        for index in range(count):
            episode += 1
            moment = datetime(current.year, current.month, current.day, 9, 0, 0) + timedelta(
                minutes=18 * index + rng.randint(0, 6), seconds=rng.randint(0, 59)
            )
            duration = rng.randint(58, 96)
            anomaly = rng.random()

            if anomaly < 0.05:
                fps = 25.0
                frames = int(round(fps * duration))
                bad_intervals = rng.randint(30, 120)
                category = "25 fps"
                r_frame_rate = "25/1"
            elif anomaly < 0.16:
                fps = round(rng.uniform(29.2, 29.8), 2)
                frames = int(round(fps * duration))
                bad_intervals = rng.randint(3, 24)
                category = "~30 fps, редкие пропуски"
                r_frame_rate = "30/1"
            else:
                fps = round(rng.uniform(29.95, 30.05), 2)
                frames = int(round(fps * duration))
                bad_intervals = 0
                category = "Идеально 30 fps"
                r_frame_rate = "30/1"

            bad_pct = round(bad_intervals / frames * 100, 2) if bad_intervals else 0.0
            max_gap = round(rng.uniform(17.0, 24.0) if bad_intervals == 0 else rng.uniform(25.0, 55.0), 2)
            bitrate = round(rng.uniform(6.1, 7.4), 2)
            resolution = pick(RESOLUTIONS, rng)
            codec = pick(CODECS, rng)
            camera, device = pick(DEVICES, rng)
            name = f"CameraRecord_{moment:%Y%m%d_%H%M%S}.mp4"

            details.append(
                [
                    current.strftime("%d.%m.%Y"),
                    "PT",
                    "SCN-task",
                    f"PT_{episode:03d}",
                    camera,
                    device,
                    name,
                    resolution,
                    codec,
                    bitrate,
                    r_frame_rate,
                    fps,
                    frames,
                    human_duration(duration),
                    bad_intervals,
                    bad_pct,
                    max_gap,
                    category,
                ]
            )

            tracking_missing = rng.random() < 0.03
            if tracking_missing:
                trackers.append(
                    [
                        current.strftime("%d.%m.%Y"),
                        "PT",
                        "SCN-task",
                        f"PT_{episode:03d}",
                        f"trackingData_{moment:%Y%m%d_%H%M%S}.txt",
                        0,
                        human_duration(duration),
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        "Не прочитан / битый",
                    ]
                )
                continue

            target_hz = rng.uniform(88.0, 90.05)
            points = int(round(target_hz * duration))
            avg_hz = round(points / duration, 2)
            start_hz = round(avg_hz + rng.uniform(-1.6, 1.2), 2)
            mid_hz = round(avg_hz + rng.uniform(-0.4, 0.5), 2)
            end_hz = round(avg_hz + rng.uniform(-0.7, 0.8), 2)
            gaps = 0 if rng.random() < 0.45 else rng.randint(1, 18)
            uniformity = round(100 - gaps / max(points, 1) * 100 * rng.uniform(0.7, 1.1), 2)
            uniformity = max(uniformity, 98.0)
            tracking_category = "Идеально ~90 Гц" if gaps <= 3 else "~90 Гц, редкие пропуски"
            trackers.append(
                [
                    current.strftime("%d.%m.%Y"),
                    "PT",
                    "SCN-task",
                    f"PT_{episode:03d}",
                    f"trackingData_{moment:%Y%m%d_%H%M%S}.txt",
                    points,
                    human_duration(duration),
                    avg_hz,
                    start_hz,
                    mid_hz,
                    end_hz,
                    uniformity,
                    gaps,
                    round(rng.uniform(17.0, 34.0), 2),
                    tracking_category,
                ]
            )

        generated += 1
        current += timedelta(days=1)

    return details, trackers


def write_sheet(worksheet, title: str, headers: list[str], rows: list[list]) -> None:
    worksheet.append([f"data | {title}"])
    worksheet["A1"].font = Font(bold=True, size=13, color="1F2937")
    worksheet.append(headers)

    header_fill = PatternFill("solid", fgColor="312E81")
    for cell in worksheet[2]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    for row in rows:
        worksheet.append(row)

    widths = [12, 10, 12, 12, 14, 14, 38, 12, 8, 14, 12, 10, 10, 10, 14, 16, 16, 24]
    for index, width in enumerate(widths[: len(headers)], start=1):
        worksheet.column_dimensions[chr(64 + index) if index <= 26 else "A"].width = width
    worksheet.freeze_panes = "A3"


def build_workbook(details: list[list], trackers: list[list]) -> Workbook:
    workbook = Workbook()
    details_sheet = workbook.active
    details_sheet.title = "Детали"
    write_sheet(details_sheet, "Детали", DETAIL_HEADERS, details)

    trackers_sheet = workbook.create_sheet("Трекеры")
    write_sheet(trackers_sheet, "Трекеры", TRACKER_HEADERS, trackers)

    summary = workbook.create_sheet("Сводка")
    summary.append(["data | Сводка"])
    summary["A1"].font = Font(bold=True, size=13, color="1F2937")
    summary.append([])
    summary.append(["FPS — категории"])
    summary.append(["Идеально 30 fps", sum(1 for row in details if row[17] == "Идеально 30 fps")])
    summary.append(["25 fps", sum(1 for row in details if row[17] == "25 fps")])
    summary.append(["~30 fps, редкие пропуски", sum(1 for row in details if row[17] == "~30 fps, редкие пропуски")])
    summary.append(["Битый файл", 0])
    summary.append([])
    summary.append(["Трекинг — категории"])
    summary.append(["Идеально ~90 Гц", sum(1 for row in trackers if row[14] == "Идеально ~90 Гц")])
    summary.append(["Не прочитан / битый", sum(1 for row in trackers if row[14] == "Не прочитан / битый")])
    summary.column_dimensions["A"].width = 32
    summary.column_dimensions["B"].width = 12
    return workbook


def main() -> None:
    parser = argparse.ArgumentParser(description="Генерация демонстрационного отчёта")
    parser.add_argument("--output", default="data/raw/demo_report_90d.xlsx", type=Path)
    parser.add_argument("--days", default=36, type=int, help="количество съёмочных дней")
    parser.add_argument("--per-day", default=6, type=int, help="среднее число эпизодов в день")
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--start", default="2026-09-01", help="первая дата (YYYY-MM-DD)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    details, trackers = build_rows(args.days, args.per_day, start, args.seed)
    workbook = build_workbook(details, trackers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(args.output)
    print(f"Создан {args.output}: {len(details)} эпизодов, {len(trackers)} файлов трекинга")


if __name__ == "__main__":
    main()
