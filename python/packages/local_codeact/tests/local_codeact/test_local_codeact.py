# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from agent_framework import Content, FunctionTool, Message, SessionContext

from agent_framework_local_codeact import (
    FileMount,
    LocalCodeActProvider,
    LocalExecuteCodeTool,
    ProcessExecutionLimits,
)
from agent_framework_local_codeact import _runner as runner_module
from agent_framework_local_codeact._files import normalize_mount_path

RUNNER_SCRIPT = Path(runner_module.__file__ or "").resolve()


def add_tool(a: int, b: int) -> int:
    return a + b


dangerous_tool = FunctionTool(
    name="dangerous_tool",
    description="Requires approval.",
    approval_mode="always_require",
    func=lambda: "ok",
)


def _content_texts(contents: list[Content]) -> list[str]:
    return [content.text or "" for content in contents if content.type == "text"]


def test_tool_construction_defaults() -> None:
    local_tool = LocalExecuteCodeTool()
    assert local_tool.name == "execute_code"
    assert local_tool.approval_mode == "never_require"
    assert local_tool.execution_mode == "subprocess"
    assert local_tool.python_executable == sys.executable
    assert local_tool.runner_script is None
    assert local_tool.get_tools() == []


def test_add_remove_clear_tools_round_trip() -> None:
    local_tool = LocalExecuteCodeTool()

    local_tool.add_tools([add_tool, dangerous_tool])
    assert [tool.name for tool in local_tool.get_tools()] == ["add_tool", "dangerous_tool"]
    assert local_tool.approval_mode == "always_require"

    local_tool.remove_tool("dangerous_tool")
    assert [tool.name for tool in local_tool.get_tools()] == ["add_tool"]
    assert local_tool.approval_mode == "never_require"

    with pytest.raises(KeyError):
        local_tool.remove_tool("missing")

    local_tool.clear_tools()
    assert local_tool.get_tools() == []


def test_default_approval_mode_always_require_is_sticky() -> None:
    local_tool = LocalExecuteCodeTool(tools=[add_tool], approval_mode="always_require")
    assert local_tool.approval_mode == "always_require"

    local_tool.clear_tools()
    assert local_tool.approval_mode == "always_require"


def test_file_mounts_normalized_and_round_tripped(tmp_path: Path) -> None:
    host_a = tmp_path / "a"
    host_a.mkdir()
    host_b = tmp_path / "b"
    host_b.mkdir()

    local_tool = LocalExecuteCodeTool(
        file_mounts=[
            str(host_a),
            (str(host_b), "/work"),
            FileMount(host_path=host_a, mount_path="/data", mode="read-write"),
        ],
    )

    mounts = local_tool.get_file_mounts()
    by_mount = {mount.mount_path: mount for mount in mounts}

    assert set(by_mount) == {normalize_mount_path(str(host_a)), "/work", "/data"}
    assert by_mount["/work"].host_path == host_b.resolve()
    assert by_mount["/data"].mode == "read-write"


def test_workspace_root_auto_mounts_at_input(tmp_path: Path) -> None:
    local_tool = LocalExecuteCodeTool(workspace_root=tmp_path)
    state = local_tool.build_serializable_state()
    assert any(mount["mount_path"] == "/input" and mount["mode"] == "read-write" for mount in state["file_mounts"])


def test_build_serializable_state_matches_effective_config(tmp_path: Path) -> None:
    local_tool = LocalExecuteCodeTool(
        tools=[add_tool, dangerous_tool],
        workspace_root=tmp_path,
        env={"VISIBLE": "yes"},
        execution_limits=ProcessExecutionLimits(timeout_seconds=3),
        python_executable=sys.executable,
    )
    state = local_tool.build_serializable_state()
    assert state["runtime"] == "local_codeact"
    assert state["execution_mode"] == "subprocess"
    assert state["python_executable"] == sys.executable
    assert state["runner_script"] is None
    assert state["approval_mode"] == "always_require"
    assert set(state["tool_names"]) == {"add_tool", "dangerous_tool"}
    assert state["workspace_root"] == str(tmp_path.resolve())
    assert state["execution_limits"]["timeout_seconds"] == 3
    assert state["env_keys"] == ["VISIBLE"]


async def test_provider_injects_execute_code_tool_and_instructions() -> None:
    provider = LocalCodeActProvider(tools=[add_tool])
    context = SessionContext(input_messages=[Message(role="user", contents=[Content.from_text("hi")])])
    state: dict[str, Any] = {}

    await provider.before_run(agent=MagicMock(), session=None, context=context, state=state)

    assert state["local_codeact"]["tool_names"] == ["add_tool"]
    assert any("add_tool" in instruction for instruction in context.instructions)
    assert len(context.tools) == 1
    assert isinstance(context.tools[0], LocalExecuteCodeTool)


