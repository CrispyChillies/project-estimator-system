from typing import Any


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class NotFound(AppError):
    def __init__(self, what: str):
        super().__init__("not_found", f"{what} not found", 404)


class Conflict(AppError):
    def __init__(self, message: str, details: Any = None):
        super().__init__("conflict", message, 409, details)
