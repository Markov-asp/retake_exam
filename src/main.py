"""Точка сборки FastAPI-приложения."""

from __future__ import annotations

import argparse
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api import routes_analytics, routes_pages, routes_reports
from src.config import Settings, load_settings
from src.services.database import init_db, session
from src.services.ingest import seed_sample
from src.utils.cache import TTLCache
from src.utils.errors import ServiceError
from src.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)

TAGS_METADATA = [
    {"name": "Интерфейс", "description": "Веб-дашборд сервиса."},
    {"name": "Отчёты", "description": "Загрузка, список и удаление отчётов."},
    {"name": "Аналитика", "description": "KPI, графики, таблицы и экспорт данных."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Создаёт приложение с заданными настройками (удобно для тестов)."""
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_directories()
        init_db(settings.database)
        if settings.auto_seed:
            with session(settings.database) as conn:
                seeded = seed_sample(conn, settings.raw_dir)
            if seeded:
                logger.info("Демонстрационные отчёты загружены: %s", len(seeded))
        logger.info("Сервис запущен: %s v%s", settings.app_name, settings.version)
        yield
        logger.info("Сервис остановлен")

    application = FastAPI(
        title=f"{settings.app_name} — сервис обработки и визуализации данных",
        description=(
            "REST API для загрузки Excel-отчётов с техническими характеристиками "
            "видео и телеметрией трекинга, агрегации метрик по дням, месяцам и "
            "всему объёму данных, а также построения интерактивных графиков Plotly."
        ),
        version=settings.version,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.state.settings = settings
    application.state.cache = TTLCache(
        ttl_seconds=settings.cache_ttl_seconds,
        max_entries=settings.cache_max_entries,
    )
    application.state.templates = Jinja2Templates(directory=str(settings.components_dir))

    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        return response

    @application.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
        logger.warning("Ошибка API %s: %s", request.url.path, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon():
        path = settings.components_dir / "favicon.svg"
        if not path.is_file():
            return Response(status_code=204)
        return FileResponse(path, media_type="image/svg+xml")

    application.mount(
        "/static/css",
        StaticFiles(directory=str(settings.styles_dir)),
        name="styles",
    )
    application.mount(
        "/static/js",
        StaticFiles(directory=str(settings.components_dir / "js")),
        name="scripts",
    )
    application.mount(
        "/static/vendor",
        StaticFiles(directory=str(settings.components_dir / "vendor")),
        name="vendor",
    )
    application.include_router(routes_pages.router)
    application.include_router(routes_reports.router)
    application.include_router(routes_analytics.router)
    return application


app = create_app()


def main() -> None:
    """Точка входа: ``python -m src.main [--host] [--port] [--reload]``."""
    parser = argparse.ArgumentParser(description="DataScope — сервис обработки и визуализации данных")
    parser.add_argument("--host", default="127.0.0.1", help="адрес, который слушает сервис")
    parser.add_argument("--port", default=8000, type=int, help="порт сервиса")
    parser.add_argument("--reload", action="store_true", help="автоперезапуск при изменении кода")
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["debug", "info", "warning", "error"],
        help="уровень журналирования uvicorn",
    )
    args = parser.parse_args()

    settings = load_settings()
    level = (args.log_level or settings.log_level).lower()
    print(f"{settings.app_name} v{settings.version}")
    print(f"  интерфейс:  http://{args.host}:{args.port}/")
    print(f"  API:        http://{args.host}:{args.port}/docs")
    print(f"  база:       {settings.database}")
    uvicorn.run(
        "src.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=level,
    )


if __name__ == "__main__":
    main()
