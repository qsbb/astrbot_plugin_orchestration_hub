"""Public series.control@1.0 adapter for orchestration limits."""

from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

FIELDS = {
    "ENABLED": {"type": "bool", "default": True},
    "GLOBAL_MAX_INFLIGHT": {
        "type": "int",
        "default": 128,
        "minimum": 1,
        "maximum": 1024,
    },
    "MAX_INLINE_PAYLOAD_BYTES": {
        "type": "int",
        "default": 262144,
        "minimum": 1024,
        "maximum": 1048576,
    },
    "LEASE_SWEEP_SECONDS": {"type": "int", "default": 5, "minimum": 1, "maximum": 60},
    "DRAIN_GRACE_SECONDS": {"type": "int", "default": 5, "minimum": 1, "maximum": 60},
}


def _path(plugin):
    return Path(plugin.adapter.data_dir) / "series-control.json"


def _load(plugin):
    try:
        data = json.loads(_path(plugin).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _native(plugin, name):
    return plugin._config(name, FIELDS[name]["default"])


def _remember_native(plugin, name):
    saved = getattr(plugin, "_series_control_native_values", None)
    if saved is None:
        saved = plugin._series_control_native_values = {}
    if name not in saved:
        present = hasattr(plugin.config, "__contains__") and name in plugin.config
        saved[name] = (present, plugin._config(name, None) if present else None)


def _restore_native(plugin, fields):
    saved = getattr(plugin, "_series_control_native_values", {})
    for name in fields:
        if name not in saved:
            continue
        present, value = saved[name]
        if present:
            plugin.config[name] = value
        elif hasattr(plugin.config, "pop"):
            plugin.config.pop(name, None)


def contract(plugin):
    return {
        "name": "series.control@1.0",
        "version": "1.0",
        "series_id": "ningxin_suxi",
        "plugin_id": "astrbot_plugin_orchestration_hub",
        "plugin_name": "凝心溯溪-枢",
        "capabilities": [
            "read_schema",
            "read_snapshot",
            "validate_patch",
            "apply_patch",
            "reset_override",
        ],
        "read_only": False,
        "secrets_in_response": False,
        "max_patch_fields": len(FIELDS),
    }


def schema(plugin):
    return {
        "contract_name": "series.control@1.0",
        "contract_version": "1.0",
        "plugin_id": "astrbot_plugin_orchestration_hub",
        "revision": int(_load(plugin).get("revision", 0) or 0),
        "fields": {
            k: {
                **v,
                "control": "overrideable",
                "secret": False,
                "restart_required": False,
            }
            for k, v in FIELDS.items()
        },
    }


def snapshot(plugin):
    state = _load(plugin)
    overrides = (
        state.get("overrides", {})
        if isinstance(state.get("overrides", {}), dict)
        else {}
    )
    managed = getattr(plugin, "_series_control_mode", "native") == "managed"
    return {
        "status": "ok",
        "revision": int(state.get("revision", 0) or 0),
        "fields": {
            k: {
                "native_configured": True,
                "managed_configured": k in overrides,
                "effective_source": "managed"
                if managed and k in overrides
                else "plugin",
            }
            for k in FIELDS
        },
    }


def validate(plugin, patch, *, expected_revision):
    state = _load(plugin)
    current = int(state.get("revision", 0) or 0)
    if current != int(expected_revision):
        return {"valid": False, "reason": "REVISION_CONFLICT"}
    if not isinstance(patch, dict) or not patch or any(k not in FIELDS for k in patch):
        return {"valid": False, "reason": "PATCH_INVALID"}
    for k, v in patch.items():
        s = FIELDS[k]
        if s["type"] == "bool" and not isinstance(v, bool):
            return {"valid": False, "reason": "PATCH_INVALID"}
        if s["type"] == "int" and (
            not isinstance(v, int)
            or isinstance(v, bool)
            or not s["minimum"] <= v <= s["maximum"]
        ):
            return {"valid": False, "reason": "PATCH_INVALID"}
    return {"valid": True, "revision": current}


def _write(plugin, state):
    path = _path(plugin)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".series-control.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(state, h, ensure_ascii=False, sort_keys=True)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply(plugin, patch, *, expected_revision):
    result = validate(plugin, patch, expected_revision=expected_revision)
    if not result.get("valid"):
        return {"success": False, **result}
    state = _load(plugin)
    overrides = dict(state.get("overrides", {}) or {})
    overrides.update(patch)
    next_state = {
        "schema_version": 1,
        "revision": int(expected_revision) + 1,
        "overrides": overrides,
    }
    _write(plugin, next_state)
    if getattr(plugin, "_series_control_mode", "native") == "managed":
        for name in patch:
            _remember_native(plugin, name)
        plugin.config.update(patch)
    return {"success": True, "revision": next_state["revision"]}


def reset(plugin, fields=None, *, expected_revision=None):
    state = _load(plugin)
    current = int(state.get("revision", 0) or 0)
    if expected_revision is not None and current != int(expected_revision):
        return {"success": False, "reason": "REVISION_CONFLICT"}
    overrides = dict(state.get("overrides", {}) or {})
    for field in fields or list(overrides):
        overrides.pop(field, None)
    _write(
        plugin, {"schema_version": 1, "revision": current + 1, "overrides": overrides}
    )
    if getattr(plugin, "_series_control_mode", "native") == "managed":
        _restore_native(plugin, fields or list(getattr(plugin, "_series_control_native_values", {})))
    return {"success": True, "revision": current + 1}


def set_mode(plugin, mode):
    next_mode = mode if mode in {"native", "managed"} else "native"
    previous_mode = getattr(plugin, "_series_control_mode", "native")
    if next_mode == "native" and previous_mode == "managed":
        _restore_native(plugin, FIELDS)
    plugin._series_control_mode = next_mode
    if plugin._series_control_mode == "managed":
        overrides = _load(plugin).get("overrides", {}) or {}
        for name in overrides:
            if name in FIELDS:
                _remember_native(plugin, name)
        plugin.config.update({k: v for k, v in overrides.items() if k in FIELDS})
    return {"success": True, "mode": plugin._series_control_mode}
