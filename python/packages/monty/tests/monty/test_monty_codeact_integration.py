# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for ``agent_framework_monty`` exercising the real Monty runtime.

These tests import the real ``pydantic-monty`` package and run actual Python
code through it via :class:`MontyExecuteCodeTool`. They are marked
``@pytest.mark.integration`` and are skipped automatically when
``pydantic_monty`` is unavailable.
"""

from __future__ import annotations

import asyncio
import importlib.util
import time
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from agent_framework import Agent, Content, Message, tool
from agent_framework._sessions import SessionContext

from agent_framework_monty import MontyCodeActProvider, MontyExecuteCodeTool


def _monty_integration_skip_reason() -> str | None:
    if importlib.util.find_spec("pydantic_monty") is None:
        return "pydantic-monty is not installed."
    return None


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _monty_integration_skip_reason() is not None,
        reason=_monty_integration_skip_reason() or "Monty integration tests are disabled.",
    ),
]


# ---------------------------------------------------------------------------
# Sample tools
# ---------------------------------------------------------------------------


@tool
def add(
    a: Annotated[int, "First addend"],
    b: Annotated[int, "Second addend"],
) -> int:
    """Return ``a + b``."""
    return a + b


@tool
def multiply(
    a: Annotated[int, "First factor"],
    b: Annotated[int, "Second factor"],
) -> int:
    """Return ``a * b``."""
    return a * b


@tool
async def async_echo(value: Annotated[str, "Value to echo"]) -> str:
    """Return ``value`` after a no-op await."""
    await asyncio.sleep(0)
    return value


def _async_slow_factory(label: str, delay: float) -> Any:
    @tool(name=f"slow_{label}")
    async def slow(value: Annotated[int, "Input"]) -> int:
        """Sleep asynchronously, then return value untouched."""
        await asyncio.sleep(delay)
        return value

    return slow


@tool(approval_mode="always_require")
def restricted(payload: Annotated[str, "Any text"]) -> str:
    """A tool that always requires approval."""
    return payload


def _text_outputs(contents: list[Content]) -> list[str]:
    return [c.text or "" for c in contents if c.type == "text"]


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------


async def test_plain_python_print_round_trips() -> None:
    monty_tool = MontyExecuteCodeTool()
    result = await monty_tool._run_code(code="print('hello world')")

    texts = _text_outputs(result)
    assert any("hello world" in text for text in texts)


async def test_last_expression_value_is_returned() -> None:
    monty_tool = MontyExecuteCodeTool()
    result = await monty_tool._run_code(code="5 + 7")

    texts = _text_outputs(result)
    assert any(text.strip() == "12" for text in texts)


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


async def test_direct_typed_tool_call_invokes_host() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add])
    result = await monty_tool._run_code(code="print(await add(a=2, b=3))")

    texts = _text_outputs(result)
    assert any("5" in text for text in texts)


async def test_call_tool_fallback_invokes_host() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add])
    result = await monty_tool._run_code(code="print(await call_tool('add', a=4, b=8))")

    texts = _text_outputs(result)
    assert any("12" in text for text in texts)


async def test_async_host_tool_is_awaited() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[async_echo])
    result = await monty_tool._run_code(code="print(await async_echo(value='ping'))")

    texts = _text_outputs(result)
    assert any("ping" in text for text in texts)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


async def test_asyncio_gather_fans_out_tool_calls_concurrently() -> None:
    """Two async tools dispatched via ``asyncio.gather`` should run on the event loop in parallel.

    Sync tools cannot fan out (FunctionTool.invoke runs them inline on the event loop),
    so this test uses async host tools to verify the bridge's gather pipeline does
    not introduce extra serialization.
    """
    slow_a = _async_slow_factory("a", delay=0.25)
    slow_b = _async_slow_factory("b", delay=0.25)
    monty_tool = MontyExecuteCodeTool(tools=[slow_a, slow_b])

    code = """
results = await asyncio.gather(slow_a(value=1), slow_b(value=2))
print(results)
"""

    start = time.perf_counter()
    result = await monty_tool._run_code(code=code)
    elapsed = time.perf_counter() - start

    texts = _text_outputs(result)
    assert any("[1, 2]" in text for text in texts)
    # Allow some scheduling slack but verify it's noticeably less than sequential (~0.5s).
    assert elapsed < 0.45, f"Expected concurrent execution; took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Sandbox safety + type checking
# ---------------------------------------------------------------------------


async def test_type_check_rejects_wrong_argument_type() -> None:
    invocation_count = {"count": 0}

    @tool
    def typed_add(
        a: Annotated[int, "First"],
        b: Annotated[int, "Second"],
    ) -> int:
        """Add two ints; records invocations."""
        invocation_count["count"] += 1
        return a + b

    monty_tool = MontyExecuteCodeTool(tools=[typed_add])
    result = await monty_tool._run_code(code="print(await typed_add(a='not an int', b=3))")

    texts = _text_outputs(result)
    errors = [c for c in result if c.type == "error"]
    # Either ty raises and surfaces as an error Content, or Monty reports the typing error in stdout.
    assert errors or any("type" in text.lower() or "monty" in text.lower() for text in texts)
    assert invocation_count["count"] == 0


async def test_os_calls_are_blocked() -> None:
    monty_tool = MontyExecuteCodeTool()
    code = """
