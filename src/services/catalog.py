"""Каталог метрик и листов отчёта.

Каталог — единственный источник правды о структуре отчёта: он описывает
заголовки, типы, единицы измерения, группировку для интерфейса и
допустимые агрегации. Парсер, API и графики используют его же,
поэтому новая метрика добавляется в одном месте.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from src.utils.errors import ValidationError


@dataclass(frozen=True)
class Column:
    """Описание колонки отчёта."""

    key: str
    title: str
    kind: str  # date | text | number | integer | category
    unit: str = ""
    group: str = ""
    chartable: bool = False
    aggregation: str = "avg"
    aggregations: tuple[str, ...] = ("avg", "sum", "min", "max")
    decimals: int = 2
    description: str = ""
    fmt: str = ""  # duration | percent | int | number | date | text
    positive_only: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "kind": self.kind,
            "unit": self.unit,
            "group": self.group,
            "chartable": self.chartable,
            "aggregation": self.aggregation,
            "aggregations": list(self.aggregations),
            "decimals": self.decimals,
            "description": self.description,
            "format": self.fmt,
            "positive_only": self.positive_only,
        }


@dataclass(frozen=True)
class Sheet:
    """Лист отчёта и его колонки."""

    key: str
    title: str
    table: str
    description: str
    columns: tuple[Column, ...]

    @property
    def metrics(self) -> tuple[Column, ...]:
        return tuple(column for column in self.columns if column.chartable)

    @property
    def dimension_columns(self) -> tuple[Column, ...]:
        return tuple(column for column in self.columns if not column.chartable)

    def column(self, key: str) -> Column | None:
        for column in self.columns:
            if column.key == key:
                return column
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "columns": [column.to_dict() for column in self.columns],
            "metrics": [column.to_dict() for column in self.metrics],
        }


DETAIL_COLUMNS: tuple[Column, ...] = (
    Column(
        "date",
        "Дата",
        "date",
        group="Идентификация",
        fmt="date",
        description="Дата съёмки эпизода (нормализована в ISO).",
        aliases=("дата", "date", "дата записи", "дата съемки"),
    ),
    Column(
        "setup",
        "Сетап",
        "category",
        group="Идентификация",
        chartable=True,
        description="Исследовательский сетап (например, PT).",
        aliases=("сетап", "setup", "проект"),
    ),
    Column(
        "scenario",
        "Сценарий",
        "category",
        group="Идентификация",
        chartable=True,
        description="Сценарий записи (например, SCN-task).",
        aliases=("сценарий", "scenario", "сценарии"),
    ),
    Column(
        "episode",
        "Эпизод",
        "text",
        group="Идентификация",
        description="Идентификатор эпизода (PT_001).",
        aliases=("эпизод", "episode", "ид эпизода"),
    ),
    Column(
        "camera_role",
        "Камера / роль",
        "category",
        group="Идентификация",
        chartable=True,
        description="Роль камеры в сетапе.",
        aliases=("камера роль", "камера", "роль камеры", "camera role"),
    ),
    Column(
        "device",
        "Устройство",
        "category",
        group="Идентификация",
        chartable=True,
        description="Устройство записи.",
        aliases=("устройство", "device", "девайс"),
    ),
    Column(
        "file",
        "Файл",
        "text",
        group="Идентификация",
        description="Имя исходного видеофайла.",
        aliases=("файл", "file", "имя файла", "название файла"),
    ),
    Column(
        "resolution",
        "Разрешение",
        "category",
        group="Видео",
        chartable=True,
        description="Разрешение кадра, WxH.",
        aliases=("разрешение", "resolution"),
    ),
    Column(
        "codec",
        "Кодек",
        "category",
        group="Видео",
        chartable=True,
        description="Кодек видео (h264, hevc, ...).",
        aliases=("кодек", "codec"),
    ),
    Column(
        "bitrate",
        "Битрейт",
        "number",
        unit="Мбит/с",
        group="Видео",
        chartable=True,
        decimals=2,
        fmt="number",
        description="Средний битрейт видеопотока.",
        aliases=("битрейт мбит с", "битрейт", "bitrate", "битрейт мбит"),
    ),
    Column(
        "r_frame_rate",
        "r_frame_rate",
        "text",
        group="Видео",
        description="Исходная дробь частоты кадров из контейнера (30/1).",
        aliases=("r frame rate", "r framerate", "r frame rate value"),
    ),
    Column(
        "fps",
        "FPS фактический",
        "number",
        unit="fps",
        group="Видео",
        chartable=True,
        decimals=2,
        fmt="number",
        description="Фактическая частота кадров, рассчитанная по кадрам и длительности.",
        aliases=("fps факт", "fps", "fps фактический", "частота кадров"),
    ),
    Column(
        "frames",
        "Кадров",
        "integer",
        unit="кадров",
        group="Видео",
        chartable=True,
        aggregation="avg",
        decimals=0,
        fmt="int",
        description="Количество кадров в файле.",
        aliases=("кадров", "кадры", "frames", "количество кадров"),
    ),
    Column(
        "duration_text",
        "Длительность",
        "text",
        group="Время",
        description="Длительность в человекочитаемом виде (1м 14с).",
        aliases=("длит", "длительность", "duration", "длит."),
    ),
    Column(
        "duration_sec",
        "Длительность, с",
        "number",
        unit="с",
        group="Время",
        chartable=True,
        decimals=1,
        fmt="duration",
        description="Длительность эпизода в секундах (для расчётов и графиков).",
        aliases=(),
    ),
    Column(
        "bad_intervals",
        "«Плохие» интервалы",
        "integer",
        unit="шт.",
        group="Качество",
        chartable=True,
        aggregation="sum",
        decimals=0,
        fmt="int",
        description="Количество интервалов с нарушением частоты кадров.",
        aliases=("плохих интерв", "плохие интервалы", "плохих интервалов", "bad intervals"),
    ),
    Column(
        "bad_intervals_pct",
        "Доля «плохих» интервалов",
        "number",
        unit="%",
        group="Качество",
        chartable=True,
        aggregation="avg",
        decimals=2,
        fmt="percent",
        description="Доля «плохих» интервалов от общего числа.",
        aliases=("плохих интерв %", "плохих интервалов %", "доля плохих", "процент плохих"),
    ),
    Column(
        "max_gap_ms",
        "Макс. разрыв",
        "number",
        unit="мс",
        group="Качество",
        chartable=True,
        decimals=2,
        fmt="number",
        description="Максимальный разрыв между кадрами.",
        aliases=("макс разрыв мс", "макс разрыв", "максимальный разрыв", "max gap мс"),
    ),
    Column(
        "category",
        "Категория",
        "category",
        group="Качество",
        chartable=True,
        description="Итоговая категория качества видео.",
        aliases=("категория", "category", "статус"),
    ),
)


TRACKER_COLUMNS: tuple[Column, ...] = (
    Column(
        "date",
        "Дата",
        "date",
        group="Идентификация",
        fmt="date",
        description="Дата записи трекинга.",
        aliases=("дата", "date", "дата записи"),
    ),
    Column(
        "setup",
        "Сетап",
        "category",
        group="Идентификация",
        chartable=True,
        description="Исследовательский сетап.",
        aliases=("сетап", "setup", "проект"),
    ),
    Column(
        "scenario",
        "Сценарий",
        "category",
        group="Идентификация",
        chartable=True,
        description="Сценарий записи.",
        aliases=("сценарий", "scenario"),
    ),
    Column(
        "episode",
        "Эпизод",
        "text",
        group="Идентификация",
        description="Идентификатор эпизода.",
        aliases=("эпизод", "episode"),
    ),
    Column(
        "file",
        "Файл",
        "text",
        group="Идентификация",
        description="Имя файла телеметрии трекинга.",
        aliases=("файл", "file", "имя файла"),
    ),
    Column(
        "points",
        "Точек трекинга",
        "integer",
        unit="точек",
        group="Трекинг",
        chartable=True,
        aggregation="avg",
        decimals=0,
        fmt="int",
        positive_only=True,
        description="Количество точек в файле трекинга.",
        aliases=("точек", "точек трекинга", "points", "кол во точек"),
    ),
    Column(
        "duration_text",
        "Длительность",
        "text",
        group="Время",
        description="Длительность в человекочитаемом виде.",
        aliases=("длит", "длительность", "duration"),
    ),
    Column(
        "duration_sec",
        "Длительность, с",
        "number",
        unit="с",
        group="Время",
        chartable=True,
        decimals=1,
        fmt="duration",
        description="Длительность эпизода в секундах.",
    ),
    Column(
        "avg_hz",
        "Средняя частота",
        "number",
        unit="Гц",
        group="Трекинг",
        chartable=True,
        decimals=2,
        fmt="number",
        positive_only=True,
        description="Средняя частота обновления трекинга.",
        aliases=("ср гц", "средняя частота", "avg hz", "ср частота"),
    ),
    Column(
        "start_hz",
        "Частота в начале",
        "number",
        unit="Гц",
        group="Трекинг",
        chartable=True,
        decimals=2,
        fmt="number",
        positive_only=True,
        description="Средняя частота на первой трети записи.",
        aliases=("старт гц", "частота старт", "start hz", "старт частота"),
    ),
    Column(
        "mid_hz",
        "Частота в середине",
        "number",
        unit="Гц",
        group="Трекинг",
        chartable=True,
        decimals=2,
        fmt="number",
        positive_only=True,
        description="Средняя частота в середине записи.",
        aliases=("середина гц", "частота середина", "mid hz"),
    ),
    Column(
        "end_hz",
        "Частота в конце",
        "number",
        unit="Гц",
        group="Трекинг",
        chartable=True,
        decimals=2,
        fmt="number",
        positive_only=True,
        description="Средняя частота на последней трети записи.",
        aliases=("конец гц", "частота конец", "end hz"),
    ),
    Column(
        "uniformity",
        "Равномерность",
        "number",
        unit="%",
        group="Качество",
        chartable=True,
        decimals=2,
        fmt="percent",
        positive_only=True,
        description="Доля интервалов в пределах целевого периода.",
        aliases=("равномерность %", "равномерность", "uniformity"),
    ),
    Column(
        "gaps",
        "Пропуски",
        "integer",
        unit="шт.",
        group="Качество",
        chartable=True,
        aggregation="sum",
        decimals=0,
        fmt="int",
        description="Количество пропущенных точек трекинга.",
        aliases=("пропусков", "пропуски", "gaps"),
    ),
    Column(
        "max_gap_ms",
        "Макс. разрыв",
        "number",
        unit="мс",
        group="Качество",
        chartable=True,
        decimals=2,
        fmt="number",
        description="Максимальный разрыв между точками.",
        aliases=("макс разрыв мс", "макс разрыв", "максимальный разрыв"),
    ),
    Column(
        "category",
        "Категория",
        "category",
        group="Качество",
        chartable=True,
        description="Итоговая категория качества трекинга.",
        aliases=("категория", "category", "статус"),
    ),
)


SHEETS: dict[str, Sheet] = {
    "details": Sheet(
        key="details",
        title="Детали",
        table="details",
        description="Технические характеристики видеофайлов.",
        columns=DETAIL_COLUMNS,
    ),
    "trackers": Sheet(
        key="trackers",
        title="Трекеры",
        table="trackers",
        description="Параметры телеметрии трекинга.",
        columns=TRACKER_COLUMNS,
    ),
}

DEFAULT_METRICS: dict[str, str] = {"details": "fps", "trackers": "avg_hz"}

GRANULARITY_TITLES: dict[str, str] = {
    "day": "По дням",
    "month": "По месяцам",
    "all": "Весь объём",
}

AGGREGATION_TITLES: dict[str, str] = {
    "avg": "Среднее",
    "sum": "Сумма",
    "min": "Минимум",
    "max": "Максимум",
}


def get_sheet(sheet: str) -> Sheet:
    """Возвращает описание листа или возбуждает ValidationError."""
    try:
        return SHEETS[sheet]
    except KeyError as exc:
        raise ValidationError(f"Неизвестный лист: {sheet!r}") from exc


def get_metric(sheet: str, metric: str) -> Column:
    """Возвращает метрику листа или возбуждает ValidationError."""
    column = get_sheet(sheet).column(metric)
    if column is None or not column.chartable:
        raise ValidationError(f"Метрика {metric!r} недоступна на листе {sheet!r}")
    return column


def all_metrics() -> Iterable[Column]:
    """Все метрики всех листов (для документации и тестов)."""
    for sheet in SHEETS.values():
        yield from sheet.metrics
