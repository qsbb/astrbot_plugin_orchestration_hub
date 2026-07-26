import asyncio

import pytest

from ..core.errors import ServiceNotFoundError, ServiceNotReadyError
from ..core.models import OperationDescriptor, ServiceDescriptor
from ..core.registry import ServiceRegistry


def descriptor(version="1.0.0"):
    return ServiceDescriptor(
        "nxsy.demo.echo", version, "stub", {"echo": OperationDescriptor("echo")}, frozenset({"stable"})
    )


async def handler(payload, context):
    return {"echo": payload["value"], "caller": context.caller_plugin}


def test_register_ready_snapshot_and_stale_unregister():
    async def scenario():
        registry = ServiceRegistry()
        token = await registry.register(descriptor(), handler)
        with pytest.raises(ServiceNotReadyError):
            from ..core.resolver import ServiceResolver
            await ServiceResolver(registry, object()).resolve("nxsy.demo.echo", caller_plugin="caller")
        await registry.mark_ready(token)
        snapshots = await registry.snapshots()
        assert snapshots[0].state == "READY"
        await registry.unregister(token)
        assert await registry.snapshots() == []

    asyncio.run(scenario())


def test_duplicate_registration_drains_old_generation():
    async def scenario():
        registry = ServiceRegistry()
        first = await registry.register(descriptor(), handler)
        await registry.mark_ready(first)
        second = await registry.register(descriptor(), handler)
        assert second.generation == 2
        states = {item.token.generation: item.state for item in await registry.snapshots()}
        assert states == {1: "DRAINING", 2: "REGISTERED"}

    asyncio.run(scenario())


def test_hot_reload_leaves_only_new_generation_resolvable():
    async def scenario():
        registry = ServiceRegistry()
        first = await registry.register(descriptor(), handler)
        await registry.mark_ready(first)
        second = await registry.register(descriptor(), handler)
        await registry.mark_ready(second)

        from ..core.resolver import ServiceResolver

        handle = await ServiceResolver(registry, object()).resolve("nxsy.demo.echo", caller_plugin="caller")
        assert handle.token == second
        assert {item.token.generation: item.state for item in await registry.snapshots()} == {
            1: "DRAINING",
            2: "READY",
        }

    asyncio.run(scenario())


def test_plugin_missing_service_is_reported():
    async def scenario():
        from ..core.resolver import ServiceResolver
        with pytest.raises(ServiceNotFoundError):
            await ServiceResolver(ServiceRegistry(), object()).resolve("nxsy.missing.echo", caller_plugin="caller")

    asyncio.run(scenario())
