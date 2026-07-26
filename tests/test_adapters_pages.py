import asyncio
from pathlib import Path

from ..adapters import AstrBotAdapter
from ..core.models import CapabilityDescriptor, OperationDescriptor
from ..core.registry import ServiceRegistry
from ..core.telemetry import Telemetry
from ..pages_manager import PagesManager


class Context:
    def __init__(self):
        self.routes = []

    def get_plugin_data_dir(self, plugin_id):
        return Path("data") / plugin_id

    def register_web_api(self, route, handler, methods, description):
        self.routes.append((route, handler, methods, description))


def test_adapter_uses_verified_local_context_shape():
    async def scenario():
        context = Context()
        adapter = AstrBotAdapter(context, "astrbot_plugin_orchestration_hub")
        assert adapter.data_dir == Path("data/astrbot_plugin_orchestration_hub")
        pages = PagesManager(ServiceRegistry(), Telemetry())
        assert pages.register(adapter)
        assert [route[0] for route in context.routes] == [
            "/astrbot_plugin_orchestration_hub/overview",
            "/astrbot_plugin_orchestration_hub/services",
            "/astrbot_plugin_orchestration_hub/telemetry",
        ]
        assert await context.routes[0][1]() == {
            "success": True,
            "services": 0,
            "instances": 0,
            "revision": 0,
        }

    asyncio.run(scenario())


def test_pages_hot_reload_reads_current_registry_and_statistics():
    async def scenario():
        old_registry = ServiceRegistry()
        current = {"registry": old_registry}
        pages = PagesManager(
            old_registry,
            Telemetry(),
            registry_provider=lambda: current["registry"],
        )
        new_registry = ServiceRegistry()
        descriptor = CapabilityDescriptor(
            "relationship.snapshot",
            "1.0.0",
            "astrbot_plugin_relationship",
            {"read": OperationDescriptor("read")},
        )
        token = await new_registry.register(
            descriptor, lambda payload, context: asyncio.sleep(0, result=payload)
        )
        await new_registry.mark_ready(token)
        current["registry"] = new_registry

        overview = await pages.overview()
        services = await pages.services()
        assert overview == {
            "success": True,
            "services": 1,
            "instances": 1,
            "revision": 2,
        }
        assert services["services"][0]["service"] == "relationship.snapshot"
        assert services["services"][0]["state"] == "READY"

    asyncio.run(scenario())


def test_page_assets_are_self_contained_and_bridge_first():
    root = Path(__file__).resolve().parents[1] / "pages" / "manager"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "bridge-sdk.js" in html and "./app.js" in html
    assert html.index("bridge-sdk.js") < html.index("./app.js")
    assert "await bridge.ready()" in js
    assert "Promise.all" in js
