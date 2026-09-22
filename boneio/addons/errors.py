"""Stable, user-safe add-on errors."""

from __future__ import annotations

from typing import Any


class AddonError(Exception):
    """An expected add-on failure safe to expose through the API."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}
