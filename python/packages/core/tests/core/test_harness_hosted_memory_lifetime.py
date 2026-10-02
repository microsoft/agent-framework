# Copyright (c) Microsoft. All rights reserved.
"""Offline verification of the hosted sample's actual request/stream protection."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from agent_framework import (
    AgentContext,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    FileMemoryProvider,
    FileMemoryRetentionManager,
    Message,
    ResponseStream,
)
from agent_framework._sessions import SessionContext


def _load_hosted(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    pytest.importorskip("agent_framework_foundry_hosting")
    pytest.importorskip("agent_framework_monty")
    pytest.importorskip("azure.ai.agentserver.core")
    sample = Path(__file__).parents[4] / "samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready"
    monkeypatch.syspath_prepend(str(sample))

    def load(name: str, path: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    load("agent", sample / "agent.py")
    return load("_file_memory_hosted_sample", sample / "hosted.py")


async def _agent(monkeypatch: pytest.MonkeyPatch, directory: Path, manager: FileMemoryRetentionManager) -> Any:
    hosted = _load_hosted(monkeypatch)
    monkeypatch.setattr(hosted.Path, "home", lambda: directory)
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "offline-test")
    monkeypatch.setattr(hosted, "AgentConfig", SimpleNamespace(from_env=lambda: SimpleNamespace(is_hosted=False)))
    monkeypatch.setattr(hosted, "get_request_context", lambda: SimpleNamespace(platform_headers=lambda: {}))
    monkeypatch.setattr(
        hosted,
        "FoundryRequestScope",
        SimpleNamespace(from_context=lambda *args, **kwargs: SimpleNamespace(storage_key="owner")),
    )
    monkeypatch.setattr(hosted, "AzureCliCredential", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(hosted, "_build_purview_middleware", lambda credential: [])

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            pass

    monkeypatch.setattr(hosted, "FoundryChatClient", Client)

    async def build(**kwargs: Any) -> Any:
        return SimpleNamespace(context_providers=[kwargs["file_memory_provider"]], middleware=[])

    monkeypatch.setattr(hosted, "build_claw_agent", build)
    return await hosted.create_agent(retention=manager)


@pytest.mark.parametrize("ending", ["normal", "close", "cancel", "error"])
async def test_hosted_stream_keeps_lease_until_actual_consumption_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ending: str
) -> None:
    directory = tmp_path / ".claw/agent-file-memory"
    manager = FileMemoryRetentionManager(directory, retention_seconds=10)
    now = [100.0]
    manager._now = lambda: now[0]
    agent = await _agent(monkeypatch, tmp_path, manager)
    provider: FileMemoryProvider = agent.context_providers[0]
    context = SessionContext(session_id="conversation", input_messages=[])
    await provider.before_run(agent=None, session=AgentSession(session_id="conversation"), context=context, state={})
    tools = {tool.name: tool for tool in context.tools}
    await tools["file_memory_write"].invoke(arguments={"file_name": "notes.md", "content": "hello"})
    now[0] = 109
    first, gate = asyncio.Event(), asyncio.Event()

    async def source() -> AsyncIterator[AgentResponseUpdate]:
        yield AgentResponseUpdate(role="assistant")
        if ending == "cancel":
            await gate.wait()
        if ending == "error":
            raise RuntimeError("upstream failure")

    inner: ResponseStream[AgentResponseUpdate, AgentResponse] = ResponseStream(
        source(), finalizer=lambda _: AgentResponse(messages=[Message(role="assistant", contents=["done"])])
    )
    run_context = AgentContext(agent=agent, messages=[], session=AgentSession(session_id="conversation"), stream=True)

    async def next_call() -> None:
        run_context.result = inner

    await agent.middleware[0](run_context, next_call)
    stream = run_context.result
    assert isinstance(stream, ResponseStream)
    now[0] = 120
    assert await manager.collect() == 0

    async def consume() -> None:
        async for _ in stream:
            first.set()
        await stream.get_final_response()

    if ending == "close":
        await stream.close()
        await stream.close()
    elif ending == "cancel":
        consumer = asyncio.create_task(consume())
        await asyncio.wait_for(first.wait(), 5)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(consumer, 5)
    elif ending == "error":
        with pytest.raises(RuntimeError, match="upstream failure"):
            await consume()
    else:
        await consume()

    assert await manager.collect() == 1
    assert await provider.store.read("conversation/notes.md") is None


async def test_hosted_nonstream_failure_releases_request_lease(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / ".claw/agent-file-memory"
    manager = FileMemoryRetentionManager(directory, retention_seconds=10)
    agent = await _agent(monkeypatch, tmp_path, manager)
    context = AgentContext(agent=agent, messages=[], session=AgentSession(session_id="conversation"))

    async def fail() -> None:
        raise RuntimeError("model failed")

    with pytest.raises(RuntimeError, match="model failed"):
        await agent.middleware[0](context, fail)
    assert not await asyncio.to_thread(lambda: list((directory / ".retention/active").rglob("*.lock")))


async def test_hosted_server_runs_gc_without_receiving_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosted = _load_hosted(monkeypatch)
    monkeypatch.setattr(hosted.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CLAW_FILE_MEMORY_RETENTION_SECONDS", "1")
    monkeypatch.setenv("CLAW_FILE_MEMORY_SWEEP_INTERVAL_SECONDS", "1")
    swept = asyncio.Event()

    async def collect(self: FileMemoryRetentionManager) -> int:
        swept.set()
        return 0

    class Server:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def run_async(self) -> None:
            await asyncio.wait_for(swept.wait(), 5)

    monkeypatch.setattr(hosted.FileMemoryRetentionManager, "collect", collect)
    monkeypatch.setattr(hosted, "ResponsesHostServer", Server)
    await hosted.main()
    assert swept.is_set()
