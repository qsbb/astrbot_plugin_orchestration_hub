from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SENSITIVE_MARKERS = ("payload", "data", "body", "content", "message", "prompt", "token", "secret", "password")


def _safe_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in SENSITIVE_MARKERS):
        if isinstance(value, Mapping):
            return {"redacted": True, "fields": sorted(str(item) for item in value), "size": len(value)}
        if isinstance(value, (list, tuple, set)):
            return {"redacted": True, "items": len(value)}
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(child): _safe_value(str(child), item) for child, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(key, item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def sanitize(record: Mapping[str, Any]) -> dict[str, Any]:
    safe = {str(key): _safe_value(str(key), value) for key, value in record.items() if str(key).lower() != "payload"}
    safe["recorded_at"] = datetime.now(timezone.utc).isoformat()
    return safe


class DataStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.snapshot_path = data_dir / "registry_snapshot.json"
        self.audit_path = data_dir / "audit.jsonl"
        self._closed = False
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        await asyncio.to_thread(self.data_dir.mkdir, parents=True, exist_ok=True)
        self._closed = False

    async def write_snapshot(self, snapshot: Mapping[str, Any]) -> None:
        if self._closed:
            return
        safe = sanitize(snapshot)
        text = json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True)
        async with self._lock:
            await asyncio.to_thread(self.snapshot_path.write_text, text, "utf-8")

    async def append_audit(self, record: Mapping[str, Any]) -> None:
        if self._closed:
            return
        line = json.dumps(sanitize(record), ensure_ascii=False, separators=(",", ":")) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append, self.audit_path, line)

    @staticmethod
    def _append(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)

    async def close(self) -> None:
        self._closed = True
