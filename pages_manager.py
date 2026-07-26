from __future__ import annotations

from .adapters.pages import PagesAdapter
from .core.registry import ServiceRegistry
from .core.telemetry import Telemetry


class PagesManager:
    def __init__(self, registry: ServiceRegistry, telemetry: Telemetry, data_store=None) -> None:
        self.registry = registry
        self.telemetry = telemetry
        self.data_store = data_store
        self.adapter: PagesAdapter | None = None

    def register(self, adapter) -> bool:
        self.adapter = PagesAdapter(adapter.context, adapter.plugin_id)
        routes = (
            ("overview", self.overview, ["GET"], "查看服务中枢总览"),
            ("services", self.services, ["GET"], "查看已注册服务"),
            ("telemetry", self.telemetry_view, ["GET"], "查看调用摘要"),
        )
        return self.adapter.register(routes)

    async def overview(self):
        snapshots = await self.registry.snapshots()
        return {"success": True, "services": len({item.descriptor.service for item in snapshots}), "instances": len(snapshots), "revision": self.registry.revision}

    async def services(self):
        snapshots = await self.registry.snapshots()
        return {"success": True, "services": [{"service": item.descriptor.service, "version": item.descriptor.version, "contract_version": item.descriptor.contract_version, "provider_plugin": item.descriptor.provider_plugin, "instance_id": item.token.instance_id, "state": item.state, "operations": sorted(item.descriptor.operations), "tags": sorted(item.descriptor.tags), "inflight": item.inflight, "lease_expires_at": item.lease_expires_at} for item in snapshots]}

    async def telemetry_view(self):
        return {"success": True, **self.telemetry.summary()}

    async def snapshot(self):
        snapshots = await self.registry.snapshots()
        payload = {"revision": self.registry.revision, "instances": [{"service": item.descriptor.service, "version": item.descriptor.version, "provider_plugin": item.descriptor.provider_plugin, "instance_id": item.token.instance_id, "generation": item.token.generation, "state": item.state, "inflight": item.inflight, "lease_expires_at": item.lease_expires_at} for item in snapshots]}
        if self.data_store:
            await self.data_store.write_snapshot(payload)
        return {"success": True, **payload}

    async def audit(self):
        return {"success": True, "persisted": bool(self.data_store), "payload_included": False}
