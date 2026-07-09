# Copyright (c) Microsoft. All rights reserved.

"""Hermetic unit tests for ``agent_framework_monty``.

These tests inject a fake Monty runtime via ``monkeypatch`` so they run without
the real ``pydantic-monty`` package doing any work. End-to-end tests against
the real runtime live in ``test_monty_codeact_integration.py``.
"""

from __future__ import annotations

import json
import sys
import types
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from agent_framework import Content, FunctionTool, Message, tool
from agent_framework._sessions import SessionContext

from agent_framework_monty import MontyCodeActProvider, MontyExecuteCodeTool
from agent_framework_monty import _execute_code_tool as execute_code_module
from agent_framework_monty import _monty_bridge as bridge_module

# ---------------------------------------------------------------------------
# Fake Monty runtime - drop-in replacement for pydantic_monty
# ---------------------------------------------------------------------------


@dataclass
class _FakeMontyComplete:
    output: Any = None


@dataclass
class _FakeFunctionSnapshot:
    function_name: str
    call_id: int
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    is_os_function: bool = False
    _script: _FakeScript | None = None

    def resume(self, payload: Any) -> Any:
        assert self._script is not None, "Snapshot must be attached to a script."
        return self._script.advance(("function_resume", self, payload))


@dataclass
class _FakeFutureSnapshot:
    pending_call_ids: list[int]
    _script: _FakeScript | None = None

    def resume(self, payload: Any) -> Any:
        assert self._script is not None, "Snapshot must be attached to a script."
        return self._script.advance(("future_resume", self, payload))


@dataclass
class _FakeNameLookupSnapshot:
    variable_name: str


@dataclass
class _PrintAction:
    """Marker pushed onto a script to emit captured stdout via the print callback."""

    text: str


class _FakeScript:
    """Replayable Monty progress script with a resume log."""

    def __init__(self, items: Iterable[Any]) -> None:
        self._queue: list[Any] = list(items)
        self.resume_log: list[tuple[str, Any, Any]] = []

    def attach(self, snapshot: Any) -> Any:
        snapshot._script = self
        return snapshot

    def next_item(self) -> Any:
        if not self._queue:
            return _FakeMontyComplete(output=None)
        item = self._queue.pop(0)
        if isinstance(item, _FakeMontyComplete):
            return item
        if isinstance(item, _PrintAction):
            return item
        if isinstance(item, _FakeNameLookupSnapshot):
            return item
        return self.attach(item)

    def advance(self, log_entry: tuple[str, Any, Any]) -> Any:
        self.resume_log.append(log_entry)
        return self.next_item()


_current_script: list[_FakeScript | None] = [None]


def _set_script(*items: Any) -> _FakeScript:
    script = _FakeScript(items)
    _current_script[0] = script
    return script


def _get_script() -> _FakeScript:
    script = _current_script[0]
    assert script is not None, "Test must call _set_script(...) before running code."
    return script


class _FakeMonty:
    def __init__(
        self,
        code: str,
        *,
        script_name: str,
        type_check: bool,
        type_check_stubs: str | None,
    ) -> None:
        self.code = code
        self.script_name = script_name
        self.type_check = type_check
        self.type_check_stubs = type_check_stubs
        self._script = _get_script()

    def start(self, *, print_callback: Any) -> Any:
        while True:
            item = self._script.next_item()
            if isinstance(item, _PrintAction):
                print_callback("stdout", item.text)
                continue
            return item


