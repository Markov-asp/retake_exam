"""Общие фикстуры тестов: собранное приложение и тестовый отчёт."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_settings  # noqa: E402

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
    "Комментарий",
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

DETAIL_ROWS = [
    [
        "01.09.2026", "PT", "SCN-task", "PT_001", "pico_headset", "Pico",
        "CameraRecord_20260901_090000.mp4", "2160x810", "h264", 6.5, "30/1",
        30, 2220, "1м 14с", 0, 0, 20.0, "Идеально 30 fps", "эталон",
    ],
    [
        "01.09.2026", "PT", "SCN-task", "PT_002", "pico_headset", "Pico",
        "CameraRecord_20260901_093000.mp4", "2160x810", "h264", 6.2, "30/1",
        29.9, 2210, "1м 14с", 5, 0.23, 41.5, "~30 fps, редкие пропуски", "",
    ],
    [
        None, "PT", "SCN-task", "PT_003", "pico_headset", "Pico",
        "CameraRecord_20260901_100000.mp4", "1920x1080", "hevc", 7.1, "30/1",
        None, 2200, "1м 13с", 0, 0, 19.8, "Идеально 30 fps", "",
    ],
    [
        "02.10.2026", "PT", "SCN-task", "PT_004", "quest3", "Meta Quest 3",
        "CameraRecord_20261002_101500.mp4", "3840x1920", "h264", 6.8, "25/1",
        25, 1500, "1м 00с", 50, 3.33, 60.2, "25 fps", "",
    ],
    [
        "02.10.2026", "PT", "SCN-task", "PT_005", "quest3", "Meta Quest 3",
        "CameraRecord_20261002_103000.mp4", "2160x810", "h264", 6.4, "30/1",
        30, 2250, "1м 15с", 0, 0, 20.5, "Идеально 30 fps", "повтор",
    ],
]

TRACKER_ROWS = [
    ["01.09.2026", "PT", "SCN-task", "PT_001", "trackingData_20260901_090000.txt", 6697, "1м 14с", 89.94, 87.3, 90.1, 90.0, 100.0, 0, 21.2, "Идеально ~90 Гц"],
    ["01.09.2026", "PT", "SCN-task", "PT_002", "trackingData_20260901_093000.txt", 6672, "1м 14с", 89.93, 86.8, 90.0, 90.0, 99.99, 1, 23.0, "Идеально ~90 Гц"],
    ["02.10.2026", "PT", "SCN-task", "PT_004", "trackingData_20261002_101500.txt", 5400, "1м 00с", 90.0, 88.0, 90.0, 90.0, 99.5, 12, 30.5, "~90 Гц, редкие пропуски"],
    ["02.10.2026", "PT", "SCN-task", "PT_005", "trackingData_20261002_103000.txt", 0, "1м 15с", 0, 0, 0, 0, 0, 0, 0, "Не прочитан / битый"],
]


def build_report(path: Path, *, detail_rows=None, tracker_rows=None) -> Path:
    """Создаёт тестовый .xlsx с листами «Детали», «Трекеры» и «Сводка»."""
    workbook = Workbook()
    details = workbook.active
    details.title = "Детали"
    details.append(["data | Детали"])
    details.append(DETAIL_HEADERS)
    for row in detail_rows if detail_rows is not None else DETAIL_ROWS:
        details.append(row)
    details.append([None] * len(DETAIL_HEADERS))  # пустая строка должна быть пропущена

    trackers = workbook.create_sheet("Трекеры")
    trackers.append(["data | Трекеры"])
    trackers.append(TRACKER_HEADERS)
    for row in tracker_rows if tracker_rows is not None else TRACKER_ROWS:
        trackers.append(row)

    summary = workbook.create_sheet("Сводка")
    summary.append(["data | Сводка"])
    summary.append(["Идеально 30 fps", 3])

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


@pytest.fixture()
def settings(tmp_path):
    return load_settings(data_dir=tmp_path, auto_seed=False)


@pytest.fixture()
def report_path(tmp_path):
    return build_report(tmp_path / "report.xlsx")


@pytest.fixture()
def client(settings):
    from fastapi.testclient import TestClient

    from src.main import create_app

    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client
