from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

SERVICE_RE = re.compile(r"^[a-z][a-z0-9_-]*\.[a-z][a-z0-9_-]*\.[a-z][a-z0-9_-]*$")
OPERATION_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
CONTRACT_RE = re.compile(r"^[1-9]\d*\.[0-9]+$")
JSONSchema = Mapping[str, Any] | str
Handler = Callable[[Mapping[str, Any], "CallContext"], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class OperationDescriptor:
    name: str
    timeout_ms: int = 10000
    permission: str | None = None
    idempotency: str = "none"
    input_schema: JSONSchema | None = None
    output_schema: JSONSchema | None = None
    max_inflight: int = 16
    queue_size: int = 32

    def validate(self) -> None:
        if not OPERATION_RE.fullmatch(self.name):
            raise ValueError("invalid operation name")
        if self.timeout_ms <= 0 or self.idempotency not in {"none", "keyed"}:
            raise ValueError("invalid operation descriptor")
        if self.max_inflight <= 0 or self.queue_size < 0:
            raise ValueError("invalid operation concurrency limits")
        for schema in (self.input_schema, self.output_schema):
            if schema is not None and not isinstance(schema, (str, Mapping)):
                raise ValueError("schema must be a JSON Schema object or registered reference")


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    service: str
    version: str
    provider_plugin: str
    operations: Mapping[str, OperationDescriptor]
    tags: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    contract_version: str = "1.0"

    @property
    def protocol(self) -> str:
        return self.contract_version

    def validate(self) -> None:
        if not CONTRACT_RE.fullmatch(self.contract_version):
            raise ValueError("invalid contract version")
        if not SERVICE_RE.fullmatch(self.service):
            raise ValueError("invalid service key")
        if not SEMVER_RE.fullmatch(self.version) or not self.provider_plugin.strip():
            raise ValueError("invalid service version or provider")
        if not self.operations:
            raise ValueError("capability must expose an operation")
        for name, operation in self.operations.items():
            if name != operation.name:
                raise ValueError("operation key does not match operation name")
            operation.validate()


# 兼容早期消费者名称；公共契约以 CapabilityDescriptor 为准。
ServiceDescriptor = CapabilityDescriptor


@dataclass(frozen=True, slots=True)
class RegistrationToken:
    service: str
    version: str
    provider_plugin: str
    instance_id: str
    generation: int
    nonce: str


@dataclass(frozen=True, slots=True)
class CallContext:
    request_id: str
    trace_id: str
    span_id: str
    service: str
    operation: str
    caller_plugin: str
    provider_instance_id: str
    deadline_at: float
    contract_version: str
    authz_revision: int
    idempotency_key: str | None = None
    parent_span_id: str | None = None
    baggage: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        service: str,
        operation: str,
        caller_plugin: str,
        provider: str,
        timeout_ms: int,
        contract_version: str,
        authz_revision: int,
        idempotency_key: str | None = None,
        trace_id: str | None = None,
    ) -> "CallContext":
        return cls(
            request_id=str(uuid.uuid4()),
            trace_id=trace_id or str(uuid.uuid4()),
            span_id=str(uuid.uuid4()),
            service=service,
            operation=operation,
            caller_plugin=caller_plugin,
            provider_instance_id=provider,
            deadline_at=time.monotonic() + max(0, timeout_ms) / 1000,
            contract_version=contract_version,
            authz_revision=authz_revision,
            idempotency_key=idempotency_key,
        )

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_at - time.monotonic())


InvocationContext = CallContext


@dataclass(frozen=True, slots=True)
class ServiceError:
    code: str
    message: str
    retryable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ServiceResponse:
    request_id: str
    trace_id: str
    provider_instance_id: str
    status: str
    data: Any = None
    error: ServiceError | None = None
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.error is None

    def unwrap(self) -> Any:
        if self.error is not None:
            from .errors import HubError

            raise HubError.from_service_error(self.error)
        return self.data


@dataclass(frozen=True, slots=True)
class ServiceSnapshot:
    descriptor: CapabilityDescriptor
    token: RegistrationToken
    state: str
    inflight: int
    registered_at: float
    lease_expires_at: float
    last_error: str | None = None