try:
    import os
    os.listdir('/')
    print('LEAKED')
except PermissionError as exc:
    print('blocked:', exc)
except Exception as exc:
    print('other:', type(exc).__name__)
"""
    result = await monty_tool._run_code(code=code)
    texts = _text_outputs(result)
    assert not any("LEAKED" in text for text in texts)
    assert any("blocked" in text or "PermissionError" in text or "other" in text for text in texts)


async def test_unknown_tool_call_returns_clean_error() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add])
    code = """
try:
    await call_tool('missing')
except Exception as exc:
    print('err:', type(exc).__name__, str(exc))
"""
    result = await monty_tool._run_code(code=code)
    texts = _text_outputs(result)
    assert any("missing" in text for text in texts)


# ---------------------------------------------------------------------------
# Print capture
# ---------------------------------------------------------------------------


async def test_print_truncation_caps_output() -> None:
    monty_tool = MontyExecuteCodeTool()
    # Emit more than MAX_PRINT_OUTPUT_CHARS bytes of output.
    code = """
for _ in range(2000):
    print('X' * 64)
"""
    result = await monty_tool._run_code(code=code)
    texts = _text_outputs(result)
    combined = "\n".join(texts)
    assert len(combined) <= 9000  # MAX_PRINT_OUTPUT_CHARS=8192 plus a small truncation marker
    assert "[stdout truncated]" in combined


# ---------------------------------------------------------------------------
# Filesystem (workspace_root, file_mounts, output capture, resource limits)
# ---------------------------------------------------------------------------


async def test_workspace_root_reads_seed_files_from_host(tmp_path: Any) -> None:
    seed = tmp_path / "seed.txt"
    seed.write_text("hello from host", encoding="utf-8")
    monty_tool = MontyExecuteCodeTool(workspace_root=tmp_path)

    code = """
import pathlib
data = pathlib.Path('/input/seed.txt').read_text()
print(data)
"""
    result = await monty_tool._run_code(code=code)
    texts = _text_outputs(result)
    assert any("hello from host" in text for text in texts)


async def test_workspace_root_writes_are_captured_as_content(tmp_path: Any) -> None:
    monty_tool = MontyExecuteCodeTool(workspace_root=tmp_path)

    code = """
import pathlib
pathlib.Path('/input/report.txt').write_text('result-payload')
print('wrote report')
"""
    result = await monty_tool._run_code(code=code)
    data_contents = [c for c in result if c.type == "data"]
    assert len(data_contents) == 1, [c.type for c in result]
    written = data_contents[0]
    # Content.from_data stores bytes as a base64-encoded data: URI.
    import base64

    assert written.uri is not None
    payload = written.uri.split(",", 1)[1]
    assert base64.b64decode(payload) == b"result-payload"
    assert (written.additional_properties or {}).get("path") == "/input/report.txt"
    # And the file actually landed on the host filesystem (read-write mode).
    assert (tmp_path / "report.txt").read_text() == "result-payload"


async def test_read_only_mount_writes_are_rejected_and_not_captured(tmp_path: Any) -> None:
    from agent_framework_monty import FileMount

    seed = tmp_path / "seed.txt"
    seed.write_text("ro-content", encoding="utf-8")

    monty_tool = MontyExecuteCodeTool(
        file_mounts=[FileMount(host_path=tmp_path, mount_path="/ro", mode="read-only")],
    )

    code = """
import pathlib
print(pathlib.Path('/ro/seed.txt').read_text())
try:
    pathlib.Path('/ro/should-not-exist.txt').write_text('nope')
    print('LEAKED')
except Exception as exc:
    print('write blocked:', type(exc).__name__)
"""
    result = await monty_tool._run_code(code=code)
    texts = _text_outputs(result)
    assert any("ro-content" in t for t in texts)
    assert not any("LEAKED" in t for t in texts)
    # No write went to host; no captured Content for the rejected write.
    assert not (tmp_path / "should-not-exist.txt").exists()
    assert not any(c.type == "data" for c in result)


async def test_overlay_mount_writes_do_not_persist_to_host(tmp_path: Any) -> None:
    from agent_framework_monty import FileMount

    monty_tool = MontyExecuteCodeTool(
        file_mounts=[FileMount(host_path=tmp_path, mount_path="/overlay", mode="overlay")],
    )

    code = """