@pytest.fixture(autouse=True)
def fake_monty_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Install a fake ``pydantic_monty`` module for the duration of each test."""
    fake = types.ModuleType("pydantic_monty")
    fake.Monty = _FakeMonty  # type: ignore[attr-defined] # ty: ignore[unresolved-attribute]
    fake.MontyComplete = _FakeMontyComplete  # type: ignore[attr-defined] # ty: ignore[unresolved-attribute]
    fake.FunctionSnapshot = _FakeFunctionSnapshot  # type: ignore[attr-defined] # ty: ignore[unresolved-attribute]
    fake.FutureSnapshot = _FakeFutureSnapshot  # type: ignore[attr-defined] # ty: ignore[unresolved-attribute]
    fake.NameLookupSnapshot = _FakeNameLookupSnapshot  # type: ignore[attr-defined] # ty: ignore[unresolved-attribute]

    monkeypatch.setitem(sys.modules, "pydantic_monty", fake)
    _current_script[0] = None
    yield
    _current_script[0] = None


# ---------------------------------------------------------------------------
# Sample tools used across tests
# ---------------------------------------------------------------------------


@tool
def add_tool(
    a: Annotated[int, "First addend"],
    b: Annotated[int, "Second addend"],
) -> int:
    """Add two integers."""
    return a + b


@tool
def mul_tool(
    a: Annotated[int, "First factor"],
    b: Annotated[int, "Second factor"],
) -> int:
    """Multiply two integers."""
    return a * b


@tool(approval_mode="always_require")
def dangerous_tool(payload: Annotated[str, "Anything"]) -> str:
    """A tool that always requires approval."""
    return payload


# ---------------------------------------------------------------------------
# MontyExecuteCodeTool tests
# ---------------------------------------------------------------------------


def test_tool_construction_defaults() -> None:
    monty_tool = MontyExecuteCodeTool()
    assert monty_tool.name == "execute_code"
    assert monty_tool.approval_mode == "never_require"
    assert monty_tool.get_tools() == []


def test_add_remove_clear_tools_round_trip() -> None:
    monty_tool = MontyExecuteCodeTool()

    monty_tool.add_tools([add_tool, mul_tool])
    assert [t.name for t in monty_tool.get_tools()] == ["add_tool", "mul_tool"]

    monty_tool.remove_tool("add_tool")
    assert [t.name for t in monty_tool.get_tools()] == ["mul_tool"]

    with pytest.raises(KeyError):
        monty_tool.remove_tool("missing")

    monty_tool.clear_tools()
    assert monty_tool.get_tools() == []


def test_approval_required_tool_gates_execute_code() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    assert monty_tool.approval_mode == "never_require"

    monty_tool.add_tools([dangerous_tool])
    assert monty_tool.approval_mode == "always_require"

    monty_tool.remove_tool("dangerous_tool")
    assert monty_tool.approval_mode == "never_require"


def test_default_approval_mode_always_require_is_sticky() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add_tool], approval_mode="always_require")
    assert monty_tool.approval_mode == "always_require"

    monty_tool.clear_tools()
    assert monty_tool.approval_mode == "always_require"


def test_dynamic_description_reflects_registered_tools() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    description = monty_tool.description
    assert "add_tool" in description
    assert "Monty" in description

    monty_tool.add_tools([mul_tool])
    description_updated = monty_tool.description
    assert "mul_tool" in description_updated


def test_create_run_tool_snapshots_current_state() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add_tool], approval_mode="never_require")
    run_tool = monty_tool.create_run_tool()

    assert run_tool is not monty_tool
    assert [t.name for t in run_tool.get_tools()] == ["add_tool"]
    assert run_tool.approval_mode == monty_tool.approval_mode

    # Mutating the original must not leak into the snapshot.
    monty_tool.add_tools([mul_tool])
    assert [t.name for t in run_tool.get_tools()] == ["add_tool"]


def test_build_serializable_state_matches_effective_config() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add_tool, dangerous_tool])
    state = monty_tool.build_serializable_state()
    assert state["runtime"] == "monty"
    assert state["approval_mode"] == "always_require"
    assert set(state["tool_names"]) == {"add_tool", "dangerous_tool"}
    assert state["workspace_root"] is None
    assert state["file_mounts"] == []
    assert state["resource_limits"] is None


def test_file_mounts_normalized_and_round_tripped(tmp_path: Path) -> None:
    from agent_framework_monty import FileMount
    from agent_framework_monty._execute_code_tool import _normalize_mount_path

    host_a = tmp_path / "a"
    host_a.mkdir()
    host_b = tmp_path / "b"
    host_b.mkdir()

    monty_tool = MontyExecuteCodeTool(
        file_mounts=[
            str(host_a),  # shorthand: same path on both sides
            (str(host_b), "/work"),  # explicit tuple
            FileMount(host_path=host_a, mount_path="/data", mode="read-only"),
        ],
    )

    mounts = monty_tool.get_file_mounts()
    by_mount = {m.mount_path: m for m in mounts}

    # The shorthand string is normalized through _normalize_mount_path (POSIX-style),
    # so on Windows `C:\\...` becomes `/C:/...`. Compare against the same normalizer.
    shorthand_key = _normalize_mount_path(str(host_a))
    assert set(by_mount) == {shorthand_key, "/work", "/data"}
    assert by_mount["/work"].host_path == host_b.resolve()
    assert by_mount["/data"].mode == "read-only"
    assert by_mount[shorthand_key].mode == "overlay"  # default


def test_workspace_root_auto_mounts_at_input(tmp_path: Path) -> None:
    monty_tool = MontyExecuteCodeTool(workspace_root=tmp_path)
    mounts = monty_tool._effective_mounts()
    assert any(m.mount_path == "/input" and m.mode == "read-write" for m in mounts)


def test_workspace_root_yields_to_explicit_input_mount(tmp_path: Path) -> None:
    from agent_framework_monty import FileMount

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    monty_tool = MontyExecuteCodeTool(
        workspace_root=tmp_path,
        file_mounts=[FileMount(host_path=explicit, mount_path="/input", mode="read-only")],
    )
    input_mounts = [m for m in monty_tool._effective_mounts() if m.mount_path == "/input"]
    assert len(input_mounts) == 1
    assert input_mounts[0].mode == "read-only"
    assert input_mounts[0].host_path == explicit.resolve()


def test_remove_file_mount_raises_on_missing() -> None:
    monty_tool = MontyExecuteCodeTool()
    with pytest.raises(KeyError):
        monty_tool.remove_file_mount("/never-added")


def test_dynamic_description_mentions_filesystem_when_mounts_configured(tmp_path: Path) -> None:
    monty_tool = MontyExecuteCodeTool(workspace_root=tmp_path)
    description = monty_tool.description
    assert "Filesystem access is enabled" in description
    assert "/input" in description


def test_dynamic_description_default_mentions_no_filesystem() -> None:
    monty_tool = MontyExecuteCodeTool()
    description = monty_tool.description
    assert "Filesystem access is unavailable" in description


def test_resource_limits_round_trip() -> None:
    monty_tool = MontyExecuteCodeTool(resource_limits={"max_duration_secs": 5.0})
    assert monty_tool.resource_limits == {"max_duration_secs": 5.0}
    state = monty_tool.build_serializable_state()
    assert state["resource_limits"] == {"max_duration_secs": 5.0}


def test_build_instructions_includes_registered_tools() -> None:
    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    instructions = monty_tool.build_instructions(tools_visible_to_model=False)
    assert "add_tool" in instructions
    assert "execute_code" in instructions
    assert "asyncio.gather" in instructions


def test_execute_code_filtered_out_when_added_as_tool() -> None:
    spurious = FunctionTool(
        name="execute_code",
        description="should not appear",
        func=lambda: None,
    )
    monty_tool = MontyExecuteCodeTool(tools=[spurious, add_tool])
    assert [t.name for t in monty_tool.get_tools()] == ["add_tool"]


# ---------------------------------------------------------------------------
# _run_code behavior with the fake Monty runtime
# ---------------------------------------------------------------------------


async def test_run_code_with_no_tools_returns_default_text() -> None:
    _set_script(_FakeMontyComplete(output=None))

    monty_tool = MontyExecuteCodeTool()
    result = await monty_tool._run_code(code="None")

    assert len(result) == 1
    assert isinstance(result[0], Content)


async def test_run_code_surfaces_stdout_and_output() -> None:
    _set_script(_PrintAction("hello\n"), _FakeMontyComplete(output=42))

    monty_tool = MontyExecuteCodeTool()
    result = await monty_tool._run_code(code="print('hello')")

    text_contents = [c for c in result if c.type == "text"]
    assert any("hello" in (c.text or "") for c in text_contents)
    assert any(
        (c.text or "").strip() and json.loads(c.text or "null") == 42
        for c in text_contents
        if (c.text or "").strip().isdigit()
    )


async def test_run_code_direct_typed_call_invokes_registered_tool() -> None:
    func_snapshot = _FakeFunctionSnapshot(
        function_name="add_tool",
        call_id=1,
        kwargs={"a": 2, "b": 3},
    )
    future_snapshot = _FakeFutureSnapshot(pending_call_ids=[1])
    script = _set_script(func_snapshot, future_snapshot, _FakeMontyComplete(output=None))

    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    await monty_tool._run_code(code="await add_tool(a=2, b=3)")

    payloads = [payload for _, _, payload in script.resume_log]
    assert {"future": ...} in payloads
    final_resume = next(p for p in payloads if isinstance(p, dict) and 1 in p)
    assert final_resume[1] == {"return_value": 5}


async def test_run_code_call_tool_fallback_invokes_registered_tool() -> None:
    func_snapshot = _FakeFunctionSnapshot(
        function_name="call_tool",
        call_id=7,
        args=("add_tool",),
        kwargs={"a": 4, "b": 8},
    )
    future_snapshot = _FakeFutureSnapshot(pending_call_ids=[7])
    script = _set_script(func_snapshot, future_snapshot, _FakeMontyComplete(output=None))

    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    await monty_tool._run_code(code="await call_tool('add_tool', a=4, b=8)")

    payloads = [payload for _, _, payload in script.resume_log]
    final_resume = next(p for p in payloads if isinstance(p, dict) and 7 in p)
    assert final_resume[7] == {"return_value": 12}


async def test_run_code_unknown_tool_returns_nameerror_resume() -> None:
    func_snapshot = _FakeFunctionSnapshot(
        function_name="does_not_exist",
        call_id=11,
    )
    script = _set_script(func_snapshot, _FakeMontyComplete(output=None))

    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    await monty_tool._run_code(code="await does_not_exist()")

    payloads = [payload for _, _, payload in script.resume_log]
    assert any(isinstance(p, dict) and p.get("exc_type") == "NameError" for p in payloads)


async def test_run_code_os_function_is_rejected_with_permissionerror() -> None:
    os_snapshot = _FakeFunctionSnapshot(
        function_name="os.listdir",
        call_id=12,
        is_os_function=True,
    )
    script = _set_script(os_snapshot, _FakeMontyComplete(output=None))

    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    await monty_tool._run_code(code="import os; os.listdir('.')")

    payloads = [payload for _, _, payload in script.resume_log]
    assert any(isinstance(p, dict) and p.get("exc_type") == "PermissionError" for p in payloads)


async def test_when_any_returns_nameerror_now_that_it_is_removed() -> None:
    """`when_any` is no longer part of the DSL and should resolve to a NameError."""
    func_snapshot = _FakeFunctionSnapshot(
        function_name="when_any",
        call_id=99,
        args=([{"tool": "add_tool", "kwargs": {"a": 1, "b": 2}}],),
    )
    script = _set_script(func_snapshot, _FakeMontyComplete(output=None))

    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    await monty_tool._run_code(code="await when_any([{'tool': 'add_tool', 'kwargs': {'a': 1, 'b': 2}}])")

    payloads = [payload for _, _, payload in script.resume_log]
    assert any(isinstance(p, dict) and p.get("exc_type") == "NameError" for p in payloads)


async def test_run_code_call_tool_with_unregistered_name_returns_error() -> None:
    func_snapshot = _FakeFunctionSnapshot(
        function_name="call_tool",
        call_id=20,
        args=("missing",),
        kwargs={},
    )
    script = _set_script(func_snapshot, _FakeMontyComplete(output=None))

    monty_tool = MontyExecuteCodeTool(tools=[add_tool])
    await monty_tool._run_code(code="await call_tool('missing')")

    payloads = [payload for _, _, payload in script.resume_log]
    assert any(
        isinstance(p, dict) and p.get("exc_type") == "ValueError" and "Tool 'missing'" in p.get("message", "")
        for p in payloads
    )


async def test_run_code_returns_error_content_on_runtime_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomBridge:
        def __init__(self, tool_map: Any, **_: Any) -> None:
            pass

        async def run(self, code: str) -> dict[str, Any]:
            raise RuntimeError("boom")

    monkeypatch.setattr(execute_code_module, "InlineCodeBridge", _BoomBridge)

    monty_tool = MontyExecuteCodeTool()
    result = await monty_tool._run_code(code="x = 1")
    assert len(result) == 1
    assert result[0].type == "error"
    assert "boom" in (result[0].error_details or "")


# ---------------------------------------------------------------------------
# MontyCodeActProvider tests
# ---------------------------------------------------------------------------


async def test_provider_injects_execute_code_tool_and_instructions() -> None:
    provider = MontyCodeActProvider(tools=[add_tool])
    context = SessionContext(input_messages=[Message(role="user", contents=[Content.from_text("hi")])])
    state: dict[str, Any] = {}

    await provider.before_run(agent=MagicMock(), session=None, context=context, state=state)

    assert state["monty_codeact"]["tool_names"] == ["add_tool"]
    assert any("add_tool" in instruction for instruction in context.instructions)
    assert len(context.tools) == 1
    assert isinstance(context.tools[0], MontyExecuteCodeTool)
    # The injected tool is a per-run snapshot, not the provider's stored copy.
    assert context.tools[0] is not provider._execute_code_tool  # type: ignore[attr-defined]


def test_provider_delegates_tool_management_to_internal_tool() -> None:
    provider = MontyCodeActProvider()
    provider.add_tools([add_tool, mul_tool])
    assert [t.name for t in provider.get_tools()] == ["add_tool", "mul_tool"]

    provider.remove_tool("add_tool")
    assert [t.name for t in provider.get_tools()] == ["mul_tool"]

    provider.clear_tools()
    assert provider.get_tools() == []


# ---------------------------------------------------------------------------
# generate_type_stubs - signature smoke test
# ---------------------------------------------------------------------------


def test_generate_type_stubs_emits_dsl_and_tool_signatures() -> None:
    def custom(x: int, y: str = "z") -> bool:
        """Stub-test tool."""
        return True

    stubs = bridge_module.generate_type_stubs({"custom": custom})

    assert "async def call_tool(name: str, **kwargs: Any) -> Any:" in stubs
    assert "async def custom(x: int, y: str = ...) -> bool:" in stubs
    assert "when_any" not in stubs


def test_generate_type_stubs_preserves_none_and_optional() -> None:

    def nullable_return(x: int) -> None:
        """Returns nothing."""
        return

    def optional_param(x: int | None = None) -> bool:  # noqa: UP045 - intentional
        """Optional via typing.Optional."""
        return x is None

    def union_param(x: int | str | None) -> str:  # noqa: UP007 - intentional
        """Union with None."""
        return str(x)

    stubs = bridge_module.generate_type_stubs({
        "nullable_return": nullable_return,
        "optional_param": optional_param,
        "union_param": union_param,
    })

    # ``None`` return must round-trip as None, not Any.
    assert "async def nullable_return(x: int) -> None:" in stubs
    # ``Optional[X]`` is ``Union[X, None]`` at runtime; preserve None.
    assert "async def optional_param(x: int | None = ...) -> bool:" in stubs
    # Multi-arm union with None.
    assert "async def union_param(x: int | str | None) -> str:" in stubs


def test_generate_type_stubs_skips_non_identifier_tool_names() -> None:
    """Tool names that are not valid Python identifiers must not be splatted into stub source.

    The model can still reach them via ``call_tool("weird-name", ...)`` at
    runtime; they just don't get type-checked stubs.
    """

    def evil(x: int) -> int:
        return x

    def normal(x: int) -> int:
        return x

    stubs = bridge_module.generate_type_stubs({
        # Hyphens are not valid identifier chars.
        "weird-name": evil,
        # Newlines in the name would inject arbitrary stub source.
        "broken\n    pass\nasync def injected": evil,
        # Python keywords are valid identifiers per ``str.isidentifier()`` but
        # would still produce uncompilable stubs.
        "async": evil,
        # Real tool that should still appear.
        "normal": normal,
    })

    assert "async def normal(x: int) -> int:" in stubs
    assert "weird-name" not in stubs
    assert "injected" not in stubs
    assert "async def async(" not in stubs


async def test_invoke_tool_awaits_partial_wrapped_async_method() -> None:
    """A FunctionTool callback registered via partial(FunctionTool.invoke, ...) must be awaited.

    Regression for PR #5915 review feedback: relying on ``inspect.iscoroutinefunction``
    to choose between ``await`` and ``asyncio.to_thread`` is fragile for
    ``functools.partial`` wrappers (cpython#98590) and would surface the
    returned coroutine as a JSON-serialization error instead of the real
    tool result. The bridge must always ``await`` entries in ``self.tool_map``.
    """
    from functools import partial

    from agent_framework_monty._monty_bridge import InlineCodeBridge

    @tool
    def adder(a: Annotated[int, ""], b: Annotated[int, ""]) -> int:
        """Add."""
        return a + b

    # Mirrors what _make_tool_callback returns.
    cb = partial(adder.invoke, skip_parsing=True)
    bridge = InlineCodeBridge({"adder": cb})

    cid, payload = await bridge._invoke_tool(7, "adder", {"a": 6, "b": 7})
    assert cid == 7
    assert payload == {"return_value": 13}, payload
