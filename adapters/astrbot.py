from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AstrBotRuntimeInfo:
    plugin_id: str
    data_dir: Path
    context: Any


class AstrBotAdapter:
    """仅封装本地插件已实际使用的 Context API。"""

    def __init__(self, context: Any, plugin_id: str, data_dir: Path | None = None) -> None:
        self.context = context
        self.plugin_id = plugin_id
        self.data_dir = data_dir or self._data_dir()

    def _data_dir(self) -> Path:
        getter = getattr(self.context, "get_plugin_data_dir", None)
        if callable(getter):
            try:
                return Path(getter(self.plugin_id))
            except TypeError:
                return Path(getter())
        return Path.cwd() / "data" / "plugin_data" / self.plugin_id

    def register_web_api(self, route: str, handler, methods: list[str], description: str) -> bool:
        register = getattr(self.context, "register_web_api", None)
        if not callable(register):
            return False
        register(route, handler, methods, description)
        return True

    def runtime_info(self) -> AstrBotRuntimeInfo:
        return AstrBotRuntimeInfo(self.plugin_id, self.data_dir, self.context)