import pathlib
pathlib.Path('/overlay/scratch.txt').write_text('overlay-only')
print('wrote')
"""
    result = await monty_tool._run_code(code=code)
    assert any("wrote" in t for t in _text_outputs(result))
    # Overlay writes stay in-memory: nothing on host, nothing captured.
    assert not (tmp_path / "scratch.txt").exists()
    assert not any(c.type == "data" for c in result)


async def test_resource_limit_short_duration_aborts_long_loop() -> None:
    # Cap CPU time hard; a busy loop should be killed before it can print 'done'.
    monty_tool = MontyExecuteCodeTool(resource_limits={"max_duration_secs": 0.2})

    code = """
total = 0
for i in range(10_000_000):
    total += i
print('done', total)
"""
    result = await monty_tool._run_code(code=code)
    # Result is either an error Content (timeout surfaces as RuntimeError) or
    # truncated stdout without the 'done' marker.
    texts = _text_outputs(result)
    assert not any("done" in t for t in texts), texts


# ---------------------------------------------------------------------------
# Symlink escape regression (MSRC-style)
# ---------------------------------------------------------------------------


def _symlinks_supported(tmp: Any) -> bool:
    """Return True if the current platform/environment supports symlinks.

    Mirrors python/packages/core/tests/core/test_skills.py so the symlink
    regression tests are skipped on restricted Windows CI runners instead of
    failing on ``OSError`` / ``NotImplementedError`` during creation.
    """
    test_target = tmp / "_symlink_test_target"
    test_link = tmp / "_symlink_test_link"
    try:
        test_target.write_text("test", encoding="utf-8")
        test_link.symlink_to(test_target)
        return True
    except (OSError, NotImplementedError):
        return False
    finally:
        test_link.unlink(missing_ok=True)
        test_target.unlink(missing_ok=True)


async def test_symlinks_inside_workspace_are_not_followed_by_runtime(tmp_path: Any) -> None:
    """A pre-existing symlink in workspace_root must NOT let sandbox code read its target.

    Monty's mount layer enforces this (PermissionError at the OS bridge), but we
    pin the behavior here so any future change to the OS dispatch path is
    detected.
    """
    if not _symlinks_supported(tmp_path):
        pytest.skip("Symlinks not supported on this platform/environment")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("SECRET_OUTSIDE_WORKSPACE", encoding="utf-8")
    (workspace / "leak.txt").symlink_to(outside)

    monty_tool = MontyExecuteCodeTool(workspace_root=workspace)
    code = """
import pathlib
try:
    print('read:', pathlib.Path('/input/leak.txt').read_text())
except PermissionError as exc:
    print('blocked:', exc)
except Exception as exc:
    print('other:', type(exc).__name__, exc)
"""
    result = await monty_tool._run_code(code=code)
    texts = _text_outputs(result)
    assert not any("SECRET_OUTSIDE_WORKSPACE" in t for t in texts), texts
    assert any("blocked" in t or "PermissionError" in t or "other" in t for t in texts), texts


async def test_post_capture_skips_symlinks_pointing_outside_workspace(tmp_path: Any) -> None:
    """File capture must NOT read through a symlink that points outside the mount.

    Reproduces the MSRC-reported Hyperlight pattern in Monty's post-execution
    file-capture path: an attacker-placed ``workspace/leak.txt -> /outside/secret``
    must not be returned as Content.
    """
    if not _symlinks_supported(tmp_path):
        pytest.skip("Symlinks not supported on this platform/environment")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("SECRET_OUTSIDE_WORKSPACE", encoding="utf-8")
    (workspace / "leak.txt").symlink_to(outside)
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "deep.txt").write_text("DEEP_SECRET", encoding="utf-8")
    (workspace / "leak_dir").symlink_to(outside_dir)

    monty_tool = MontyExecuteCodeTool(workspace_root=workspace)
    # Run trivial code so the post-execution scan fires.
    result = await monty_tool._run_code(code="print('ran')")

    # Inspect the URIs of any returned data Content items.
    import base64

    leaked_paths: list[str] = []
    leaked_bodies: list[bytes] = []
    for content in result:
        if content.type != "data" or not content.uri:
            continue
        payload = content.uri.split(",", 1)[1] if "," in content.uri else ""
        try:
            body = base64.b64decode(payload)
        except Exception:  # noqa: BLE001
            body = b""
        leaked_bodies.append(body)
        leaked_paths.append((content.additional_properties or {}).get("path", ""))

    assert not any(b"SECRET_OUTSIDE_WORKSPACE" in body for body in leaked_bodies), (
        "Symlink file outside workspace was captured: " + repr(leaked_paths)
    )
    assert not any(b"DEEP_SECRET" in body for body in leaked_bodies), (
        "Symlinked directory escape was captured: " + repr(leaked_paths)
    )


async def test_post_capture_still_returns_real_writes_when_symlinks_present(tmp_path: Any) -> None:
    """The symlink-skipping logic must not regress capture of legitimate sandbox writes."""
    if not _symlinks_supported(tmp_path):
        pytest.skip("Symlinks not supported on this platform/environment")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("SHOULD_NEVER_LEAK", encoding="utf-8")
    (workspace / "leak.txt").symlink_to(outside)

    monty_tool = MontyExecuteCodeTool(workspace_root=workspace)
    code = """
