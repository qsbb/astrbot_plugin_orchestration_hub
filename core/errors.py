from __future__ import annotations

from typing import Any


class HubError(Exception):
    code = "INTERNAL"
    retryable = False

    def __init__(self, message: str = "", *, details: dict[str, Any] | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details or {}

    def to_service_error(self):
        from .models import ServiceError

        return ServiceError(self.code, self.message, self.retryable, self.details)

    @classmethod
    def from_service_error(cls, error):
        return type("RemoteHubError", (HubError,), {"code": error.code, "retryable": error.retryable})(error.message, details=dict(error.details))


class ServiceNotFoundError(HubError):
    code = "SERVICE_NOT_FOUND"
    retryable = True


class ServiceNotReadyError(HubError):
    code = "SERVICE_NOT_READY"
    retryable = True


class PermissionDeniedError(HubError):
    code = "PERMISSION_DENIED"


class InvalidArgumentError(HubError):
    code = "INVALID_ARGUMENT"


class PayloadTooLargeError(HubError):
    code = "PAYLOAD_TOO_LARGE"


class DeadlineExceededError(HubError):
    code = "DEADLINE_EXCEEDED"
    retryable = True


class ProviderUnavailableError(HubError):
    code = "PROVIDER_UNAVAILABLE"
    retryable = True


class ConflictError(HubError):
    code = "CONFLICT"


class ResourceExhaustedError(HubError):
    code = "RESOURCE_EXHAUSTED"
    retryable = True


class CancelledError(HubError):
    code = "CANCELLED"


class SchemaValidationError(InvalidArgumentError):
    pass
