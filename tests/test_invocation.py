import asyncio

import pytest

from ..core.errors import DeadlineExceededError, PermissionDeniedError, ServiceNotReadyError
from ..core.invocation import InvocationEngine
from ..core.models import OperationDescriptor, ServiceDescriptor
from ..core.policy import PolicyEngine, PolicyRule
from ..core.registry import ServiceRegistry
from ..core.resolver import ServiceResolver, satisfies
from ..core.telemetry import Telemetry


def desc(timeout=100):
    return ServiceDescriptor("nxsy.demo.echo", "1.2.0", "stub", {"echo": OperationDescriptor("echo", timeout_ms=timeout, permission="nxsy.demo.echo:echo")}, frozenset({"stable"}))


def test_resolve_call_and_telemetry():
    async def scenario():
        async def handler(payload, context):
            return {"value": payload["value"], "request_id": context.request_id}

        registry, policy, telemetry = ServiceRegistry(), PolicyEngine(), Telemetry()
        policy.set_rules([PolicyRule("caller", "nxsy.demo.echo", "echo")])
        token = await registry.register(desc(), handler)
        await registry.mark_ready(token)
        engine = InvocationEngine(registry, policy, telemetry)
        handle = await ServiceResolver(registry, policy, engine).resolve("nxsy.demo.echo", ">=1.0.0,<2.0.0", {"stable"}, "caller")
        assert (await handle.call("echo", {"value": "ok"}))['value'] == "ok"
        assert telemetry.summary()["counts"][0]["result"] == "ok"

    asyncio.run(scenario())


def test_provider_timeout_is_bounded():
    async def scenario():
        async def slow(payload, context):
            await asyncio.sleep(0.05)
            return payload

        registry, policy = ServiceRegistry(), PolicyEngine()
        policy.set_rules([PolicyRule("caller", "nxsy.demo.echo", "echo")])
        token = await registry.register(desc(timeout=5), slow)
        await registry.mark_ready(token)
        engine = InvocationEngine(registry, policy, Telemetry())
        handle = await ServiceResolver(registry, policy, engine).resolve("nxsy.demo.echo", caller_plugin="caller")
        with pytest.raises(DeadlineExceededError):
            await handle.call("echo", {})

    asyncio.run(scenario())


def test_permission_denied_before_handler():
    async def scenario():
        called = False

        async def handler(payload, context):
            nonlocal called
            called = True
            return payload

        registry, policy = ServiceRegistry(), PolicyEngine()
        token = await registry.register(desc(), handler)
        await registry.mark_ready(token)
        engine = InvocationEngine(registry, policy, Telemetry())
        handle = await ServiceResolver(registry, policy, engine).resolve("nxsy.demo.echo", caller_plugin="caller")
        with pytest.raises(PermissionDeniedError):
            await handle.call("echo", {})
        assert not called

    asyncio.run(scenario())


def test_incompatible_contract_version_is_not_resolved():
    async def scenario():
        registry = ServiceRegistry()
        token = await registry.register(desc(), lambda payload, context: asyncio.sleep(0, result=payload))
        await registry.mark_ready(token)
        with pytest.raises(ServiceNotReadyError):
            await ServiceResolver(registry, PolicyEngine()).resolve("nxsy.demo.echo", caller_plugin="caller", contract_version="2.0")

    asyncio.run(scenario())


def test_version_constraint():
    assert satisfies("1.2.0", ">=1.0.0,<2.0.0")
    assert not satisfies("2.0.0", ">=1.0.0,<2.0.0")
