import asyncio
from pathlib import Path

from ..adapters import AstrBotAdapter
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


def test_page_assets_are_self_contained_and_bridge_first():
    root = Path(__file__).resolve().parents[1] / "pages" / "manager"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "bridge-sdk.js" in html and "./app.js" in html
    assert html.index("bridge-sdk.js") < html.index("./app.js")
    assert "await bridge.ready()" in js
    assert "Promise.all" in js
