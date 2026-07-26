import asyncio
import importlib
import sys
import types
from pathlib import Path

from ..core.models import CapabilityDescriptor, OperationDescriptor


def test_main_only_contains_lifecycle_assembly():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "class OrchestrationHubPlugin" in source
    assert "ServiceRegistry()" in source
    assert "async def terminate" in source
    assert '@filter.command_group("hub")' in source
    assert source.count("@hub_group.command(") == 3


def test_terminate_cleans_registry_invocation_task_and_store(tmp_path, monkeypatch):
    class CommandGroup:
        def command(self, _name):
            return lambda function: function

    def command_group(_name):
        def decorator(function):
            function.command = CommandGroup().command
            return function

        return decorator

    api = types.ModuleType("astrbot.api")
    api.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)
    event = types.ModuleType("astrbot.api.event")
    event.filter = types.SimpleNamespace(command_group=command_group)
    star = types.ModuleType("astrbot.api.star")
    star.Context = object
    star.Star = type("Star", (), {"__init__": lambda self, context: None})
    star.register = lambda *args, **kwargs: lambda cls: cls
    astrbot = types.ModuleType("astrbot")
    astrbot.api = api
    monkeypatch.setitem(sys.modules, "astrbot", astrbot)
    monkeypatch.setitem(sys.modules, "astrbot.api", api)
    monkeypatch.setitem(sys.modules, "astrbot.api.event", event)
    monkeypatch.setitem(sys.modules, "astrbot.api.star", star)

    main = importlib.import_module("..main", __package__)

    class Context:
        def get_plugin_data_dir(self, _plugin_id):
            return tmp_path

    async def scenario():
        plugin = main.OrchestrationHubPlugin(Context(), {"DRAIN_GRACE_SECONDS": 0})
        await plugin.initialize()
        token = await plugin.registry.register(
            CapabilityDescriptor(
                "nxsy.demo.echo",
                "1.0.0",
                "provider",
                {"echo": OperationDescriptor("echo")},
            ),
            lambda payload, context: asyncio.sleep(0, result=payload),
        )
        await plugin.registry.mark_ready(token)
        plugin.invocation._idempotent[("service", "operation", "key")] = object()
        await plugin.terminate()

        assert plugin._terminated
        assert plugin._lease_task is None
        assert await plugin.registry.snapshots() == []
        assert plugin.invocation._idempotent == {}
        assert plugin.store._closed
        audit = (tmp_path / "audit.jsonl").read_text("utf-8")
        assert '"action":"terminate"' in audit and '"result":"ok"' in audit

    asyncio.run(scenario())
