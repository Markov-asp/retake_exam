"""Нормализация заголовков и значений отчёта.

Отчёты выгружаются из разных версий конвейера, поэтому заголовки могут
отличаться регистром, кавычками и пунктуацией. Модуль приводит заголовки
к каноническим ключам каталога и разбирает значения в типизированный вид.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from typing import Any

from src.services.catalog import Column, Sheet

_DATE_FORMATS = (
    "%d.%m.%Y",
    "%d.%m.%y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d %m %Y",
)

_EMPTY_MARKERS = {"", "-", "—", "–", "n/a", "na", "нет", "none", "null", "nan"}

_DURATION_TOKEN = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>мс|ч|час[а-я]*|мин[а-я]*|м|с|сек[а-я]*)",
    re.IGNORECASE,
)
_CLOCK_DURATION = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})(?:[.,]\d+)?\s*$")
_FILENAME_STAMP = re.compile(r"(?P<date>\d{8})[_T-](?P<time>\d{6})")
_ISO_STAMP = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})[T_ ](?P<time>\d{2}[-:]\d{2}[-:]\d{2})"
)


def normalize_header(value: Any) -> str:
    """Приводит заголовок к сравнимому виду.

    ``«Плохих» интерв., %`` → ``плохих интерв %``;
    ``r_frame_rate`` → ``r frame rate``.
    """
    if value is None:
        return ""
    text = str(value).replace("\ufeff", " ").replace("ё", "е").replace("Ё", "Е")
    text = text.lower()
    text = re.sub(r"[^0-9a-zа-я%]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: Any) -> str | None:
    """Очищает строковое значение, пустые маркеры превращает в ``None``."""
    if value is None:
        return None
    text = str(value).replace("\ufeff", " ").replace("\xa0", " ").strip()
    if text.lower() in _EMPTY_MARKERS:
        return None
    return text or None


def parse_number(value: Any) -> float | None:
    """Разбирает число с запятой, процентами и пробелами-разделителями."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    text = str(value).strip().replace("\xa0", " ").replace(" ", "")
    if not text or text.lower() in _EMPTY_MARKERS:
        return None
    text = text.replace("%", "").replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def parse_int(value: Any) -> int | None:
    """Разбирает целое число, отбрасывая дробную часть."""
    number = parse_number(value)
    if number is None:
        return None
    return int(round(number))


def parse_date(value: Any) -> date | None:
    """Разбирает дату из ячейки Excel или строки."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel-серийный номер даты.
        if 20000 <= float(value) <= 80000:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
        return None

    text = str(value).strip().replace("\xa0", " ")
    if not text:
        return None
    match = _ISO_STAMP.search(text)
    if match:
        try:
            return datetime.strptime(match.group("date"), "%Y-%m-%d").date()
        except ValueError:
            return None
    # Отбрасываем время, если оно приклеено через пробел.
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", text)
    if match:
        for fmt in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                continue
    return None


def parse_duration(value: Any) -> float | None:
    """Переводит ``1м 14с`` или ``01:14`` в секунды."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value >= 0 else None

    text = str(value).strip().replace("\xa0", " ")
    if not text or text.lower() in _EMPTY_MARKERS:
        return None

    clock = _CLOCK_DURATION.match(text)
    if clock:
        hours = int(clock.group(1) or 0)
        minutes = int(clock.group(2))
        seconds = int(clock.group(3))
        return float(hours * 3600 + minutes * 60 + seconds)

    total = 0.0
    found = False
    for match in _DURATION_TOKEN.finditer(text):
        found = True
        amount = float(match.group("value").replace(",", "."))
        unit = match.group("unit").lower()
        if unit.startswith("мс"):
            total += amount / 1000.0
        elif unit.startswith("ч"):
            total += amount * 3600
        elif unit.startswith("мин") or unit == "м":
            total += amount * 60
        else:
            total += amount
    if found:
        return round(total, 3)

    number = parse_number(text)
    return number


def human_duration(seconds: float | None) -> str | None:
    """Форматирует секунды в ``1ч 02м 03с`` / ``1м 14с``."""
    if seconds is None:
        return None
    total = int(round(float(seconds)))
    if total < 0:
        return None
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}ч {minutes:02d}м {secs:02d}с"
    return f"{minutes}м {secs:02d}с"


