"""凝心溯溪-枢：AstrBot 生命周期装配入口。"""

from __future__ import annotations

import asyncio
import weakref
from typing import Any

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register

from .adapters import AstrBotAdapter
from .adapters.storage import DataStore
from .core import InvocationEngine, PolicyEngine, ServiceRegistry, ServiceResolver, Telemetry
from .pages_manager import PagesManager

PLUGIN_ID = "astrbot_plugin_orchestration_hub"
__version__ = "0.1.1"


@register(PLUGIN_ID, "Justice-ocr", "凝心溯溪系列服务中枢模块：同进程服务注册、发现与异步调用", __version__)
class OrchestrationHubPlugin(Star):
    """只负责装配、命令入口和清理；服务语义位于 core。"""

    _current_ref: weakref.ReferenceType["OrchestrationHubPlugin"] | None = None

    def __init__(self, context: Context, config: Any = None) -> None:
        super().__init__(context)
        self.context = context
        self.config = config or {}
        self.registry = ServiceRegistry()  # default lease is overridden by explicit registration lease when configured
        self.policy = PolicyEngine()
        self.telemetry = Telemetry()
        self.invocation = InvocationEngine(self.registry, self.policy, self.telemetry, max_inflight=int(self._config("GLOBAL_MAX_INFLIGHT", 128)), max_inline_payload_bytes=int(self._config("MAX_INLINE_PAYLOAD_BYTES", 262144)))
        self.resolver = ServiceResolver(self.registry, self.policy, self.invocation)
        self.adapter = AstrBotAdapter(context, PLUGIN_ID)
        self.store = DataStore(self.adapter.data_dir)
        self.pages = PagesManager(
            self.registry,
            self.telemetry,
            self.store,
            registry_provider=self._current_registry,
        )
        self.page_registered = self.pages.register(self.adapter)
        self._terminated = False
        self._lifecycle_lock = asyncio.Lock()
        self._lease_task: asyncio.Task | None = None

    def _config(self, key: str, default: Any) -> Any:
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        getter = getattr(self.config, "get", None)
        return getter(key, default) if callable(getter) else default

    @classmethod
    def get_current(cls) -> "OrchestrationHubPlugin | None":
        """返回已完成初始化且仍可接收注册的当前枢实例。"""
        instance = cls._current_ref() if cls._current_ref is not None else None
        if instance is None or instance._terminated:
            return None
        return instance

    def _current_registry(self) -> ServiceRegistry:
        current = self.get_current()
        return current.registry if current is not None else self.registry

    async def initialize(self) -> None:
        async with self._lifecycle_lock:
            if self._terminated:
                return
            await self.store.open()
            if self._lease_task is None or self._lease_task.done():
                self._lease_task = asyncio.create_task(self._lease_supervisor())
            OrchestrationHubPlugin._current_ref = weakref.ref(self)
        logger.info("[orchestration-hub] v%s loaded; pages=%s", __version__, self.page_registered)

    async def _lease_supervisor(self) -> None:
        try:
            while not self._terminated:
                await asyncio.sleep(max(1.0, min(10.0, float(self._config("LEASE_SWEEP_SECONDS", 5)))))
                await self.registry.snapshots()
        except asyncio.CancelledError:
            return

    def _disabled_notice(self) -> str | None:
        return "凝心溯溪-枢 已被配置禁用。" if not self._config("ENABLED", True) else None

    @filter.command_group("hub")
    def hub_group(self) -> None:
        """服务中枢管理命令。"""

    @hub_group.command("status")
    async def hub_status(self, event):
        notice = self._disabled_notice()
        if notice:
            yield event.plain_result(notice)
            return
        snapshots = await self.registry.snapshots()
        yield event.plain_result(f"凝心溯溪-枢\n服务: {len({item.descriptor.service for item in snapshots})}\n实例: {len(snapshots)}\nrevision: {self.registry.revision}\nPages: {'可用' if self.page_registered else '降级'}")

    @hub_group.command("services")
    async def hub_services(self, event):
        snapshots = await self.registry.snapshots()
        lines = ["已注册服务"]
        lines.extend(f"- {item.descriptor.service} {item.descriptor.version} [{item.state}] {item.token.instance_id}" for item in snapshots)
        yield event.plain_result("\n".join(lines))

    @hub_group.command("diagnose")
    async def hub_diagnose(self, event):
        report = {"pages": self.pages.adapter.report() if self.pages.adapter else {"available": False, "degraded": True}, "registry_accepting": not self._terminated}
        yield event.plain_result(f"能力诊断\nPages: {'可用' if report['pages']['available'] else '降级'}\nRegistry: {'可用' if report['registry_accepting'] else '已停止'}")

    async def terminate(self) -> None:
        async with self._lifecycle_lock:
            if self._terminated:
                return
            self._terminated = True
            await self.registry.stop_accepting()
            lease_task = self._lease_task
            self._lease_task = None
        if lease_task is not None and lease_task is not asyncio.current_task():
            lease_task.cancel()
            await asyncio.gather(lease_task, return_exceptions=True)
        await self.registry.wait_for_idle(float(self._config("DRAIN_GRACE_SECONDS", 5)))
        await self.registry.clear()
        self.invocation.clear()
        await self.store.append_audit({"action": "terminate", "result": "ok", "revision": self.registry.revision})
        await self.store.close()
        current = (
            OrchestrationHubPlugin._current_ref()
            if OrchestrationHubPlugin._current_ref is not None
            else None
        )
        if current is self:
            OrchestrationHubPlugin._current_ref = None
        logger.info("[orchestration-hub] terminated")
