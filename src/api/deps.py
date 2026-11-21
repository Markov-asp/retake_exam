"""Зависимости FastAPI: настройки, БД и кэш из состояния приложения."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from src.config import Settings
from src.services.database import session
from src.utils.cache import TTLCache


def get_settings(request: Request) -> Settings:
    """Настройки приложения."""
    return request.app.state.settings


def get_cache(request: Request) -> TTLCache:
    """Кэш агрегатов."""
    return request.app.state.cache


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """Соединение с БД на время запроса."""
    settings: Settings = request.app.state.settings
    with session(settings.database) as conn:
        yield conn
