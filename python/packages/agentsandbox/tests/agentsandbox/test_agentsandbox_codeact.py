# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agent_framework import AgentSession, ContextProvider, FunctionTool, SessionContext, SupportsAgentRun
from k8s_agent_sandbox import AsyncSandboxClient

from agent_framework_agentsandbox import AgentSandboxCodeActProvider, AgentSandboxExecuteCodeTool

WARMPOOL = "python-sandbox-pool"


def _fake_execution_result(stdout: str = "", stderr: str = "", exit_code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr=stderr, exit_code=exit_code)


def _fake_sandbox(execution_result: SimpleNamespace) -> tuple[SimpleNamespace, dict[str, Any]]:
    """Build a fake AsyncSandbox + a recorder dict so tests can assert on calls.

    The real SDK exposes ``files.write`` / ``commands.run`` / ``terminate`` as
    coroutines, so the fakes are ``async def`` to match.
    """
    recorder: dict[str, Any] = {"writes": [], "runs": [], "terminated": False}

    async def fake_write(path: str, content: str, timeout: int = 60) -> None:
        recorder["writes"].append((path, content, timeout))

    async def fake_run(command: str, timeout: int = 60) -> SimpleNamespace:
        recorder["runs"].append((command, timeout))
        return execution_result

    async def fake_terminate() -> None:
        recorder["terminated"] = True

    sandbox = SimpleNamespace(
        sandbox_id="sandbox-test",
        is_active=True,
        files=SimpleNamespace(write=fake_write),
        commands=SimpleNamespace(run=fake_run),
        terminate=fake_terminate,
    )
    return sandbox, recorder


class _FakeAsyncClient:
    """Fake AsyncSandboxClient that hands back a canned sandbox on create_sandbox()."""

    def __init__(self, sandbox: SimpleNamespace) -> None:
        self._sandbox = sandbox
        self.create_kwargs: dict[str, Any] | None = None
        self.closed = False

    async def create_sandbox(self, **kwargs: Any) -> SimpleNamespace:
        self.create_kwargs = kwargs
        return self._sandbox

    async def close(self) -> None:
        self.closed = True


def test_tool_is_a_function_tool() -> None:
    tool = AgentSandboxExecuteCodeTool(warmpool=WARMPOOL)
    assert isinstance(tool, FunctionTool)
    assert tool.name == "execute_code"
    assert tool.approval_mode == "never_require"


def test_provider_is_a_context_provider() -> None:
    provider = AgentSandboxCodeActProvider(warmpool=WARMPOOL)
    assert isinstance(provider, ContextProvider)
    assert provider.source_id == AgentSandboxCodeActProvider.DEFAULT_SOURCE_ID
    assert provider.execute_code_tool.name == "execute_code"


def test_tool_requires_warmpool() -> None:
    with pytest.raises(ValueError, match="warmpool is required"):
        AgentSandboxExecuteCodeTool(warmpool="")


async def test_run_code_happy_path() -> None:
    sandbox, recorder = _fake_sandbox(_fake_execution_result(stdout="832040\n", exit_code=0))
    client = _FakeAsyncClient(sandbox)

    tool = AgentSandboxExecuteCodeTool(
        warmpool=WARMPOOL,
        namespace="my-ns",
        shutdown_after_seconds=300,
        _client=cast("AsyncSandboxClient", client),
    )

    code = "print(sum(range(10)))"
    contents = await tool._run_code(code=code)

    # The tool should pass warmpool/namespace/timeout/labels/shutdown through.
    assert client.create_kwargs == {
        "warmpool": WARMPOOL,
        "namespace": "my-ns",
        "sandbox_ready_timeout": 180,
        "labels": None,
        "shutdown_after_seconds": 300,
    }
    # One write (the source file), one exec (python3 -u <file>).
    assert recorder["writes"] == [("_agent_sandbox_exec.py", code, 60)]
    assert recorder["runs"] == [("python3 -u _agent_sandbox_exec.py", 120)]
    # Stdout surfaces as a single text Content with trailing newline stripped.
    assert len(contents) == 1
    assert contents[0].type == "text"
    assert contents[0].text == "832040"


async def test_run_code_surfaces_error_on_nonzero_exit() -> None:
    sandbox, _ = _fake_sandbox(
        _fake_execution_result(stderr="Traceback...\nValueError: bad input\n", exit_code=1),
    )
    client = _FakeAsyncClient(sandbox)

    tool = AgentSandboxExecuteCodeTool(warmpool=WARMPOOL, _client=cast("AsyncSandboxClient", client))
    contents = await tool._run_code(code="raise ValueError('bad input')")

    error_contents = [c for c in contents if c.type == "error"]
    assert error_contents, "expected an error Content"
    assert "ValueError" in (error_contents[0].error_details or "")


