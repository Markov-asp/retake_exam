"""Доменные исключения сервиса и их HTTP-представление."""

from __future__ import annotations


class ServiceError(Exception):
    """Базовая ошибка сервиса с HTTP-статусом и кодом."""

    status_code = 400
    code = "service_error"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(ServiceError):
    """Запрошенный объект не найден."""

    status_code = 404
    code = "not_found"


class ValidationError(ServiceError):
    """Некорректные входные данные."""

    status_code = 422
    code = "validation_error"


class ConflictError(ServiceError):
    """Конфликт состояния (например, повторная загрузка отчёта)."""

    status_code = 409
    code = "conflict"


class PayloadTooLarge(ServiceError):
    """Файл превышает допустимый размер."""

    status_code = 413
    code = "payload_too_large"
