# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib.util
import os
import sys
from types import SimpleNamespace
from typing import Any, cast

import pytest

if sys.platform == "win32":  # pragma: no cover - platform-dependent
    # The integration test relies on POSIX-style commands inside the sandbox. Skip the
    # whole module on Windows to match the sibling ``agent-framework-hyperlight`` tests.
    pytest.skip("Tenki tests use POSIX-style shell invocations.", allow_module_level=True)

# The executor module raises ``RuntimeError`` at import time when ``tenki_sandbox`` is
# missing. In that case there's nothing meaningful to test here — skip the whole module.
try:
    from agent_framework_tenki import TenkiCodeActProvider, TenkiExecuteCodeTool
    from agent_framework_tenki import _execute_code_tool as _tenki_module
except RuntimeError as _import_err:  # pragma: no cover - environment-dependent
    pytest.skip(
        f"tenki-sandbox SDK is not importable ({_import_err}); skipping Tenki tests.",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Fake Tenki SDK — deterministic, in-memory replacement for ``tenki_sandbox.Sandbox``.
# ---------------------------------------------------------------------------


class _FakeExecResult(SimpleNamespace):
    def __init__(self, *, stdout_text: str = "", stderr_text: str = "", exit_code: int = 0) -> None:
        super().__init__(stdout_text=stdout_text, stderr_text=stderr_text, exit_code=exit_code)


class _FakeSandbox:
    def __init__(self, *, name: str) -> None:
        self.name = name
        self.closed: bool = False
        self.exec_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.script_result: _FakeExecResult = _FakeExecResult(stdout_text="ok\n")
        self.script_handler: Any = None
        # Lifecycle state — mirrors the real SDK's ``sandbox.state`` string values.
        self.state: str = "RUNNING"
        self.refresh_calls: int = 0
        self.resume_calls: int = 0
        # When set, ``refresh()`` transitions ``state`` to this value on the next call.
        self.refresh_transitions_to: str | None = None
        # When set, ``refresh()`` raises this exception on the next call.
        self.refresh_raises: BaseException | None = None
        # When set, ``resume()`` raises this exception on the next call.
        self.resume_raises: BaseException | None = None

    def exec(self, *args: Any, **kwargs: Any) -> _FakeExecResult:
        self.exec_calls.append((args, kwargs))
        if self.script_handler is not None:
            return self.script_handler(args, kwargs)  # type: ignore[no-any-return]
        return self.script_result

    def refresh(self) -> None:
        self.refresh_calls += 1
        if self.refresh_raises is not None:
            exc, self.refresh_raises = self.refresh_raises, None
            raise exc
        if self.refresh_transitions_to is not None:
            self.state = self.refresh_transitions_to
            self.refresh_transitions_to = None

    def resume(self) -> None:
        self.resume_calls += 1
        if self.resume_raises is not None:
            exc, self.resume_raises = self.resume_raises, None
            raise exc
        self.state = "RUNNING"

    def close_if_open(self) -> None:
        self.closed = True


class _FakeSandboxFactory:
    """Stand-in for :class:`tenki_sandbox.Sandbox`. Records ``create`` calls."""

    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.sandboxes: list[_FakeSandbox] = []
        self.raise_on_create: BaseException | None = None

    @property
    def last_sandbox(self) -> _FakeSandbox | None:
        return self.sandboxes[-1] if self.sandboxes else None

    def create(self, **kwargs: Any) -> _FakeSandbox:
        if self.raise_on_create is not None:
            raise self.raise_on_create
        self.create_calls.append(kwargs)
        sandbox = _FakeSandbox(name=kwargs.get("name", "sb-fake"))
        self.sandboxes.append(sandbox)
        return sandbox


@pytest.fixture
def fake_sdk(monkeypatch: pytest.MonkeyPatch) -> _FakeSandboxFactory:
    """Replace the Tenki ``Sandbox`` class in the executor module with an in-memory fake."""
    factory = _FakeSandboxFactory()
    monkeypatch.setattr(_tenki_module, "Sandbox", factory)
    return factory


# ---------------------------------------------------------------------------
# Unit tests — no network / no real Tenki service.
# ---------------------------------------------------------------------------


def test_default_sandbox_name_carries_agent_framework_prefix() -> None:
    tool = TenkiExecuteCodeTool()
    assert tool.sandbox_name.startswith("agent-framework-")
    # 8-char hex suffix, per _default_sandbox_name.
    suffix = tool.sandbox_name.rsplit("-", 1)[-1]
    assert len(suffix) == 8
    int(suffix, 16)  # raises if the suffix is not hex.


def test_explicit_sandbox_name_is_preserved() -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="my-name")
    assert tool.sandbox_name == "my-name"


