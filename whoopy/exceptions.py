"""Exception hierarchy for Whoop API v2.

This module provides a comprehensive exception hierarchy for handling
various error conditions that can occur when interacting with the Whoop API.

Copyright (c) 2024 Felix Geilert
"""

from typing import Any


class WhoopException(Exception):
    """Base exception for all Whoop API errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(WhoopException):
    """Raised when authentication fails or credentials are invalid."""

    def __init__(self, message: str = "Authentication failed", details: dict[str, Any] | None = None):
        super().__init__(message, details)


class TokenExpiredError(AuthenticationError):
    """Raised when the access token has expired."""

    def __init__(self, message: str = "Access token has expired", details: dict[str, Any] | None = None):
        super().__init__(message, details)


class RefreshTokenError(AuthenticationError):
    """Raised when refreshing the access token fails."""

    def __init__(self, message: str = "Failed to refresh access token", details: dict[str, Any] | None = None):
        super().__init__(message, details)


class RateLimitError(WhoopException):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.retry_after = retry_after


class ResourceNotFoundError(WhoopException):
    """Raised when a requested resource is not found (404)."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        if message is None:
            if resource_id:
                message = f"{resource_type} with ID '{resource_id}' not found"
            else:
                message = f"{resource_type} not found"
        super().__init__(message, details)
        self.resource_type = resource_type
        self.resource_id = resource_id


class ValidationError(WhoopException):
    """Raised when request validation fails (400)."""

    def __init__(
        self,
        message: str = "Request validation failed",
        validation_errors: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.validation_errors = validation_errors or {}


class ServerError(WhoopException):
    """Raised when the server encounters an error (5xx)."""

    def __init__(
        self, status_code: int = 500, message: str = "Internal server error", details: dict[str, Any] | None = None
    ):
        super().__init__(message, details)
        self.status_code = status_code


class ConfigurationError(WhoopException):
    """Raised when there's a configuration issue with the client."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, details)
