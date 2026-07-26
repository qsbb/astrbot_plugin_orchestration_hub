from __future__ import annotations

from collections import Counter, deque
from typing import Any


class Telemetry:
    def __init__(self, max_records: int = 1000) -> None:
        self._records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._counts: Counter[tuple[str, str, str]] = Counter()

    def record(self, *, service: str, operation: str, caller: str, result: str, duration_ms: float, trace_id: str = "", request_id: str = "", provider: str = "") -> None:
        self._counts[(service, operation, result)] += 1
        self._records.append({"service": service, "operation": operation, "caller": caller, "provider": provider, "trace_id": trace_id, "request_id": request_id, "result": result, "duration_ms": round(duration_ms, 3)})

    def summary(self) -> dict[str, Any]:
        return {"counts": [{"service": key[0], "operation": key[1], "result": key[2], "count": value} for key, value in self._counts.items()], "recent": list(self._records)}

    def trace(self, trace_id: str) -> list[dict[str, Any]]:
        return [item for item in self._records if item.get("trace_id") == trace_id]

    def clear(self) -> None:
        self._records.clear()
        self._counts.clear()