def parse_filename_stamp(filename: str | None) -> tuple[date | None, datetime | None]:
    """Извлекает дату и время из имени файла вида ``..._20261012_122228``."""
    if not filename:
        return None, None
    match = _ISO_STAMP.search(filename)
    if match:
        try:
            moment = datetime.strptime(
                f"{match.group('date')} {match.group('time').replace('-', ':')}",
                "%Y-%m-%d %H:%M:%S",
            )
            return moment.date(), moment
        except ValueError:
            pass
    match = _FILENAME_STAMP.search(filename)
    if match:
        try:
            moment = datetime.strptime(
                f"{match.group('date')}{match.group('time')}", "%Y%m%d%H%M%S"
            )
            return moment.date(), moment
        except ValueError:
            pass
    return None, None


def _alias_index(sheet: Sheet) -> dict[str, str]:
    index: dict[str, str] = {}
    for column in sheet.columns:
        index[normalize_header(column.title)] = column.key
        for alias in column.aliases:
            index[normalize_header(alias)] = column.key
    return index


def resolve_headers(
    sheet: Sheet, raw_headers: Iterable[Any]
) -> tuple[dict[int, str], dict[int, str]]:
    """Сопоставляет заголовки листа с ключами каталога.

    Возвращает два словаря: ``индекс → ключ`` и ``индекс → неизвестный заголовок``.
    """
    aliases = _alias_index(sheet)
    mapping: dict[int, str] = {}
    unknown: dict[int, str] = {}
    used: set[str] = set()

    for position, raw in enumerate(raw_headers):
        header = normalize_header(raw)
        if not header:
            continue
        key = aliases.get(header)
        if key is None:
            key = _guess_key(header, sheet, used)
        if key and key not in used:
            mapping[position] = key
            used.add(key)
        else:
            unknown[position] = clean_text(raw) or header
    return mapping, unknown


def _guess_key(header: str, sheet: Sheet, used: set[str]) -> str | None:
    """Эвристики для заголовков, которых нет в явных алиасах."""
    available = {column.key for column in sheet.columns} - used
    rules: list[tuple[tuple[str, ...], str]] = [
        (("r frame rate", "r framerate"), "r_frame_rate"),
        (("fps",), "fps"),
        (("битрейт", "bitrate"), "bitrate"),
        (("кадр", "frames"), "frames"),
        (("разрыв", "gap"), "max_gap_ms"),
        (("плох",), "bad_intervals"),
        (("равномерн", "uniformity"), "uniformity"),
        (("пропуск", "gaps"), "gaps"),
        (("точек", "points"), "points"),
        (("ср", "avg"), "avg_hz"),
        (("старт", "start"), "start_hz"),
        (("середин", "mid"), "mid_hz"),
        (("конец", "end"), "end_hz"),
        (("разрешени", "resolution"), "resolution"),
        (("кодек", "codec"), "codec"),
        (("устройств", "device"), "device"),
        (("камер", "camera"), "camera_role"),
        (("дат", "date"), "date"),
        (("эпизод", "episode"), "episode"),
        (("сценар", "scenario"), "scenario"),
        (("сетап", "setup"), "setup"),
        (("файл", "file"), "file"),
        (("длит", "duration"), "duration_text"),
        (("категор", "category"), "category"),
    ]
    for keywords, key in rules:
        if key in available and any(keyword in header for keyword in keywords):
            if "%" in header and key in {"bad_intervals", "max_gap_ms"}:
                return "bad_intervals_pct" if "bad_intervals_pct" in available else None
            return key
    return None


def value_for_column(column: Column, value: Any) -> Any:
    """Приводит значение ячейки к типу колонки."""
    if column.kind == "date":
        return parse_date(value)
    if column.kind == "number":
        return parse_number(value)
    if column.kind == "integer":
        return parse_int(value)
    return clean_text(value)


def build_search_text(record: Mapping[str, Any]) -> str:
    """Собирает нижний регистр всех значений для быстрого поиска."""
    parts: list[str] = []

    def collect(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
            return
        if isinstance(value, (list, tuple)):
            for nested in value:
                collect(nested)
            return
        text = str(value).strip()
        if text:
            parts.append(text.lower())

    for value in record.values():
        collect(value)
    return " | ".join(parts)
