"""Конфигурация сервиса.

Все параметры читаются из переменных окружения с префиксом ``DASHBOARD_``
и имеют безопасные значения по умолчанию, поэтому сервис запускается
без дополнительной настройки.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class Settings:
    """Неизменяемый набор настроек приложения."""

    app_name: str = "DataScope"
    version: str = "1.0.0"
    description: str = (
        "Сервис обработки и визуализации данных: технические характеристики "
        "видео и телеметрия трекинга."
    )

    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    db_path: Path | None = None
    components_dir: Path = BASE_DIR / "src" / "components"
    styles_dir: Path = BASE_DIR / "src" / "styles"

    max_upload_mb: int = 256
    cache_ttl_seconds: int = 300
    cache_max_entries: int = 384
    auto_seed: bool = True
    log_level: str = "INFO"
    page_size: int = 50
    max_page_size: int = 500

    @property
    def database(self) -> Path:
        """Путь до файла базы данных SQLite."""
        return self.db_path or (self.data_dir / "app.db")

    @property
    def raw_dir(self) -> Path:
        """Каталог с исходными отчётами."""
        return self.data_dir / "raw"

    @property
    def uploads_dir(self) -> Path:
        """Каталог для загруженных пользователем файлов."""
        return self.data_dir / "uploads"

    def ensure_directories(self) -> None:
        """Создаёт рабочие каталоги, если их ещё нет."""
        for path in (self.data_dir, self.raw_dir, self.uploads_dir, self.database.parent):
            path.mkdir(parents=True, exist_ok=True)


def load_settings(**overrides: object) -> Settings:
    """Собирает настройки из окружения и явных переопределений.

    Переопределения удобны в тестах: ``load_settings(data_dir=tmp_path)``.
    """
    data_dir = Path(os.getenv("DASHBOARD_DATA_DIR", str(BASE_DIR / "data"))).expanduser()
    db_raw = os.getenv("DASHBOARD_DB_PATH", "").strip()

    settings = Settings(
        app_name=os.getenv("DASHBOARD_APP_NAME", "DataScope").strip() or "DataScope",
        version=os.getenv("DASHBOARD_VERSION", "1.0.0"),
        data_dir=data_dir,
        db_path=Path(db_raw).expanduser() if db_raw else None,
        max_upload_mb=_env_int("DASHBOARD_MAX_UPLOAD_MB", 256),
        cache_ttl_seconds=_env_int("DASHBOARD_CACHE_TTL_SECONDS", 300),
        auto_seed=_env_bool("DASHBOARD_AUTO_SEED", True),
        log_level=os.getenv("DASHBOARD_LOG_LEVEL", "INFO").upper(),
        page_size=_env_int("DASHBOARD_PAGE_SIZE", 50),
    )
    if overrides:
        settings = replace(settings, **overrides)  # type: ignore[arg-type]
    return settings