def test_exec_timeout_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="exec_timeout_seconds"):
        TenkiExecuteCodeTool(exec_timeout_seconds=0)


async def test_run_code_lazily_creates_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="lazy")
    # No sandbox yet just from construction.
    assert fake_sdk.create_calls == []

    await tool._run_code(code="print('hello')")
    assert len(fake_sdk.create_calls) == 1
    assert fake_sdk.create_calls[0]["name"] == "lazy"


async def test_run_code_reuses_the_same_sandbox_across_calls(fake_sdk: _FakeSandboxFactory) -> None:
    """Reuse-per-session: subsequent calls do NOT create a new sandbox."""
    tool = TenkiExecuteCodeTool(sandbox_name="reuse")
    await tool._run_code(code="x = 1")
    await tool._run_code(code="print(x)")
    await tool._run_code(code="print(x + 1)")
    assert len(fake_sdk.create_calls) == 1
    # All exec calls landed on the single created sandbox.
    assert fake_sdk.last_sandbox is not None
    assert len(fake_sdk.last_sandbox.exec_calls) == 3


async def test_close_terminates_sandbox_and_next_call_creates_new_one(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="cycle")
    await tool._run_code(code="print('a')")
    first_sandbox = fake_sdk.last_sandbox
    assert first_sandbox is not None
    await tool.close()
    assert first_sandbox.closed is True

    await tool._run_code(code="print('b')")
    assert len(fake_sdk.create_calls) == 2
    assert fake_sdk.last_sandbox is not first_sandbox


