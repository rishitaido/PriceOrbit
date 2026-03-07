"""
Custom exception classes for PriceOrbit.

Industry practice: define domain-specific exceptions instead of raising
raw HTTPException directly in service code. This keeps business logic
clean and lets the API layer own the HTTP status mapping.

Pattern: Service raises domain exception → Router catches it → Returns
consistent HTTP error shape. Every error response looks like:
    {"detail": {"code": "NOT_FOUND", "message": "...", "context": {...}}}
"""

from typing import Any, Optional


class PriceOrbitError(Exception):
    """
    Base exception for all PriceOrbit domain errors.
    Catch broadly with `except PriceOrbitError` or narrowly with subclasses.
    """

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        """
        Args:
            message: Human-readable description of what went wrong.
            details: Optional structured context (dict, list, etc.).
        """
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(PriceOrbitError):
    """
    Raised when a requested resource does not exist.
    Maps to HTTP 404.

    Example:
        raise NotFoundError("Product", product_id)
    """

    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            message=f"{resource} with identifier '{identifier}' was not found.",
            details={"resource": resource, "identifier": identifier},
        )


class DuplicateError(PriceOrbitError):
    """
    Raised when creating a resource that already exists.
    Maps to HTTP 409 Conflict.

    Example:
        raise DuplicateError("Product", "name", "Bananas")
    """

    def __init__(self, resource: str, field: str, value: Any) -> None:
        super().__init__(
            message=f"{resource} with {field} '{value}' already exists.",
            details={"resource": resource, "field": field, "value": value},
        )


class ValidationError(PriceOrbitError):
    """
    Raised when business-level validation fails beyond Pydantic checks.
    Maps to HTTP 422.
    """

    pass


class ExternalAPIError(PriceOrbitError):
    """
    Raised when an external API call fails.
    Maps to HTTP 502 Bad Gateway.

    Example:
        raise ExternalAPIError("Kroger", "timeout after 10s")
    """

    def __init__(self, service: str, reason: str) -> None:
        super().__init__(
            message=f"External service '{service}' failed: {reason}",
            details={"service": service, "reason": reason},
        )


class AuthenticationError(PriceOrbitError):
    """
    Raised when authentication or token validation fails.
    Maps to HTTP 401.
    """

    pass