async def test_run_code_empty_output_returns_friendly_text() -> None:
    sandbox, _ = _fake_sandbox(_fake_execution_result())
    client = _FakeAsyncClient(sandbox)

    tool = AgentSandboxExecuteCodeTool(warmpool=WARMPOOL, _client=cast("AsyncSandboxClient", client))
    contents = await tool._run_code(code="x = 1")

    assert len(contents) == 1
    assert contents[0].type == "text"
    assert contents[0].text is not None
    assert "without output" in contents[0].text


async def test_provider_before_run_injects_instructions_and_tool() -> None:
    sandbox, _ = _fake_sandbox(_fake_execution_result(stdout="ok\n"))
    client = _FakeAsyncClient(sandbox)

    provider = AgentSandboxCodeActProvider(
        warmpool=WARMPOOL,
        _client=cast("AsyncSandboxClient", client),
    )

    class FakeSessionContext:
        def __init__(self) -> None:
            self.instructions: dict[str, str] = {}
            self.tools: dict[str, list[Any]] = {}

        def extend_instructions(self, source_id: str, instructions: str) -> None:
            self.instructions[source_id] = instructions

        def extend_tools(self, source_id: str, tools: list[Any]) -> None:
            self.tools[source_id] = list(tools)

    ctx = FakeSessionContext()
    await provider.before_run(
        agent=cast("SupportsAgentRun", None),
        session=cast("AgentSession", None),
        context=cast("SessionContext", ctx),
        state={},
    )

    assert AgentSandboxCodeActProvider.DEFAULT_SOURCE_ID in ctx.instructions
    assert "execute_code" in ctx.instructions[AgentSandboxCodeActProvider.DEFAULT_SOURCE_ID]
    injected = ctx.tools[AgentSandboxCodeActProvider.DEFAULT_SOURCE_ID]
    assert len(injected) == 1
    assert injected[0].name == "execute_code"


async def test_close_terminates_sandbox_and_rejects_further_calls() -> None:
    sandbox, recorder = _fake_sandbox(_fake_execution_result(stdout="hi\n"))
    client = _FakeAsyncClient(sandbox)

    provider = AgentSandboxCodeActProvider(
        warmpool=WARMPOOL,
        _client=cast("AsyncSandboxClient", client),
    )
    # The concrete tool type exposes the internal _run_code; cast because the
    # pydantic mypy plugin widens the property's return to FunctionTool.
    tool = cast("AgentSandboxExecuteCodeTool", provider.execute_code_tool)
    # Trigger sandbox creation.
    await tool._run_code(code="print('hi')")
    assert recorder["terminated"] is False

    await provider.close()
    assert recorder["terminated"] is True
    # An injected client is not owned, so close() must leave it open for the caller.
    assert client.closed is False
    # Idempotent.
    await provider.close()

    with pytest.raises(RuntimeError, match="has been closed"):
        await tool._run_code(code="print('hi')")


async def test_provider_as_async_context_manager_cleans_up() -> None:
    sandbox, recorder = _fake_sandbox(_fake_execution_result(stdout="hi\n"))
    client = _FakeAsyncClient(sandbox)

    async with AgentSandboxCodeActProvider(
        warmpool=WARMPOOL,
        _client=cast("AsyncSandboxClient", client),
    ) as provider:
        tool = cast("AgentSandboxExecuteCodeTool", provider.execute_code_tool)
        await tool._run_code(code="print('hi')")

    assert recorder["terminated"] is True
    # Injected client is not owned, so it is left open for the caller.
    assert client.closed is False


async def test_close_during_in_flight_claim_terminates_new_sandbox() -> None:
    """close() must not leak a sandbox that is being claimed concurrently."""
    sandbox, recorder = _fake_sandbox(_fake_execution_result(stdout="hi\n"))
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowClient:
        def __init__(self) -> None:
            self.closed = False

        async def create_sandbox(self, **kwargs: Any) -> Any:
            started.set()
            await release.wait()  # hold the sandbox lock while close() blocks on it
            return sandbox

        async def close(self) -> None:
            self.closed = True

    slow_client = _SlowClient()
    provider = AgentSandboxCodeActProvider(
        warmpool=WARMPOOL,
        _client=cast("AsyncSandboxClient", slow_client),
    )
    tool = cast("AgentSandboxExecuteCodeTool", provider.execute_code_tool)

    claim = asyncio.create_task(tool._ensure_sandbox())
    await started.wait()  # _ensure_sandbox holds the lock, awaiting create_sandbox
    close_task = asyncio.create_task(provider.close())  # blocks on the same lock
    await asyncio.sleep(0)  # let close_task reach the lock
    release.set()  # let the claim finish
    await claim
    await close_task

    # The freshly claimed sandbox was terminated rather than orphaned.
    assert recorder["terminated"] is True
    # A subsequent claim is refused now that the tool is closed.
    with pytest.raises(RuntimeError, match="has been closed"):
        await tool._ensure_sandbox()
