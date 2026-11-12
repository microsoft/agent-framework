# Copyright (c) Microsoft. All rights reserved.

"""Local runtime regressions that do not require external services."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import pytest
from agent_framework import FunctionTool
from pydantic_monty import MontyRuntimeError, MountDir

from agent_framework_monty import MontyExecuteCodeTool
from agent_framework_monty import _monty_bridge as bridge_module
from agent_framework_monty._execute_code_tool import _make_tool_callback
from agent_framework_monty._monty_bridge import InlineCodeBridge

_RUNAWAY_GUEST = "while True:\n    pass"
_READ_MOUNT_FILE = "from pathlib import Path\nPath('/input/value.txt').read_text()\n"
_READ_MOUNT_FILE_IGNORING_ERRORS = (
    "from pathlib import Path\ntry:\n    Path('/input/value.txt').read_text()\nexcept Exception:\n    pass\n"
)
_WRITE_FILE_THEN_PAUSE = "from pathlib import Path\nPath('/input/{name}.txt').write_text('{name}')\nawait pause()\n"


@pytest.mark.parametrize(
    "resource_limits",
    [
        {"max_duration_secs": 5.0, "max_memory": 64 * 1024 * 1024},
        {"max_feed_duration_secs": 5.0},
        {"max_turn_duration_secs": 5.0},
        {"max_duration_secs": 5.0, "max_turn_duration_secs": 1.0},
        {"max_duration_secs": None},
    ],
)
async def test_duration_limits_allow_execution_without_mutating_configuration(resource_limits: dict[str, Any]) -> None:
    original_limits = dict(resource_limits)
    execute_code = MontyExecuteCodeTool(resource_limits=resource_limits)

    contents = await execute_code._run_code(code="print('completed')")

    assert not any(content.type == "error" for content in contents)
    assert any(content.type == "text" and "completed" in (content.text or "") for content in contents)
    assert resource_limits == original_limits
    assert execute_code.resource_limits == original_limits
    assert execute_code.build_serializable_state()["resource_limits"] == original_limits


@pytest.mark.parametrize(
    ("duration_key", "limit_scope"),
    [
        ("max_duration_secs", "feed"),
        ("max_feed_duration_secs", "feed"),
        ("max_turn_duration_secs", "turn"),
    ],
)
async def test_duration_limits_stop_execution_with_a_timeout(duration_key: str, limit_scope: str) -> None:
    bridge = InlineCodeBridge({}, resource_limits={duration_key: 0.001})

    with pytest.raises(MontyRuntimeError, match=f"TimeoutError: {limit_scope} time limit exceeded"):
        await bridge.run("while True:\n    pass")


@pytest.mark.parametrize("legacy_duration", [None, 5.0])
async def test_legacy_and_feed_duration_limits_are_rejected_as_ambiguous(legacy_duration: float | None) -> None:
    bridge = InlineCodeBridge(
        {},
        resource_limits={"max_duration_secs": legacy_duration, "max_feed_duration_secs": 1.0},
    )

    with pytest.raises(ValueError, match="Specify only one of max_duration_secs and max_feed_duration_secs"):
        await bridge.run("print('must not run')")


async def test_default_feed_duration_limit_stops_runaway_guest_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_module, "DEFAULT_MAX_FEED_DURATION_SECS", 0.3)

    with pytest.raises(MontyRuntimeError, match="feed time limit exceeded"):
        await InlineCodeBridge({}).run(_RUNAWAY_GUEST)


@pytest.mark.parametrize(
    ("code", "use_mount"),
    [
        (_RUNAWAY_GUEST, False),
        (f"await record()\n{_RUNAWAY_GUEST}", False),
        (f"{_READ_MOUNT_FILE_IGNORING_ERRORS}{_RUNAWAY_GUEST}", False),
        (f"{_READ_MOUNT_FILE}{_RUNAWAY_GUEST}", True),
    ],
    ids=["feed", "resume_after_host_tool", "resume_after_os_error", "resume_after_mount_read"],
)
async def test_runaway_guest_code_does_not_block_the_event_loop(code: str, use_mount: bool, tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("value", encoding="utf-8")
    mounts = [MountDir(host_path=str(tmp_path), virtual_path="/input", mode="read-only")] if use_mount else None
    loop = asyncio.get_running_loop()
    timestamps = [loop.time()]

    async def record() -> None:
        # Measure only the time after the guest resumes from this host call.
        timestamps[:] = [loop.time()]

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(0.01)
            timestamps.append(loop.time())

    bridge = InlineCodeBridge({"record": record}, mounts=mounts, resource_limits={"max_feed_duration_secs": 1.0})
    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        with pytest.raises(MontyRuntimeError, match="feed time limit exceeded"):
            await bridge.run(code)
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
    timestamps.append(loop.time())

    # A blocked loop leaves a gap about as long as the 1 s guest budget.
    assert max(later - earlier for earlier, later in zip(timestamps, timestamps[1:])) < 0.5


async def test_timeout_around_running_guest_code_returns_promptly_and_later_runs_recover() -> None:
    guest_started = asyncio.Event()

    async def record() -> None:
        guest_started.set()

    bridge = InlineCodeBridge({"record": record}, resource_limits={"max_feed_duration_secs": 2.0})
    run = asyncio.create_task(bridge.run(f"await record()\n{_RUNAWAY_GUEST}"))
    await asyncio.wait_for(guest_started.wait(), timeout=30)
    started = asyncio.get_running_loop().time()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(run, timeout=0.3)

    assert run.cancelled()
    assert asyncio.get_running_loop().time() - started < 1.5
    assert (await InlineCodeBridge({}).run("1 + 1"))["output"] == 2


async def test_concurrent_runs_sharing_a_writable_mount_capture_only_their_own_files(tmp_path: Path) -> None:
    async def pause() -> None:
        await asyncio.sleep(0.05)

    execute_code = MontyExecuteCodeTool(tools=[FunctionTool(name="pause", func=pause)], workspace_root=tmp_path)

    first, second = await asyncio.gather(
        execute_code._run_code(code=_WRITE_FILE_THEN_PAUSE.format(name="first")),
        execute_code._run_code(code=_WRITE_FILE_THEN_PAUSE.format(name="second")),
    )

    assert [(c.additional_properties or {}).get("path") for c in first if c.type == "data"] == ["/input/first.txt"]
    assert [(c.additional_properties or {}).get("path") for c in second if c.type == "data"] == ["/input/second.txt"]


async def test_concurrent_runs_without_a_writable_mount_overlap() -> None:
    arrivals = 0
    both_arrived = asyncio.Event()

    async def rendezvous() -> None:
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            both_arrived.set()
        # Serialized runs would never meet here, so this wait would time out.
        await asyncio.wait_for(both_arrived.wait(), timeout=10)

    execute_code = MontyExecuteCodeTool(tools=[FunctionTool(name="rendezvous", func=rendezvous)])

    results = await asyncio.gather(
        execute_code._run_code(code="await rendezvous()"),
        execute_code._run_code(code="await rendezvous()"),
    )

    assert not any(content.type == "error" for contents in results for content in contents)


async def test_tool_state_leaves_out_the_writable_mount_lock_and_restores_usable(tmp_path: Path) -> None:
    execute_code = MontyExecuteCodeTool(workspace_root=tmp_path)
    await asyncio.gather(execute_code._run_code(code="1"), execute_code._run_code(code="2"))

    # Use the pickle state hooks directly: copying or pickling the whole tool also depends on global telemetry state.
    state = execute_code.__getstate__()
    restored = MontyExecuteCodeTool.__new__(MontyExecuteCodeTool)
    restored.__setstate__(state)

    assert "_writable_mount_lock" not in state
    assert not any(c.type == "error" for c in await restored._run_code(code="print('ok')"))


@pytest.mark.parametrize("recording_host_tool", ["positional_or_keyword", "keyword_only"], indirect=True)
async def test_positional_tool_call_is_rejected_before_any_host_tool_runs(
    recording_host_tool: tuple[FunctionTool, list[str | None]],
) -> None:
    host_tool, calls = recording_host_tool
    execute_code = MontyExecuteCodeTool(tools=[host_tool], include_detailed_errors=True)

    contents = await execute_code._run_code(code='await record(label="first")\nawait record("second")')

    assert [content.type for content in contents] == ["error"]
    assert "positional" in (contents[0].error_details or "").lower()
    # Type checking fails before execution, so even the valid first call never reaches the host.
    assert calls == []


@pytest.mark.parametrize("recording_host_tool", ["positional_or_keyword", "keyword_only"], indirect=True)
async def test_positional_tool_call_is_rejected_when_type_checking_is_bypassed(
    recording_host_tool: tuple[FunctionTool, list[str | None]],
) -> None:
    host_tool, calls = recording_host_tool
    bridge = InlineCodeBridge({"record": _make_tool_callback(host_tool)})

    with pytest.raises(MontyRuntimeError, match="record accepts keyword arguments only"):
        await bridge.run('await record("second")')

    assert calls == []


@pytest.mark.parametrize("recording_host_tool", ["positional_or_keyword", "keyword_only"], indirect=True)
async def test_keyword_tool_call_runs_and_omitted_parameters_use_defaults(
    recording_host_tool: tuple[FunctionTool, list[str | None]],
) -> None:
    host_tool, calls = recording_host_tool
    execute_code = MontyExecuteCodeTool(tools=[host_tool])

    contents = await execute_code._run_code(code='await record(label="named")\nawait record()')

    assert not any(content.type == "error" for content in contents)
    assert calls == ["named", None]


@pytest.mark.parametrize(
    ("unsupplied_parameter_host_tool", "expected_call"),
    [
        ("context", "x:FunctionInvocationContext"),
        ("var_keyword", "x"),
        ("var_positional", "x"),
        ("method", "x"),
    ],
    indirect=["unsupplied_parameter_host_tool"],
)
async def test_typed_call_does_not_require_parameters_that_guest_code_cannot_supply(
    unsupplied_parameter_host_tool: tuple[FunctionTool, list[str]],
    expected_call: str,
) -> None:
    host_tool, calls = unsupplied_parameter_host_tool
    execute_code = MontyExecuteCodeTool(tools=[host_tool], include_detailed_errors=True)

    contents = await execute_code._run_code(code='await lookup(query="x")')

    assert not any(content.type == "error" for content in contents)
    assert calls == [expected_call]


@pytest.mark.parametrize("unsupplied_parameter_host_tool", ["var_keyword"], indirect=True)
async def test_typed_call_with_undeclared_keyword_is_rejected_before_any_host_tool_runs(
    unsupplied_parameter_host_tool: tuple[FunctionTool, list[str]],
) -> None:
    host_tool, calls = unsupplied_parameter_host_tool
    execute_code = MontyExecuteCodeTool(tools=[host_tool], include_detailed_errors=True)

    contents = await execute_code._run_code(code='await lookup(query="x", extra=1)')

    assert [content.type for content in contents] == ["error"]
    assert "unknown-argument" in (contents[0].error_details or "")
    assert calls == []
