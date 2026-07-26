import asyncio
import json
from pathlib import Path

import pytest

from ..adapters.storage import DataStore
from ..core.errors import ProviderUnavailableError, ResourceExhaustedError, SchemaValidationError
from ..core.invocation import InvocationEngine
from ..core.models import CallContext, CapabilityDescriptor, OperationDescriptor, ServiceResponse
from ..core.policy import PolicyEngine, PolicyRule
from ..core.registry import ServiceRegistry
from ..core.resolver import ServiceResolver
from ..core.telemetry import Telemetry


INPUT = {"type": "object", "required": ["value"], "properties": {"value": {"type": "string"}}, "additionalProperties": False}
OUTPUT = {"type": "object", "required": ["value"], "properties": {"value": {"type": "string"}}, "additionalProperties": False}


def capability(max_inflight=1, queue_size=0):
    return CapabilityDescriptor("nxsy.demo.echo", "1.0.0", "provider", {"echo": OperationDescriptor("echo", permission="echo", input_schema=INPUT, output_schema=OUTPUT, max_inflight=max_inflight, queue_size=queue_size)})


def test_required_public_contract_models():
    descriptor = capability()
    descriptor.validate()
    context = CallContext.create("nxsy.demo.echo", "echo", "caller", "provider:1", 100, "1.0", 3)
    response = ServiceResponse(context.request_id, context.trace_id, context.provider_instance_id, "ok", {"value": "ok"})
    assert descriptor.contract_version == "1.0"
    assert context.trace_id and response.ok


def test_lease_expiry_and_renewal():
    async def scenario():
        registry = ServiceRegistry(default_lease_seconds=0.02)
        token = await registry.register(capability(), lambda payload, context: asyncio.sleep(0, result=payload))
        await registry.renew(token, 0.03)
        await registry.mark_ready(token)
        await asyncio.sleep(0.04)
        with pytest.raises(ProviderUnavailableError):
            await registry.acquire(token)
        assert (await registry.snapshots())[0].state == "EXPIRED"

    asyncio.run(scenario())


def test_schema_response_trace_and_concurrency():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def handler(payload, context):
            started.set()
            await release.wait()
            return payload

        registry, policy, telemetry = ServiceRegistry(), PolicyEngine(), Telemetry()
        policy.set_rules([PolicyRule("caller", "nxsy.demo.echo", "echo")])
        token = await registry.register(capability(), handler)
        await registry.mark_ready(token)
        handle = await ServiceResolver(registry, policy, InvocationEngine(registry, policy, telemetry)).resolve("nxsy.demo.echo", caller_plugin="caller")
        with pytest.raises(SchemaValidationError):
            await handle.call("echo", {"wrong": 1})
        first = asyncio.create_task(handle.call("echo", {"value": "ok"}, return_response=True))
        await started.wait()
        with pytest.raises(ResourceExhaustedError):
            await handle.call("echo", {"value": "busy"})
        release.set()
        response = await first
        assert response.ok and response.trace_id
        assert telemetry.trace(response.trace_id)[0]["request_id"] == response.request_id

    asyncio.run(scenario())


def test_data_snapshot_and_audit_never_persist_payload(tmp_path: Path):
    async def scenario():
        store = DataStore(tmp_path)
        await store.open()
        await store.write_snapshot({"service": "nxsy.demo.echo", "payload": {"secret": "raw"}, "metadata": {"message": "private"}})
        await store.append_audit({"action": "call", "payload": {"secret": "raw"}, "trace_id": "t"})
        await store.close()
        snapshot_path = tmp_path / "registry_snapshot.json"
        snapshot = json.loads(snapshot_path.read_text("utf-8"))
        audit = json.loads((tmp_path / "audit.jsonl").read_text("utf-8"))
        assert "payload" not in snapshot and "payload" not in audit
        assert "raw" not in snapshot_path.read_text("utf-8")
        assert "raw" not in (tmp_path / "audit.jsonl").read_text("utf-8")
        assert not (tmp_path / "snapshot.json").exists()

    asyncio.run(scenario())


def test_hub_has_exact_three_subcommands():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text("utf-8")
    assert '@filter.command_group("hub")' in source
    assert source.count("@hub_group.command(") == 3
    for name in ("status", "services", "diagnose"):
        assert f'@hub_group.command("{name}")' in source
    assert '@hub_group.command("probe")' not in source