async def test_paused_sandbox_is_auto_resumed_between_calls(fake_sdk: _FakeSandboxFactory) -> None:
    """A sandbox paused between calls must be transparently resumed before the next exec."""
    tool = TenkiExecuteCodeTool(sandbox_name="paused")
    await tool._run_code(code="print('a')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    # Simulate a server-side pause discovered on the next ``refresh()``.
    sandbox.refresh_transitions_to = "PAUSED"

    await tool._run_code(code="print('b')")

    # Same sandbox reused (no re-provision).
    assert len(fake_sdk.create_calls) == 1
    assert fake_sdk.last_sandbox is sandbox
    # refresh + resume were called, and state landed back on RUNNING.
    assert sandbox.refresh_calls == 1
    assert sandbox.resume_calls == 1
    assert sandbox.state == "RUNNING"
    # The second exec landed on the same sandbox.
    assert len(sandbox.exec_calls) == 2


async def test_terminated_sandbox_is_replaced_by_fresh_provision(fake_sdk: _FakeSandboxFactory) -> None:
    """A sandbox that terminated between calls must be dropped and replaced."""
    tool = TenkiExecuteCodeTool(sandbox_name="gone")
    await tool._run_code(code="print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None

    first.refresh_transitions_to = "TERMINATED"

    await tool._run_code(code="print('b')")

    # A brand new sandbox was provisioned; the terminated one was not resumed.
    assert len(fake_sdk.create_calls) == 2
    assert fake_sdk.last_sandbox is not first
    assert first.resume_calls == 0
    assert fake_sdk.last_sandbox is not None
    assert len(fake_sdk.last_sandbox.exec_calls) == 1


async def test_resume_failure_surfaces_as_error_content(fake_sdk: _FakeSandboxFactory) -> None:
    """If ``resume()`` raises, the failure surfaces to the caller as error content.

    The stale handle is deliberately kept so that a subsequent call (once the underlying
    condition clears, e.g. quota released) can retry ``resume()`` on the same sandbox
    without losing filesystem state to an unnecessary re-provision.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="resume-fail")
    await tool._run_code(code="print('a')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    sandbox.refresh_transitions_to = "PAUSED"
    sandbox.resume_raises = RuntimeError("quota_exceeded: resume denied")

    contents = await tool._run_code(code="print('b')")

    # RuntimeError from _ensure_sandbox_sync is caught in _run_code and returned as
    # error content — the caller sees a structured failure, not an unhandled exception.
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "Failed to provision Tenki sandbox" in (contents[0].message or "")
    assert "quota_exceeded" in (contents[0].error_details or "")

    # Resume was attempted exactly once; no re-provision happened.
    assert sandbox.resume_calls == 1
    assert len(fake_sdk.create_calls) == 1


async def test_refresh_failure_falls_back_to_fresh_provision(fake_sdk: _FakeSandboxFactory) -> None:
    """If ``refresh()`` raises, the stale handle is dropped and a fresh sandbox is provisioned."""
    tool = TenkiExecuteCodeTool(sandbox_name="stale")
    await tool._run_code(code="print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None

    first.refresh_raises = RuntimeError("connection reset")

    await tool._run_code(code="print('b')")

    assert len(fake_sdk.create_calls) == 2
    assert fake_sdk.last_sandbox is not first
    # We did not attempt to resume a sandbox whose state we couldn't confirm.
    assert first.resume_calls == 0


async def test_close_is_idempotent(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="idempotent")
    await tool.close()  # no sandbox yet — no-op.
    await tool._run_code(code="print('x')")
    await tool.close()
    await tool.close()  # second close — no-op.
    assert fake_sdk.last_sandbox is not None
    assert fake_sdk.last_sandbox.closed is True


async def test_async_context_manager_closes_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    async with TenkiExecuteCodeTool(sandbox_name="cm") as tool:
        await tool._run_code(code="print('inside')")
    assert fake_sdk.last_sandbox is not None
    assert fake_sdk.last_sandbox.closed is True


async def test_create_kwargs_only_forward_set_optionals(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(
        sandbox_name="kwargs",
        api_key="tk_TEST",
        image="my-image",
        project_id="proj-1",
        workspace_id="ws-1",
        cpu_cores=4,
        memory_mb=2048,
        disk_size_gb=10,
        max_duration_seconds=300,
        extra_create_kwargs={"allow_inbound": True},
    )
    await tool._run_code(code="pass")

    call = fake_sdk.create_calls[0]
    assert call["name"] == "kwargs"
    assert call["auth_token"] == "tk_TEST"
    assert call["image"] == "my-image"
    assert call["project_id"] == "proj-1"
    assert call["workspace_id"] == "ws-1"
    assert call["cpu_cores"] == 4
    assert call["memory_mb"] == 2048
    assert call["disk_size_gb"] == 10
    assert call["max_duration"] == 300
    assert call["allow_inbound"] is True


async def test_create_kwargs_omit_unset_optionals(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every Tenki env var the tool consults must be scrubbed so this test doesn't
    # inherit a real developer/CI value and start asserting against it.
    monkeypatch.delenv("TENKI_API_KEY", raising=False)
    monkeypatch.delenv("TENKI_PROJECT_ID", raising=False)
    monkeypatch.delenv("TENKI_WORKSPACE_ID", raising=False)
    tool = TenkiExecuteCodeTool(sandbox_name="bare")
    await tool._run_code(code="pass")

    call = fake_sdk.create_calls[0]
    for absent in (
        "auth_token",
        "image",
        "project_id",
        "workspace_id",
        "cpu_cores",
        "memory_mb",
        "disk_size_gb",
        "max_duration",
    ):
        assert absent not in call, f"expected {absent!r} to be omitted from create kwargs"


async def test_env_api_key_is_forwarded_as_auth_token(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TENKI_API_KEY", "tk_FROM_ENV")
    tool = TenkiExecuteCodeTool(sandbox_name="env-key")
    await tool._run_code(code="pass")
    assert fake_sdk.create_calls[0]["auth_token"] == "tk_FROM_ENV"


async def test_env_project_id_is_forwarded_when_unset(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TENKI_PROJECT_ID env var populates project_id when the constructor arg is None."""
    monkeypatch.setenv("TENKI_PROJECT_ID", "proj-from-env")
    tool = TenkiExecuteCodeTool(sandbox_name="env-proj")
    await tool._run_code(code="pass")
    assert fake_sdk.create_calls[0]["project_id"] == "proj-from-env"


async def test_env_workspace_id_is_forwarded_when_unset(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TENKI_WORKSPACE_ID env var populates workspace_id when the constructor arg is None."""
    monkeypatch.setenv("TENKI_WORKSPACE_ID", "ws-from-env")
    tool = TenkiExecuteCodeTool(sandbox_name="env-ws")
    await tool._run_code(code="pass")
    assert fake_sdk.create_calls[0]["workspace_id"] == "ws-from-env"


async def test_constructor_project_id_wins_over_env(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit constructor project_id takes precedence over TENKI_PROJECT_ID env."""
    monkeypatch.setenv("TENKI_PROJECT_ID", "proj-from-env")
    monkeypatch.setenv("TENKI_WORKSPACE_ID", "ws-from-env")
    tool = TenkiExecuteCodeTool(
        sandbox_name="explicit-wins",
        project_id="proj-explicit",
        workspace_id="ws-explicit",
    )
    await tool._run_code(code="pass")
    call = fake_sdk.create_calls[0]
    assert call["project_id"] == "proj-explicit"
    assert call["workspace_id"] == "ws-explicit"


async def test_create_failure_returns_error_content(fake_sdk: _FakeSandboxFactory) -> None:
    fake_sdk.raise_on_create = RuntimeError("resource_exhausted: no live node-agent")
    tool = TenkiExecuteCodeTool(sandbox_name="fails")
    contents = await tool._run_code(code="print('never runs')")
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "Failed to provision Tenki sandbox" in (contents[0].message or "")
    assert "resource_exhausted" in (contents[0].error_details or "")


async def test_run_code_uses_python3_dash_c_with_timeout(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="argshape", exec_timeout_seconds=45)
    await tool._run_code(code="print(1 + 1)")

    assert fake_sdk.last_sandbox is not None
    args, kwargs = fake_sdk.last_sandbox.exec_calls[0]
    assert args == ("python3", "-c", "print(1 + 1)")
    assert kwargs == {"timeout": 45}


async def test_stdout_only_produces_single_text_content(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="stdout")
    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="hello\n", exit_code=0)
    contents = await tool._run_code(code="print('hello')")
    assert len(contents) == 1
    assert contents[0].type == "text"
    assert contents[0].text == "hello\n"


async def test_non_zero_exit_produces_error_content_with_stderr(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="failing")
    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="", stderr_text="Traceback...\n", exit_code=1)
    contents = await tool._run_code(code="raise ValueError('boom')")
    error_contents = [c for c in contents if c.type == "error"]
    assert len(error_contents) == 1
    message = error_contents[0].message or ""
    assert "status 1" in message
    # stderr must be inlined into the message so LLMs that under-weight
    # `error_details` still see the traceback in the primary field.
    assert "Traceback" in message
    assert "Traceback" in (error_contents[0].error_details or "")


async def test_syntaxerror_appends_recovery_hint(fake_sdk: _FakeSandboxFactory) -> None:
    """SyntaxError stderr must trigger the recovery hint in the message field."""
    tool = TenkiExecuteCodeTool(sandbox_name="syntax")
    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(
        stdout_text="",
        stderr_text=(
            'File "<string>", line 1\n'
            "    import os; with open('/tmp/x') as f: pass\n"
            "               ^^^^\n"
            "SyntaxError: invalid syntax"
        ),
        exit_code=1,
    )
    contents = await tool._run_code(code="import os; with open('/tmp/x') as f: pass")
    error_content = next(c for c in contents if c.type == "error")
    message = error_content.message or ""
    # Hint should mention both known failure modes.
    assert "Common causes" in message
    assert "compound statement" in message
    assert "\\n" in message  # literal-newline pitfall reference


async def test_non_syntax_error_does_not_append_hint(fake_sdk: _FakeSandboxFactory) -> None:
    """Non-SyntaxError stderr must NOT trigger the recovery hint (no misleading advice)."""
    tool = TenkiExecuteCodeTool(sandbox_name="runtime")
    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(
        stdout_text="",
        stderr_text=(
            'Traceback (most recent call last):\n  File "<string>", line 1, in <module>\nValueError: bad value'
        ),
        exit_code=1,
    )
    contents = await tool._run_code(code="raise ValueError('bad value')")
    error_content = next(c for c in contents if c.type == "error")
    message = error_content.message or ""
    assert "ValueError" in message
    assert "Common causes" not in message


async def test_error_message_truncates_long_stderr(fake_sdk: _FakeSandboxFactory) -> None:
    """Very long stderr must be truncated in the message so it doesn't blow the field."""
    tool = TenkiExecuteCodeTool(sandbox_name="failing-long")
    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    long_stderr = "err " * 500  # 2000 chars total
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="", stderr_text=long_stderr, exit_code=1)
    contents = await tool._run_code(code="raise Exception('x')")
    error_contents = [c for c in contents if c.type == "error"]
    assert len(error_contents) == 1
    message = error_contents[0].message or ""
    # message field capped: status prefix + up to 500 chars of stderr + minor formatting.
    # Verify total is well below the full stderr length so the LLM's context isn't flooded.
    assert len(message) < 700
    # Full stderr still available via error_details for callers that want it.
    assert len(error_contents[0].error_details or "") == len(long_stderr)


