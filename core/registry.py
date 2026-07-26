from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field

from .errors import ProviderUnavailableError, ServiceNotReadyError
from .models import CapabilityDescriptor, Handler, RegistrationToken, ServiceSnapshot


@dataclass
class _Entry:
    descriptor: CapabilityDescriptor
    token: RegistrationToken
    handler: Handler
    state: str = "REGISTERED"
    inflight: int = 0
    registered_at: float = 0.0
    lease_expires_at: float = 0.0
    last_error: str | None = None
    operation_semaphores: dict[str, asyncio.Semaphore] = field(default_factory=dict)
    operation_waiters: dict[str, int] = field(default_factory=dict)

    def lease_valid(self, now: float | None = None) -> bool:
        return self.lease_expires_at > (time.monotonic() if now is None else now)


class ServiceRegistry:
    def __init__(self, default_lease_seconds: float = 60.0) -> None:
        if default_lease_seconds <= 0:
            raise ValueError("default lease must be positive")
        self.default_lease_seconds = default_lease_seconds
        self._entries: dict[str, list[_Entry]] = {}
        self._lock = asyncio.Lock()
        self._generation: dict[tuple[str, str, str], int] = {}
        self.revision = 0
        self._accepting = True

    @property
    def accepting(self) -> bool:
        """供同进程发现逻辑快速排除已进入停止阶段的 Registry。"""
        return self._accepting

    async def register(self, descriptor: CapabilityDescriptor, handler: Handler, lease_seconds: float | None = None) -> RegistrationToken:
        descriptor.validate()
        if not callable(handler):
            raise TypeError("handler must be callable")
        ttl = self.default_lease_seconds if lease_seconds is None else lease_seconds
        if ttl <= 0:
            raise ValueError("lease must be positive")
        async with self._lock:
            if not self._accepting:
                raise ServiceNotReadyError("registry is stopping")
            self._expire_locked()
            key = (descriptor.provider_plugin, descriptor.service, descriptor.version)
            active = [entry for entry in self._entries.get(descriptor.service, []) if entry.descriptor.provider_plugin == descriptor.provider_plugin and entry.descriptor.version == descriptor.version and entry.state in {"REGISTERED", "READY", "DEGRADED"}]
            for old in active:
                old.state = "DRAINING"
            generation = self._generation.get(key, 0) + 1
            self._generation[key] = generation
            token = RegistrationToken(descriptor.service, descriptor.version, descriptor.provider_plugin, f"{descriptor.provider_plugin}:{generation}:{uuid.uuid4().hex[:12]}", generation, secrets.token_urlsafe(16))
            entry = _Entry(
                descriptor,
                token,
                handler,
                registered_at=time.time(),
                lease_expires_at=time.monotonic() + ttl,
                operation_semaphores={name: asyncio.Semaphore(operation.max_inflight) for name, operation in descriptor.operations.items()},
                operation_waiters={name: 0 for name in descriptor.operations},
            )
            self._entries.setdefault(descriptor.service, []).append(entry)
            self.revision += 1
            return token

    async def renew(self, token: RegistrationToken, lease_seconds: float | None = None) -> float:
        ttl = self.default_lease_seconds if lease_seconds is None else lease_seconds
        if ttl <= 0:
            raise ValueError("lease must be positive")
        async with self._lock:
            entry = self._find_token_locked(token)
            if entry.state in {"DRAINING", "UNREGISTERED", "EXPIRED"}:
                raise ProviderUnavailableError("registration lease is no longer renewable")
            entry.lease_expires_at = time.monotonic() + ttl
            self.revision += 1
            return entry.lease_expires_at

    async def mark_ready(self, token: RegistrationToken) -> None:
        async with self._lock:
            entry = self._find_token_locked(token)
            if not entry.lease_valid():
                self._expire_entry(entry)
                raise ProviderUnavailableError("registration lease expired")
            if entry.state != "REGISTERED":
                raise ServiceNotReadyError("service is not registerable")
            entry.state = "READY"
            for old in self._entries.get(token.service, []):
                if old is not entry and old.descriptor.provider_plugin == token.provider_plugin and old.descriptor.version == token.version and old.state in {"READY", "DEGRADED"}:
                    old.state = "DRAINING"
            self.revision += 1

    async def unregister(self, token: RegistrationToken) -> None:
        async with self._lock:
            entry = self._find_token_locked(token)
            entry.state = "UNREGISTERED"
            self.revision += 1

    async def begin_drain(self, token: RegistrationToken) -> None:
        async with self._lock:
            entry = self._find_token_locked(token)
            entry.state = "DRAINING"
            self.revision += 1

    async def acquire(self, token: RegistrationToken) -> _Entry:
        async with self._lock:
            entry = self._find_token_locked(token)
            if not entry.lease_valid():
                self._expire_entry(entry)
                raise ProviderUnavailableError("registration lease expired")
            if entry.state != "READY":
                raise ServiceNotReadyError("service is not ready")
            entry.inflight += 1
            return entry

    async def release(self, entry: _Entry) -> None:
        async with self._lock:
            entry.inflight = max(0, entry.inflight - 1)

    async def snapshots(self) -> list[ServiceSnapshot]:
        async with self._lock:
            self._expire_locked()
            return [ServiceSnapshot(e.descriptor, e.token, e.state, e.inflight, e.registered_at, e.lease_expires_at, e.last_error) for entries in self._entries.values() for e in entries if e.state != "UNREGISTERED"]

    async def find(self, service: str) -> list[_Entry]:
        async with self._lock:
            self._expire_locked()
            return [entry for entry in self._entries.get(service, []) if entry.state not in {"UNREGISTERED", "EXPIRED"}]

    async def stop_accepting(self) -> None:
        async with self._lock:
            self._accepting = False
            for entries in self._entries.values():
                for entry in entries:
                    if entry.state in {"REGISTERED", "READY", "DEGRADED"}:
                        entry.state = "DRAINING"
            self.revision += 1

    async def wait_for_idle(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0, timeout_seconds)
        while time.monotonic() < deadline:
            if all(item.inflight == 0 for item in await self.snapshots()):
                return True
            await asyncio.sleep(0.01)
        return all(item.inflight == 0 for item in await self.snapshots())

    async def wait_for_token_idle(
        self, token: RegistrationToken, timeout_seconds: float
    ) -> bool:
        """等待指定服务实例完成调用，不阻塞其他提供者。"""
        deadline = time.monotonic() + max(0, timeout_seconds)
        while time.monotonic() < deadline:
            async with self._lock:
                entry = self._find_token_locked(token)
                if entry.inflight == 0:
                    return True
            await asyncio.sleep(0.01)
        async with self._lock:
            return self._find_token_locked(token).inflight == 0

    async def clear(self) -> None:
        async with self._lock:
            for entries in self._entries.values():
                for entry in entries:
                    entry.state = "UNREGISTERED"
            self._entries.clear()
            self.revision += 1

    def _find_token_locked(self, token: RegistrationToken) -> _Entry:
        for entry in self._entries.get(token.service, []):
            if entry.token == token:
                return entry
        raise ProviderUnavailableError("registration token is stale")

    def _expire_entry(self, entry: _Entry) -> None:
        if entry.state not in {"UNREGISTERED", "EXPIRED"}:
            entry.state = "EXPIRED"
            entry.last_error = "LEASE_EXPIRED"
            self.revision += 1

    def _expire_locked(self) -> None:
        now = time.monotonic()
        for entries in self._entries.values():
            for entry in entries:
                if entry.state not in {"DRAINING", "UNREGISTERED", "EXPIRED"} and not entry.lease_valid(now):
                    self._expire_entry(entry)
