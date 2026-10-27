"""Domain error types and the consistent API error envelope (docs/governance/conventions.md)."""
from __future__ import annotations

from typing import Any, Optional


class DomainError(Exception):
    """Base class for business-rule violations. Carries a stable machine code."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: Optional[str] = None, *, code: Optional[str] = None,
                 details: Optional[dict[str, Any]] = None):
        super().__init__(message or self.code)
        self.message = message or self.code
        if code:
            self.code = code
        self.details = details or {}


class NotFoundError(DomainError):
    status_code = 404
    code = "RESOURCE_NOT_FOUND"


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"


class ForbiddenError(DomainError):
    status_code = 403
    code = "FORBIDDEN"


class UnauthorizedError(DomainError):
    status_code = 401
    code = "UNAUTHORIZED"


class ValidationFailure(DomainError):
    status_code = 422
    code = "VALIDATION_ERROR"


class PaymentRequiredError(DomainError):
    """Business-level payment failure (e.g. insufficient balance)."""

    status_code = 402
    code = "PAYMENT_FAILED"


class PolicyOpenError(DomainError):
    """A capability whose governing policy is still OPEN (Operating Model §15)."""

    status_code = 501
    code = "POLICY_OPEN"


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def error_body(code: str, message: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    body: dict[str, Any] = {"success": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body
