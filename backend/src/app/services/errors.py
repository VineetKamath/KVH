"""Typed application errors. `error_code` values come from DynamicPricing/data/enums.json (error_code) where
one fits; the API renders {error_code, message} and never leaks stack traces, SQL or paths."""
from __future__ import annotations


class AppError(Exception):
    def __init__(self, error_code: str, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status = status
        self.details = details or {}


def invalid_id(what: str) -> AppError:
    return AppError("invalid_id", f"unknown {what}", 404)


def infeasible(message: str) -> AppError:
    return AppError("constraint_infeasible", message, 422)