async def test_stderr_without_error_becomes_text_content(fake_sdk: _FakeSandboxFactory) -> None:
    """Warnings to stderr should still surface to the model, matching Hyperlight."""
    tool = TenkiExecuteCodeTool(sandbox_name="warn")
    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(
        stdout_text="", stderr_text="DeprecationWarning: foo\n", exit_code=0
    )
    contents = await tool._run_code(code="import warnings; warnings.warn('foo')")
    assert any(c.type == "text" and "DeprecationWarning" in (c.text or "") for c in contents)
    assert not any(c.type == "error" for c in contents)


async def test_empty_output_produces_placeholder_text(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="silent")
    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="", stderr_text="", exit_code=0)
    contents = await tool._run_code(code="x = 1")
    assert len(contents) == 1
    assert contents[0].type == "text"
    assert "without output" in (contents[0].text or "")


async def test_exec_exception_returns_error_content(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="exec-err")

    def handler(_args: tuple[Any, ...], _kwargs: dict[str, Any]) -> _FakeExecResult:
        raise RuntimeError("SDK exec transport error")

    await tool._run_code(code="init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_handler = handler

    contents = await tool._run_code(code="print('x')")
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "Sandbox execution failed" in (contents[0].message or "")


async def test_tool_name_and_description() -> None:
    tool = TenkiExecuteCodeTool()
    assert tool.name == "execute_code"
    assert "Tenki" in tool.description


async def test_provider_close_terminates_underlying_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    provider = TenkiCodeActProvider(sandbox_name="prov")
    await provider.execute_code_tool._run_code(code="print('x')")
    assert fake_sdk.last_sandbox is not None
    await provider.close()
    assert fake_sdk.last_sandbox.closed is True


async def test_provider_async_context_manager_closes_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    async with TenkiCodeActProvider(sandbox_name="prov-cm") as provider:
        await provider.execute_code_tool._run_code(code="print('x')")
        assert fake_sdk.last_sandbox is not None
        assert fake_sdk.last_sandbox.closed is False
    assert fake_sdk.last_sandbox is not None
    assert fake_sdk.last_sandbox.closed is True


async def test_provider_exposes_execute_code_tool_before_run(fake_sdk: _FakeSandboxFactory) -> None:
    provider = TenkiCodeActProvider(sandbox_name="ctx")
    recorded: dict[str, Any] = {"tools_calls": [], "instructions_calls": []}

    class _StubContext:
        def extend_tools(self, source_id: str, tools: list[Any]) -> None:
            recorded["tools_calls"].append((source_id, tools))

        def extend_instructions(self, source_id: str, instructions: str) -> None:
            recorded["instructions_calls"].append((source_id, instructions))

    # ``_StubContext`` is structurally compatible with ``SessionContext`` (implements
    # extend_tools + extend_instructions) but isn't a nominal subclass. Cast to Any
    # so strict type checkers accept the deliberate stub injection.
    await provider.before_run(agent=None, session=None, context=cast(Any, _StubContext()), state={})

    assert len(recorded["tools_calls"]) == 1
    tools_source_id, tools = recorded["tools_calls"][0]
    assert tools_source_id == TenkiCodeActProvider.DEFAULT_SOURCE_ID
    assert tools == [provider.execute_code_tool]

    assert len(recorded["instructions_calls"]) == 1
    instr_source_id, instructions = recorded["instructions_calls"][0]
    assert instr_source_id == TenkiCodeActProvider.DEFAULT_SOURCE_ID
    # The instructions must reinforce the print() requirement, the persistence
    # rules, the "no Jupyter magic" rule, and the "newlines for compound
    # statements" rule so that small models tool-call correctly against a
    # fresh interpreter.
    assert "print(" in instructions
    assert "python3 -c" in instructions
    assert "filesystem persists" in instructions
    assert "subprocess" in instructions
    # Match on '!command' to catch the specific Jupyter-magic footgun we hit
    # in the field (small models emitted `!{sys.executable} -m pip install ...`).
    assert "!command" in instructions
    # Match on 'compound statements' to catch the semicolon-in-compound-stmt
    # footgun (small models emitted `import os; with open(...) as f: ...`).
    assert "compound statements" in instructions
    # A concrete valid single-line `with` example nudges small models toward
    # the shape that actually worked in the field.
    assert "with open('/tmp/x.txt') as f: print(f.read())" in instructions


# ---------------------------------------------------------------------------
# Integration test — real Tenki service. Requires TENKI_API_KEY. Marked as
# integration so ``pytest -m "not integration"`` (the default suite) skips it.
# ---------------------------------------------------------------------------


def _tenki_integration_skip_reason() -> str | None:
    if os.environ.get("SKIP_TENKI", "").lower() == "true":
        return "SKIP_TENKI=true is set."
    if importlib.util.find_spec("tenki_sandbox") is None:
        return "tenki-sandbox is not installed."
    if not os.environ.get("TENKI_API_KEY"):
        return "TENKI_API_KEY is not set."
    return None


skip_if_tenki_integration_disabled = pytest.mark.skipif(
    _tenki_integration_skip_reason() is not None,
    reason=_tenki_integration_skip_reason() or "unknown",
)


@pytest.mark.integration
@skip_if_tenki_integration_disabled
async def test_integration_execute_hello_world() -> None:
    project_id = os.environ.get("TENKI_PROJECT_ID")
    async with TenkiExecuteCodeTool(
        sandbox_name=f"agent-framework-ci-{os.getpid()}",
        project_id=project_id,
        max_duration_seconds=300,
    ) as tool:
        contents = await tool._run_code(code="print('hello from tenki')")
    text_contents = [c for c in contents if c.type == "text"]
    assert any("hello from tenki" in (c.text or "") for c in text_contents)
