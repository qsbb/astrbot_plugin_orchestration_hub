from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Mapping

from .errors import DeadlineExceededError, HubError, InvalidArgumentError, PayloadTooLargeError, ProviderUnavailableError, ResourceExhaustedError
from .models import CallContext, ServiceResponse
from .registry import ServiceRegistry, _Entry
from .telemetry import Telemetry
from .validation import SchemaRegistry


class InvocationEngine:
    def __init__(self, registry: ServiceRegistry, policy, telemetry: Telemetry, schemas: SchemaRegistry | None = None, max_inflight: int = 128, max_inline_payload_bytes: int = 262144) -> None:
        self.registry = registry
        self.policy = policy
        self.telemetry = telemetry
        self.schemas = schemas or SchemaRegistry()
        self.max_inline_payload_bytes = max_inline_payload_bytes
        self._semaphore = asyncio.Semaphore(max_inflight)
        self._idempotent: dict[tuple[str, str, str], ServiceResponse] = {}

    async def call(self, handle, operation: str, payload: Mapping[str, Any], timeout_ms: int | None = None, idempotency_key: str | None = None, *, return_response: bool = False) -> Any:
        descriptor = handle.descriptor.operations.get(operation)
        if descriptor is None:
            raise InvalidArgumentError("unknown operation")
        if not isinstance(payload, Mapping):
            raise InvalidArgumentError("payload must be a JSON object")
        self.policy.allow(handle.caller_plugin, handle.descriptor.service, operation, descriptor.permission)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > self.max_inline_payload_bytes:
            raise PayloadTooLargeError("inline payload exceeds limit")
        self.schemas.validate(payload, descriptor.input_schema, direction="input")
        if descriptor.idempotency == "keyed" and not idempotency_key:
            raise InvalidArgumentError("idempotency_key is required for keyed operation")
        cache_key = (handle.descriptor.service, operation, idempotency_key or "")
        if descriptor.idempotency == "keyed" and cache_key in self._idempotent:
            response = self._idempotent[cache_key]
            return response if return_response else response.unwrap()
        timeout = descriptor.timeout_ms if timeout_ms is None else timeout_ms
        if timeout <= 0:
            raise InvalidArgumentError("timeout_ms must be positive")
        context = CallContext.create(handle.descriptor.service, operation, handle.caller_plugin, handle.token.instance_id, timeout, handle.descriptor.contract_version, self.policy.revision, idempotency_key)
        started = time.monotonic()
        acquired = False
        entry: _Entry | None = None
        try:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), context.remaining_seconds)
                acquired = True
            except asyncio.TimeoutError as exc:
                raise ResourceExhaustedError("global concurrency limit") from exc
            entry = await self.registry.acquire(handle.token)
            waiter_count = entry.operation_waiters[operation]
            if entry.operation_semaphores[operation].locked() and waiter_count >= descriptor.queue_size:
                raise ResourceExhaustedError("operation queue is full")
            entry.operation_waiters[operation] = waiter_count + 1
            try:
                await asyncio.wait_for(entry.operation_semaphores[operation].acquire(), context.remaining_seconds)
            except asyncio.TimeoutError as exc:
                raise ResourceExhaustedError("operation concurrency limit") from exc
            finally:
                entry.operation_waiters[operation] = max(0, entry.operation_waiters[operation] - 1)
            try:
                result = await asyncio.wait_for(entry.handler(payload, context), context.remaining_seconds)
            finally:
                entry.operation_semaphores[operation].release()
            self.schemas.validate(result, descriptor.output_schema, direction="output")
            response = ServiceResponse(context.request_id, context.trace_id, context.provider_instance_id, "ok", result, None, {"duration_ms": round((time.monotonic() - started) * 1000, 3), "degraded": False})
            if descriptor.idempotency == "keyed":
                self._idempotent[cache_key] = response
            self.telemetry.record(service=context.service, operation=operation, caller=context.caller_plugin, trace_id=context.trace_id, request_id=context.request_id, provider=context.provider_instance_id, result="ok", duration_ms=(time.monotonic() - started) * 1000)
            return response if return_response else result
        except asyncio.TimeoutError as exc:
            error = DeadlineExceededError("provider call exceeded deadline")
            response = ServiceResponse(context.request_id, context.trace_id, context.provider_instance_id, "error", None, error.to_service_error(), {"duration_ms": round((time.monotonic() - started) * 1000, 3), "degraded": False})
            self.telemetry.record(service=context.service, operation=operation, caller=context.caller_plugin, trace_id=context.trace_id, request_id=context.request_id, provider=context.provider_instance_id, result=error.code, duration_ms=(time.monotonic() - started) * 1000)
            if return_response:
                return response
            raise error from exc
        except Exception as exc:
            error = exc if isinstance(exc, HubError) else ProviderUnavailableError("provider execution failed")
            self.telemetry.record(service=context.service, operation=operation, caller=context.caller_plugin, trace_id=context.trace_id, request_id=context.request_id, provider=context.provider_instance_id, result=error.code, duration_ms=(time.monotonic() - started) * 1000)
            if return_response:
                return ServiceResponse(context.request_id, context.trace_id, context.provider_instance_id, "error", None, error.to_service_error(), {"duration_ms": round((time.monotonic() - started) * 1000, 3), "degraded": False})
            if error is not exc:
                raise error from exc
            raise
        finally:
            if entry is not None:
                await self.registry.release(entry)
            if acquired:
                self._semaphore.release()

    def clear(self) -> None:
        self._idempotent.clear()
