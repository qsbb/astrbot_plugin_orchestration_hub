from types import SimpleNamespace

from .. import series_control


def _plugin(tmp_path, config=None):
    return SimpleNamespace(
        config=dict(config or {"ENABLED": True}),
        adapter=SimpleNamespace(data_dir=tmp_path),
        _config=lambda key, default: dict(config or {"ENABLED": True}).get(key, default),
    )


def test_contract_and_schema_are_scoped_to_safe_hub_limits(tmp_path):
    plugin = _plugin(tmp_path)
    assert series_control.contract(plugin)["name"] == "series.control@1.0"
    assert set(series_control.schema(plugin)["fields"]) == {
        "ENABLED",
        "GLOBAL_MAX_INFLIGHT",
        "MAX_INLINE_PAYLOAD_BYTES",
        "LEASE_SWEEP_SECONDS",
        "DRAIN_GRACE_SECONDS",
    }


def test_managed_override_restores_native_mode(tmp_path):
    plugin = _plugin(tmp_path, {"ENABLED": True, "GLOBAL_MAX_INFLIGHT": 8})
    series_control.set_mode(plugin, "managed")
    assert series_control.apply(plugin, {"GLOBAL_MAX_INFLIGHT": 32}, expected_revision=0) == {"success": True, "revision": 1}
    assert plugin.config["GLOBAL_MAX_INFLIGHT"] == 32
    series_control.set_mode(plugin, "native")
    assert plugin.config["GLOBAL_MAX_INFLIGHT"] == 8


def test_validation_rejects_unknown_out_of_range_and_stale_revision(tmp_path):
    plugin = _plugin(tmp_path)
    assert series_control.validate(plugin, {"NOT_A_LIMIT": 1}, expected_revision=0)["reason"] == "PATCH_INVALID"
    assert series_control.validate(plugin, {"GLOBAL_MAX_INFLIGHT": 0}, expected_revision=0)["reason"] == "PATCH_INVALID"
    assert series_control.validate(plugin, {"ENABLED": False}, expected_revision=1)["reason"] == "REVISION_CONFLICT"
