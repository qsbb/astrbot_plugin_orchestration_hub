from __future__ import annotations

from typing import Any


class PagesAdapter:
    """Plugin Page 能力探测与最小注册桥接；不假定非公开 API。"""

    def __init__(self, context: Any, plugin_id: str) -> None:
        self.context = context
        self.plugin_id = plugin_id
        self.routes: list[str] = []
        self.available = callable(getattr(context, "register_web_api", None))

    def register(self, routes: tuple[tuple[str, Any, list[str], str], ...]) -> bool:
        register = getattr(self.context, "register_web_api", None)
        if not callable(register):
            return False
        try:
            for name, handler, methods, description in routes:
                route = f"/{self.plugin_id}/{name}"
                register(route, handler, methods, description)
                self.routes.append(route)
        except Exception:
            self.routes.clear()
            return False
        return True

    def report(self) -> dict[str, Any]:
        return {"available": self.available, "registered": bool(self.routes), "routes": list(self.routes), "degraded": not self.available}