import pathlib
pathlib.Path('/input/report.txt').write_text('legit-output')
print('wrote')
"""
    result = await monty_tool._run_code(code=code)
    import base64

    data_items = [c for c in result if c.type == "data" and c.uri]
    # Exactly one new file should be captured: report.txt.
    assert len(data_items) == 1, [(c.additional_properties or {}).get("path") for c in data_items]
    item = data_items[0]
    assert (item.additional_properties or {}).get("path") == "/input/report.txt"
    payload = item.uri.split(",", 1)[1] if item.uri and "," in item.uri else ""
    assert base64.b64decode(payload) == b"legit-output"


# ---------------------------------------------------------------------------
# Provider + approval gating
# ---------------------------------------------------------------------------


async def test_provider_run_tool_executes_real_monty_end_to_end() -> None:
    provider = MontyCodeActProvider(tools=[add])
    context = SessionContext(input_messages=[Message(role="user", contents=[Content.from_text("hi")])])
    state: dict[str, Any] = {}

    await provider.before_run(agent=MagicMock(), session=None, context=context, state=state)

    run_tool = context.tools[0]
    assert isinstance(run_tool, MontyExecuteCodeTool)

    result = await run_tool._run_code(code="print(await add(a=10, b=32))")
    texts = _text_outputs(result)
    assert any("42" in text for text in texts)


async def test_approval_required_tool_gates_execute_code_end_to_end() -> None:
    provider = MontyCodeActProvider(tools=[restricted])
    context = SessionContext(input_messages=[Message(role="user", contents=[Content.from_text("hi")])])
    state: dict[str, Any] = {}

    await provider.before_run(agent=MagicMock(), session=None, context=context, state=state)
    run_tool = context.tools[0]
    assert isinstance(run_tool, MontyExecuteCodeTool)
    assert run_tool.approval_mode == "always_require"
    assert state["monty_codeact"]["approval_mode"] == "always_require"


# ---------------------------------------------------------------------------
# End-to-end Agent run with a fake chat client
# ---------------------------------------------------------------------------


async def test_agent_runs_monty_codeact_end_to_end() -> None:
    """A fake chat client emits one execute_code tool call; Monty runs it end-to-end."""
    from collections.abc import Awaitable, Mapping, MutableSequence

    from agent_framework import (
        BaseChatClient,
        ChatResponse,
        ChatResponseUpdate,
        FunctionInvocationLayer,
        ResponseStream,
    )

    class _FakeCodeActChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)
            self.call_count = 0

        def _inner_get_response(
            self,
            *,
            messages: MutableSequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            if stream:
                raise AssertionError("Streaming is not used in this integration test.")

            async def _get_response() -> ChatResponse:
                self.call_count += 1

                if self.call_count == 1:
                    return ChatResponse(
                        messages=Message(
                            role="assistant",
                            contents=[
                                Content.from_function_call(
                                    call_id="execute_code_call",
                                    name="execute_code",
                                    arguments={"code": "print(await add(a=6, b=7))"},
                                )
                            ],
                        )
                    )

                function_results = [
                    content for message in messages for content in message.contents if content.type == "function_result"
                ]
                assert len(function_results) == 1

                result_content = function_results[0]
                result_text = ""
                if isinstance(result_content.result, list):
                    for item in result_content.result:
                        text = getattr(item, "text", None)
                        if text:
                            result_text += text
                else:
                    result_text = str(result_content.result or "")

                return ChatResponse(
                    messages=Message(
                        role="assistant",
                        contents=[f"answer: {result_text.strip() or 'none'}"],
                    )
                )

            return _get_response()

    client = _FakeCodeActChatClient()
    provider = MontyCodeActProvider(tools=[add])
    agent = Agent(client=client, context_providers=[provider])

    response = await agent.run("Add 6 and 7 inside execute_code.")
    assert "13" in (response.text or "")
    assert client.call_count == 2