async def test_subprocess_run_code_surfaces_stdout_and_output() -> None:
    local_tool = LocalExecuteCodeTool(execution_limits=ProcessExecutionLimits(timeout_seconds=5))
    result = await local_tool._run_code(code="print('hello')\n1 + 2")

    texts = _content_texts(result)
    assert any("hello" in text for text in texts)
    assert any(text.strip() == "3" for text in texts)


async def test_subprocess_run_code_invokes_registered_tool() -> None:
    local_tool = LocalExecuteCodeTool(tools=[add_tool], execution_limits=ProcessExecutionLimits(timeout_seconds=5))
    result = await local_tool._run_code(code="await add_tool(a=2, b=3)")

    assert any(text.strip() == "5" for text in _content_texts(result))


async def test_subprocess_call_tool_fallback_invokes_registered_tool() -> None:
    local_tool = LocalExecuteCodeTool(tools=[add_tool], execution_limits=ProcessExecutionLimits(timeout_seconds=5))
    result = await local_tool._run_code(code="await call_tool('add_tool', a=4, b=8)")

    assert any(text.strip() == "12" for text in _content_texts(result))


async def test_subprocess_fanout_tool_calls_are_serialized_over_bridge() -> None:
    local_tool = LocalExecuteCodeTool(tools=[add_tool], execution_limits=ProcessExecutionLimits(timeout_seconds=5))
    result = await local_tool._run_code(
        code="await asyncio.gather(add_tool(a=1, b=2), call_tool('add_tool', a=3, b=4))"
    )

    assert any(json.loads(text) == [3, 7] for text in _content_texts(result) if text.startswith("["))


async def test_subprocess_environment_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_CODEACT_SECRET", "hidden")
    local_tool = LocalExecuteCodeTool(
        env={"VISIBLE": "yes"}, execution_limits=ProcessExecutionLimits(timeout_seconds=5)
    )
    result = await local_tool._run_code(
        code="import os\n{'visible': os.environ.get('VISIBLE'), 'secret': os.environ.get('LOCAL_CODEACT_SECRET')}"
    )

    payloads = [json.loads(text) for text in _content_texts(result) if text.startswith("{")]
    assert payloads == [{"visible": "yes", "secret": None}]


async def test_subprocess_runner_script_executes_by_file_path() -> None:
    local_tool = LocalExecuteCodeTool(
        runner_script=RUNNER_SCRIPT,
        execution_limits=ProcessExecutionLimits(timeout_seconds=5),
    )
    result = await local_tool._run_code(code="'script runner'")

    assert local_tool.runner_script == RUNNER_SCRIPT
    assert any(text.strip() == '"script runner"' for text in _content_texts(result))


async def test_subprocess_timeout_returns_error_content() -> None:
    local_tool = LocalExecuteCodeTool(execution_limits=ProcessExecutionLimits(timeout_seconds=0.2))
    result = await local_tool._run_code(code="import time\ntime.sleep(5)")

    assert len(result) == 1
    assert result[0].type == "error"
    assert "exceeded" in (result[0].error_details or "")


async def test_file_capture_skips_symlinks_and_returns_written_files(tmp_path: Path) -> None:
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (mounted / "link.txt").symlink_to(outside)

    local_tool = LocalExecuteCodeTool(
        file_mounts=[FileMount(mounted, "/output", mode="read-write")],
        execution_limits=ProcessExecutionLimits(timeout_seconds=5),
    )
    result = await local_tool._run_code(
        code=f"from pathlib import Path\nPath({str(mounted)!r}, 'out.txt').write_text('hello', encoding='utf-8')"
    )

    data_contents = [content for content in result if content.type == "data"]
    assert len(data_contents) == 1
    assert data_contents[0].additional_properties["path"] == "/output/out.txt"
    assert data_contents[0].uri is not None
    encoded = data_contents[0].uri.split(",", 1)[1]
    assert base64.b64decode(encoded) == b"hello"


async def test_unsafe_in_process_mode_runs_code() -> None:
    local_tool = LocalExecuteCodeTool(execution_mode="unsafe_in_process")
    result = await local_tool._run_code(code="print('unsafe')\n'ran'")

    texts = _content_texts(result)
    assert any("unsafe" in text for text in texts)
    assert any(text.strip() == '"ran"' for text in texts)
