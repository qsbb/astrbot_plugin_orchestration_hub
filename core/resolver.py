from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ServiceNotFoundError, ServiceNotReadyError
from .models import RegistrationToken, ServiceDescriptor
from .registry import ServiceRegistry, _Entry

_RANGE_RE = re.compile(r"^(>=|>|<=|<|=)?\s*(\d+)\.(\d+)\.(\d+)$")


def _version(version: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return (0, 0, 0)
    return tuple(map(int, match.groups()))


def satisfies(version: str, constraint: str) -> bool:
    if not constraint or constraint == "*":
        return True
    current = _version(version)
    for part in constraint.split(","):
        match = _RANGE_RE.fullmatch(part.strip())
        if not match:
            return False
        operator = match.group(1) or "="
        target = tuple(map(int, match.groups()[1:]))
        if operator == ">=" and current < target or operator == ">" and current <= target or operator == "<=" and current > target or operator == "<" and current >= target or operator == "=" and current != target:
            return False
    return True


@dataclass(frozen=True)
class ServiceHandle:
    registry: ServiceRegistry
    entry: _Entry
    caller_plugin: str
    permission_checker: object
    invocation_engine: object | None = None

    async def call(
        self,
        operation: str,
        payload,
        timeout_ms: int | None = None,
        idempotency_key: str | None = None,
        *,
        return_response: bool = False,
    ):
        if self.invocation_engine is None:
            raise RuntimeError("invocation engine is not bound")
        return await self.invocation_engine.call(
            self, operation, payload, timeout_ms, idempotency_key,
            return_response=return_response,
        )

    @property
    def descriptor(self) -> ServiceDescriptor:
        return self.entry.descriptor

    @property
    def token(self) -> RegistrationToken:
        return self.entry.token


class ServiceResolver:
    def __init__(self, registry: ServiceRegistry, permission_checker, invocation_engine=None) -> None:
        self.registry = registry
        self.permission_checker = permission_checker
        self.invocation_engine = invocation_engine

    async def resolve(self, service: str, version: str = "*", required_tags: set[str] | frozenset[str] | None = None, caller_plugin: str = "", contract_version: str = "1.0") -> ServiceHandle:
        candidates = [entry for entry in await self.registry.find(service) if entry.state == "READY" and entry.descriptor.contract_version == contract_version and satisfies(entry.descriptor.version, version) and (not required_tags or set(required_tags).issubset(entry.descriptor.tags))]
        if not candidates:
            all_entries = await self.registry.find(service)
            if all_entries:
                raise ServiceNotReadyError("no ready service satisfies request")
            raise ServiceNotFoundError("service not found")
        candidates.sort(key=lambda item: (_version(item.descriptor.version), -item.inflight), reverse=True)
        entry = candidates[0]
        return ServiceHandle(self.registry, entry, caller_plugin, self.permission_checker, self.invocation_engine)
