# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, cast

import pytest

# ``tenki-sandbox`` is a hard dep of this package, so in practice it's always present.
# Skip the module if it happens to be missing (e.g. dev checkout without a full install)
# instead of erroring pytest collection.
try:
    from agent_framework_tenki import TenkiCodeActProvider, TenkiExecuteCodeTool
    from agent_framework_tenki import _execute_code_tool as _tenki_module
except ImportError as _import_err:  # pragma: no cover - environment-dependent
    pytest.skip(
        f"tenki-sandbox SDK is not importable ({_import_err}); skipping Tenki tests.",
        allow_module_level=True,
    )


# ---------------------------------------------------------------------------
# Fake Tenki SDK — deterministic, in-memory replacement for ``tenki_sandbox.Sandbox``.
# ---------------------------------------------------------------------------


class _FakeExecResult(SimpleNamespace):
    """Mirror ``tenki_sandbox.models.CommandResult`` — including the ``ok`` property."""

    def __init__(
        self,
        *,
        stdout_text: str = "",
        stderr_text: str = "",
        exit_code: int = 0,
        signal: str | None = None,
        reason: str | None = None,
        errno: int | None = None,
    ) -> None:
        super().__init__(
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            exit_code=exit_code,
            signal=signal,
            reason=reason,
            errno=errno,
        )

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.signal


class _FakeClient:
    def __init__(self) -> None:
        self.closed: bool = False

    def close(self) -> None:
        self.closed = True


class _FakeSandbox:
    def __init__(self, *, name: str) -> None:
        self.id: str = f"sandbox-{name}"
        self.name: str = name
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
        # When set, ``refresh()`` walks through the sequence one value per call.
        # Terminal value stays after the sequence is exhausted.
        self.refresh_state_sequence: list[str] | None = None
        # When set, ``refresh()`` / ``close_if_open()`` raise this once.
        self.refresh_raises: BaseException | None = None
        self.close_raises: BaseException | None = None
        # ``resume()`` failure knobs: ``resume_raises`` raises on EVERY call
        # (persistent failure), ``resume_raises_once`` raises once then clears
        # (transient failure — e.g. USER_SHUTDOWN's snapshot not yet linked).
        self.resume_raises: BaseException | None = None
        self.resume_raises_once: BaseException | None = None
        # ``resume()`` in the real SDK returns while state may still be ``RESUMING``.
        # Fake matches: by default resume leaves state at ``RUNNING`` (tests can override).
        self.resume_leaves_state_as: str = "RUNNING"
        # SDK-owned client fields that ``Sandbox.create`` sets when it builds a Client.
        self._owns_client: bool = True
        self._client: _FakeClient = _FakeClient()

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
        if self.refresh_state_sequence:
            self.state = self.refresh_state_sequence.pop(0)
        elif self.refresh_transitions_to is not None:
            self.state = self.refresh_transitions_to
            self.refresh_transitions_to = None

    def resume(self) -> None:
        self.resume_calls += 1
        if self.resume_raises_once is not None:
            exc, self.resume_raises_once = self.resume_raises_once, None
            raise exc
        if self.resume_raises is not None:
            raise self.resume_raises
        self.state = self.resume_leaves_state_as

    def close_if_open(self) -> None:
        if self.close_raises is not None:
            exc, self.close_raises = self.close_raises, None
            raise exc
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
    """Replace the Tenki ``Sandbox`` class with an in-memory fake + tight polls."""
    factory = _FakeSandboxFactory()
    monkeypatch.setattr(_tenki_module, "Sandbox", factory)
    # Shrink poll interval + timeout so tests exercising state polls stay fast.
    monkeypatch.setattr(_tenki_module, "_RESUME_POLL_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(_tenki_module, "_RESUME_POLL_TIMEOUT_SECONDS", 0.5)
    return factory


async def _invoke(tool: TenkiExecuteCodeTool, code: str) -> list[Any]:
    """Invoke the tool through the public :meth:`FunctionTool.invoke` API."""
    return await tool.invoke(arguments={"code": code})


# ---------------------------------------------------------------------------
# Construction + naming
# ---------------------------------------------------------------------------


def test_default_sandbox_name_carries_agent_framework_prefix() -> None:
    tool = TenkiExecuteCodeTool()
    assert tool.sandbox_name.startswith("agent-framework-")
    suffix = tool.sandbox_name.rsplit("-", 1)[-1]
    assert len(suffix) == 8
    int(suffix, 16)  # raises if the suffix is not hex


def test_explicit_sandbox_name_is_preserved() -> None:
    """Standalone use with an explicit name preserves the literal (no suffix)."""
    tool = TenkiExecuteCodeTool(sandbox_name="my-name")
    assert tool.sandbox_name == "my-name"


def test_exec_timeout_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="exec_timeout_seconds"):
        TenkiExecuteCodeTool(exec_timeout_seconds=0)


# ---------------------------------------------------------------------------
# Sandbox creation + kwargs forwarding
# ---------------------------------------------------------------------------


async def test_run_code_lazily_creates_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="lazy")
    assert fake_sdk.create_calls == []
    await _invoke(tool, "print('hello')")
    assert len(fake_sdk.create_calls) == 1
    assert fake_sdk.create_calls[0]["name"] == "lazy"


async def test_run_code_reuses_the_same_sandbox_across_calls(fake_sdk: _FakeSandboxFactory) -> None:
    """Reuse-per-tool: subsequent calls on the same tool do NOT create a new sandbox."""
    tool = TenkiExecuteCodeTool(sandbox_name="reuse")
    await _invoke(tool, "x = 1")
    await _invoke(tool, "print(x)")
    await _invoke(tool, "print(x + 1)")
    assert len(fake_sdk.create_calls) == 1
    assert fake_sdk.last_sandbox is not None
    assert len(fake_sdk.last_sandbox.exec_calls) == 3


async def test_default_max_duration_is_finite(fake_sdk: _FakeSandboxFactory) -> None:
    """Even without ``max_duration_seconds`` the tool applies a finite server-side backstop."""
    tool = TenkiExecuteCodeTool(sandbox_name="default-cap")
    await _invoke(tool, "pass")
    call = fake_sdk.create_calls[0]
    assert call["max_duration"] == _tenki_module._DEFAULT_MAX_DURATION_SECONDS
    assert call["max_duration"] > 0


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
    await _invoke(tool, "pass")

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
    await _invoke(tool, "pass")

    call = fake_sdk.create_calls[0]
    # ``max_duration`` is now unconditionally set (finite default) — so it is NOT in
    # the omitted list. The other optionals should still be absent when unset.
    for absent in (
        "auth_token",
        "image",
        "project_id",
        "workspace_id",
        "cpu_cores",
        "memory_mb",
        "disk_size_gb",
    ):
        assert absent not in call, f"expected {absent!r} to be omitted from create kwargs"


async def test_max_duration_opt_out(fake_sdk: _FakeSandboxFactory) -> None:
    """Passing ``max_duration_seconds=None`` explicitly opts out of the finite cap."""
    tool = TenkiExecuteCodeTool(sandbox_name="no-cap", max_duration_seconds=None)
    await _invoke(tool, "pass")
    assert "max_duration" not in fake_sdk.create_calls[0]


async def test_pause_retention_omitted_by_default_standalone(fake_sdk: _FakeSandboxFactory) -> None:
    """A standalone tool leaves pause retention to the Tenki server default (7 days).

    A user who deliberately pauses a long-lived standalone sandbox must not have
    its snapshot GC'd early by a default they never asked for.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="retention-default")
    await _invoke(tool, "pass")
    assert "pause_retention" not in fake_sdk.create_calls[0]


async def test_pause_retention_forwarded_when_set(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="retention-explicit", pause_retention_seconds=120)
    await _invoke(tool, "pass")
    assert fake_sdk.create_calls[0]["pause_retention"] == 120


async def test_run_tool_defaults_to_short_pause_retention(fake_sdk: _FakeSandboxFactory) -> None:
    """Run-scoped sandboxes get a short pause retention by default.

    A run-scoped sandbox that outlives its run is an orphan of a failed cleanup
    (crash / cancellation / abandoned stream) — nothing will resume it, so its
    pause snapshot should be GC'd after an hour, not the server's 7-day default.
    """
    run_tool = TenkiExecuteCodeTool(sandbox_name="prefix").create_run_tool()
    await _invoke(run_tool, "pass")
    expected = _tenki_module._DEFAULT_RUN_SCOPED_PAUSE_RETENTION_SECONDS
    assert fake_sdk.create_calls[0]["pause_retention"] == expected


async def test_run_tool_preserves_explicit_pause_retention(fake_sdk: _FakeSandboxFactory) -> None:
    run_tool = TenkiExecuteCodeTool(sandbox_name="prefix", pause_retention_seconds=7200).create_run_tool()
    await _invoke(run_tool, "pass")
    assert fake_sdk.create_calls[0]["pause_retention"] == 7200


async def test_env_api_key_is_forwarded_as_auth_token(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TENKI_API_KEY", "tk_FROM_ENV")
    tool = TenkiExecuteCodeTool(sandbox_name="env-key")
    await _invoke(tool, "pass")
    assert fake_sdk.create_calls[0]["auth_token"] == "tk_FROM_ENV"


async def test_env_project_id_is_forwarded_when_unset(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TENKI_PROJECT_ID", "proj-from-env")
    tool = TenkiExecuteCodeTool(sandbox_name="env-proj")
    await _invoke(tool, "pass")
    assert fake_sdk.create_calls[0]["project_id"] == "proj-from-env"


async def test_env_workspace_id_is_forwarded_when_unset(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TENKI_WORKSPACE_ID", "ws-from-env")
    tool = TenkiExecuteCodeTool(sandbox_name="env-ws")
    await _invoke(tool, "pass")
    assert fake_sdk.create_calls[0]["workspace_id"] == "ws-from-env"


async def test_empty_string_env_vars_are_treated_as_unset(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI systems expand unconfigured secrets/vars to "" — never forward those."""
    monkeypatch.setenv("TENKI_API_KEY", "")
    monkeypatch.setenv("TENKI_PROJECT_ID", "")
    monkeypatch.setenv("TENKI_WORKSPACE_ID", "")
    tool = TenkiExecuteCodeTool(sandbox_name="empty-env")
    await _invoke(tool, "pass")
    call = fake_sdk.create_calls[0]
    assert "auth_token" not in call
    assert "project_id" not in call
    assert "workspace_id" not in call


async def test_constructor_project_id_wins_over_env(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TENKI_PROJECT_ID", "proj-from-env")
    monkeypatch.setenv("TENKI_WORKSPACE_ID", "ws-from-env")
    tool = TenkiExecuteCodeTool(
        sandbox_name="explicit-wins",
        project_id="proj-explicit",
        workspace_id="ws-explicit",
    )
    await _invoke(tool, "pass")
    call = fake_sdk.create_calls[0]
    assert call["project_id"] == "proj-explicit"
    assert call["workspace_id"] == "ws-explicit"


async def test_create_failure_returns_error_content(fake_sdk: _FakeSandboxFactory) -> None:
    fake_sdk.raise_on_create = RuntimeError("resource_exhausted: no live node-agent")
    tool = TenkiExecuteCodeTool(sandbox_name="fails")
    contents = await _invoke(tool, "print('never runs')")
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "Failed to prepare Tenki sandbox" in (contents[0].message or "")
    assert "resource_exhausted" in (contents[0].error_details or "")


async def test_run_code_uses_python3_dash_c_with_timeout(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="argshape", exec_timeout_seconds=45)
    await _invoke(tool, "print(1 + 1)")
    assert fake_sdk.last_sandbox is not None
    args, kwargs = fake_sdk.last_sandbox.exec_calls[0]
    assert args == ("python3", "-c", "print(1 + 1)")
    assert kwargs == {"timeout": 45}


# ---------------------------------------------------------------------------
# Result parsing — ok/signal/reason/errno
# ---------------------------------------------------------------------------


async def test_stdout_only_produces_single_text_content(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="stdout")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="hello\n", exit_code=0)
    contents = await _invoke(tool, "print('hello')")
    assert len(contents) == 1
    assert contents[0].type == "text"
    assert contents[0].text == "hello\n"


async def test_non_zero_exit_produces_error_content_with_stderr(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="failing")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="", stderr_text="Traceback...\n", exit_code=1)
    contents = await _invoke(tool, "raise ValueError('boom')")
    error_contents = [c for c in contents if c.type == "error"]
    assert len(error_contents) == 1
    message = error_contents[0].message or ""
    assert "status 1" in message
    assert "Traceback" in message
    assert "Traceback" in (error_contents[0].error_details or "")


async def test_signal_termination_reports_failure_via_ok_property(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """SIGKILL / SIGTERM etc. leave ``exit_code=0`` but ``ok=False``.

    We must trust ``ok`` (or the derived ``exit_code == 0 and not signal`` check),
    not ``exit_code`` alone — otherwise ``Killed`` reads as success.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="sig")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(
        stdout_text="", stderr_text="Killed\n", exit_code=0, signal="SIGKILL", reason="oom"
    )
    contents = await _invoke(tool, "hog memory")
    error_contents = [c for c in contents if c.type == "error"]
    assert len(error_contents) == 1
    message = error_contents[0].message or ""
    assert "signal SIGKILL" in message
    assert "reason oom" in message


async def test_errno_surfaces_in_failure_message(fake_sdk: _FakeSandboxFactory) -> None:
    """Spawn failures carry ``errno`` — must be visible in the error message."""
    tool = TenkiExecuteCodeTool(sandbox_name="spawn-fail")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(
        stdout_text="", stderr_text="", exit_code=127, errno=2, reason="spawn_failed"
    )
    contents = await _invoke(tool, "nope")
    error_contents = [c for c in contents if c.type == "error"]
    message = error_contents[0].message or ""
    assert "errno 2" in message
    assert "reason spawn_failed" in message


async def test_syntaxerror_appends_recovery_hint(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="syntax")
    await _invoke(tool, "init")
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
    contents = await _invoke(tool, "import os; with open('/tmp/x') as f: pass")
    error_content = next(c for c in contents if c.type == "error")
    message = error_content.message or ""
    assert "Common causes" in message
    assert "compound statement" in message
    assert "\\n" in message


async def test_non_syntax_error_does_not_append_hint(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="runtime")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(
        stdout_text="",
        stderr_text=(
            'Traceback (most recent call last):\n  File "<string>", line 1, in <module>\nValueError: bad value'
        ),
        exit_code=1,
    )
    contents = await _invoke(tool, "raise ValueError('bad value')")
    error_content = next(c for c in contents if c.type == "error")
    message = error_content.message or ""
    assert "ValueError" in message
    assert "Common causes" not in message


async def test_error_message_truncates_long_stderr(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="failing-long")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    long_stderr = "err " * 500
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="", stderr_text=long_stderr, exit_code=1)
    contents = await _invoke(tool, "raise Exception('x')")
    error_contents = [c for c in contents if c.type == "error"]
    assert len(error_contents) == 1
    message = error_contents[0].message or ""
    assert len(message) < 700
    assert len(error_contents[0].error_details or "") == len(long_stderr)


async def test_stderr_without_error_becomes_text_content(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="warn")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(
        stdout_text="", stderr_text="DeprecationWarning: foo\n", exit_code=0
    )
    contents = await _invoke(tool, "import warnings; warnings.warn('foo')")
    assert any(c.type == "text" and "DeprecationWarning" in (c.text or "") for c in contents)
    assert not any(c.type == "error" for c in contents)


async def test_empty_output_produces_placeholder_text(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="silent")
    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_result = _FakeExecResult(stdout_text="", stderr_text="", exit_code=0)
    contents = await _invoke(tool, "x = 1")
    assert len(contents) == 1
    assert contents[0].type == "text"
    assert "without output" in (contents[0].text or "")


async def test_exec_exception_returns_error_content(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="exec-err")

    def handler(_args: tuple[Any, ...], _kwargs: dict[str, Any]) -> _FakeExecResult:
        raise RuntimeError("SDK exec transport error")

    await _invoke(tool, "init")
    assert fake_sdk.last_sandbox is not None
    fake_sdk.last_sandbox.script_handler = handler

    contents = await _invoke(tool, "print('x')")
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "Sandbox execution failed" in (contents[0].message or "")


# ---------------------------------------------------------------------------
# Cancellation propagation — real ``asyncio.Task.cancel()`` mid-execution
# ---------------------------------------------------------------------------


async def test_task_cancel_during_exec_propagates(fake_sdk: _FakeSandboxFactory) -> None:
    """Cancelling the outer task while ``sandbox.exec`` is running propagates ``CancelledError``.

    Not a mocked raise inside the worker — a real ``asyncio.Task.cancel()`` from the
    outer coroutine while the ``to_thread(exec)`` call is still running. Verifies
    that our ``except asyncio.CancelledError: raise`` propagates the cancel through
    to the caller, which is what higher-level workflows depend on to stop promptly,
    AND that the tool remains cleanly closable afterwards (no leaked sandbox).
    """
    import threading

    tool = TenkiExecuteCodeTool(sandbox_name="cancel")
    await _invoke(tool, "init")  # provision sandbox up-front
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    loop = asyncio.get_running_loop()
    exec_started = asyncio.Event()
    # ``threading.Event`` — set by the outer coroutine to release the worker.
    # Cross-thread signalling with no private-API reach into ``asyncio.Event._loop``.
    exec_release = threading.Event()

    def slow_exec(_args: tuple[Any, ...], _kwargs: dict[str, Any]) -> _FakeExecResult:
        loop.call_soon_threadsafe(exec_started.set)
        exec_release.wait(timeout=2.0)
        return _FakeExecResult(stdout_text="never returned\n")

    sandbox.script_handler = slow_exec

    task = asyncio.create_task(_invoke(tool, "print('never')"))
    await exec_started.wait()
    task.cancel()
    exec_release.set()  # let the worker complete so its thread can join

    with pytest.raises(asyncio.CancelledError):
        await task

    # Teardown/leak assertion: after cancellation the tool must still close
    # cleanly — a cancelled run must not orphan the underlying sandbox.
    await tool.close()
    assert sandbox.closed is True
    assert sandbox._client.closed is True
    assert tool._sandbox is None


# ---------------------------------------------------------------------------
# Reconcile lifecycle — refresh / pause+resume / terminate / poll
# ---------------------------------------------------------------------------


async def test_paused_sandbox_is_auto_resumed_between_calls(fake_sdk: _FakeSandboxFactory) -> None:
    """A sandbox paused between calls must be transparently resumed before the next exec."""
    tool = TenkiExecuteCodeTool(sandbox_name="paused")
    await _invoke(tool, "print('a')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    sandbox.refresh_transitions_to = "PAUSED"
    await _invoke(tool, "print('b')")

    assert len(fake_sdk.create_calls) == 1
    assert fake_sdk.last_sandbox is sandbox
    assert sandbox.refresh_calls >= 1
    assert sandbox.resume_calls == 1
    assert sandbox.state == "RUNNING"
    assert len(sandbox.exec_calls) == 2


async def test_resume_polls_until_running_when_state_lags(fake_sdk: _FakeSandboxFactory) -> None:
    """``resume()`` can return while the SDK reports ``RESUMING`` — poll until ``RUNNING``.

    Uses a state sequence: refresh #1 reveals ``PAUSED``, then after resume the fake
    reports ``RESUMING`` for a couple of polls before flipping to ``RUNNING``.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="resume-lag")
    await _invoke(tool, "init")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    # Refresh sequence drives the reconcile: PAUSED (triggers resume), then RUNNING
    # (poll loop sees running). ``resume()`` itself leaves state at ``RESUMING``.
    sandbox.refresh_state_sequence = ["PAUSED", "RUNNING"]
    sandbox.resume_leaves_state_as = "RESUMING"

    await _invoke(tool, "print('after-resume')")
    assert sandbox.resume_calls == 1
    assert sandbox.state == "RUNNING"


async def test_resume_timeout_raises_runtime_error(fake_sdk: _FakeSandboxFactory) -> None:
    """If the sandbox never reaches RUNNING within the poll budget, surface a clear error."""
    tool = TenkiExecuteCodeTool(sandbox_name="resume-timeout")
    await _invoke(tool, "init")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    # Refresh #1 exposes PAUSED, then every subsequent refresh keeps reporting RESUMING.
    sandbox.refresh_state_sequence = ["PAUSED"] + ["RESUMING"] * 200
    sandbox.resume_leaves_state_as = "RESUMING"

    contents = await _invoke(tool, "print('x')")
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "did not reach RUNNING" in (contents[0].error_details or "")


async def test_transitional_state_polls_to_running(fake_sdk: _FakeSandboxFactory) -> None:
    """Transitional states (CREATING / RESUMING) resolve via the poll loop, no resume() call."""
    tool = TenkiExecuteCodeTool(sandbox_name="transitional")
    await _invoke(tool, "init")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    # Refresh sequence: CREATING (initial reconcile) → RESUMING (first poll) → RUNNING.
    sandbox.refresh_state_sequence = ["CREATING", "RESUMING", "RUNNING"]

    await _invoke(tool, "print('done')")
    assert sandbox.resume_calls == 0  # no resume — only polling
    assert sandbox.state == "RUNNING"


async def test_pausing_settles_to_paused_then_resumes(fake_sdk: _FakeSandboxFactory) -> None:
    """A sandbox caught mid-PAUSING must be polled to PAUSED and then resumed."""
    tool = TenkiExecuteCodeTool(sandbox_name="pausing")
    await _invoke(tool, "init")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    # Refresh sequence: PAUSING (initial reconcile) → PAUSED (first poll, triggers resume).
    sandbox.refresh_state_sequence = ["PAUSING", "PAUSED"]

    await _invoke(tool, "print('done')")
    assert sandbox.resume_calls == 1
    assert sandbox.state == "RUNNING"


async def test_user_shutdown_sandbox_is_auto_resumed(fake_sdk: _FakeSandboxFactory) -> None:
    """USER_SHUTDOWN (guest OS shut down inside the VM) is resumable — treat it like PAUSED."""
    tool = TenkiExecuteCodeTool(sandbox_name="guest-shutdown")
    await _invoke(tool, "print('a')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    sandbox.refresh_transitions_to = "USER_SHUTDOWN"
    await _invoke(tool, "print('b')")

    assert len(fake_sdk.create_calls) == 1  # resumed, not re-provisioned
    assert sandbox.resume_calls == 1
    assert sandbox.state == "RUNNING"
    assert len(sandbox.exec_calls) == 2


async def test_terminated_sandbox_is_replaced_by_fresh_provision(fake_sdk: _FakeSandboxFactory) -> None:
    """A sandbox that terminated between calls must be dropped and replaced."""
    tool = TenkiExecuteCodeTool(sandbox_name="gone")
    await _invoke(tool, "print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None
    first.refresh_transitions_to = "TERMINATED"

    await _invoke(tool, "print('b')")
    assert len(fake_sdk.create_calls) == 2
    assert fake_sdk.last_sandbox is not first
    assert first.resume_calls == 0
    assert fake_sdk.last_sandbox is not None
    assert len(fake_sdk.last_sandbox.exec_calls) == 1


@pytest.mark.parametrize("terminal_state", ["TERMINATED", "TERMINATING"])
async def test_reprovision_on_terminal_state_closes_owning_client(
    fake_sdk: _FakeSandboxFactory, terminal_state: str
) -> None:
    """Terminal-state re-provision must close the old sandbox's owning gRPC client.

    Without this a long-lived standalone tool that repeatedly hits a terminal
    state leaks one control-plane channel per cycle for the lifetime of the
    process.
    """
    tool = TenkiExecuteCodeTool(sandbox_name=f"leak-{terminal_state.lower()}")
    await _invoke(tool, "print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None
    first.refresh_transitions_to = terminal_state

    await _invoke(tool, "print('b')")

    assert fake_sdk.last_sandbox is not first
    assert first._client.closed is True


async def test_reprovision_regenerates_name_for_autogenerated_defaults(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """Auto-generated sandbox names must be refreshed on every re-provision."""
    tool = TenkiExecuteCodeTool()
    original_name = tool.sandbox_name
    await _invoke(tool, "print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None
    first.refresh_transitions_to = "TERMINATED"

    await _invoke(tool, "print('b')")
    assert len(fake_sdk.create_calls) == 2
    assert fake_sdk.create_calls[0]["name"] == original_name
    assert fake_sdk.create_calls[1]["name"] != original_name
    assert fake_sdk.create_calls[1]["name"].startswith("agent-framework-")


async def test_reprovision_preserves_explicit_sandbox_name(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """An explicit ``sandbox_name`` must be kept as-is across re-provision."""
    tool = TenkiExecuteCodeTool(sandbox_name="explicit-name")
    await _invoke(tool, "print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None
    first.refresh_transitions_to = "TERMINATED"

    await _invoke(tool, "print('b')")
    assert [call["name"] for call in fake_sdk.create_calls] == ["explicit-name", "explicit-name"]


async def test_refresh_failure_raises_without_dropping_handle(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """A transient ``refresh()`` failure must not orphan the sandbox.

    We keep the handle and surface an error; the next call retries the same
    sandbox rather than provisioning a duplicate (which would leak the first).
    """
    tool = TenkiExecuteCodeTool(sandbox_name="stale")
    await _invoke(tool, "print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None
    first.refresh_raises = RuntimeError("connection reset")

    contents = await _invoke(tool, "print('b')")
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "Failed to refresh" in (contents[0].error_details or "")

    # Handle preserved: no new sandbox, no close on the old one, no resume attempted.
    assert len(fake_sdk.create_calls) == 1
    assert first.closed is False
    assert first.resume_calls == 0

    # Next call succeeds when the API recovers — same sandbox is reused.
    await _invoke(tool, "print('c')")
    assert len(fake_sdk.create_calls) == 1
    assert len(first.exec_calls) == 2  # 'a' and 'c' (the 'b' call never reached exec)


async def test_persistent_resume_failure_surfaces_as_error_content(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """If ``resume()`` keeps raising past the poll budget, the failure surfaces as error content."""
    tool = TenkiExecuteCodeTool(sandbox_name="resume-fail")
    await _invoke(tool, "print('a')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None
    sandbox.refresh_transitions_to = "PAUSED"
    sandbox.resume_raises = RuntimeError("quota_exceeded: resume denied")

    contents = await _invoke(tool, "print('b')")
    assert len(contents) == 1
    assert contents[0].type == "error"
    assert "Failed to prepare Tenki sandbox" in (contents[0].message or "")
    assert "quota_exceeded" in (contents[0].error_details or "")
    assert sandbox.resume_calls >= 2  # retried within the budget before giving up
    assert len(fake_sdk.create_calls) == 1


async def test_transient_resume_failure_is_retried(fake_sdk: _FakeSandboxFactory) -> None:
    """A transient resume rejection must be retried within the poll budget.

    ``USER_SHUTDOWN`` links its pause snapshot asynchronously — the server
    rejects resume with "session has no pause snapshot" until the rootfs
    capture completes, so the first rejection must not fail the call.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="resume-retry")
    await _invoke(tool, "print('a')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None
    sandbox.refresh_transitions_to = "USER_SHUTDOWN"
    sandbox.resume_raises_once = RuntimeError("session has no pause snapshot")

    contents = await _invoke(tool, "print('b')")
    assert not any(c.type == "error" for c in contents)
    assert sandbox.resume_calls == 2  # first rejected, retry succeeded
    assert sandbox.state == "RUNNING"
    assert len(fake_sdk.create_calls) == 1


async def test_server_reverted_resume_is_retried(fake_sdk: _FakeSandboxFactory) -> None:
    """An accepted resume that the server reverts must be retried, not treated as fatal.

    A resume that fails on the node reverts the session to its source state
    (``RESUMING`` → ``USER_SHUTDOWN``/``PAUSED``, with ``last_resume_error``
    recorded server-side); the loop sees the resumable state again and retries.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="resume-revert")
    await _invoke(tool, "print('a')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    # Reconcile refresh reveals USER_SHUTDOWN; resume #1 is accepted (state →
    # RESUMING) but the next refresh shows the server reverted it; resume #2
    # is accepted and the sandbox reaches RUNNING.
    sandbox.refresh_state_sequence = ["USER_SHUTDOWN", "USER_SHUTDOWN", "RUNNING"]
    sandbox.resume_leaves_state_as = "RESUMING"

    contents = await _invoke(tool, "print('b')")
    assert not any(c.type == "error" for c in contents)
    assert sandbox.resume_calls == 2
    assert sandbox.state == "RUNNING"
    assert len(fake_sdk.create_calls) == 1


# ---------------------------------------------------------------------------
# Close lifecycle
# ---------------------------------------------------------------------------


async def test_close_terminates_sandbox_and_closes_owning_client(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="close-clean")
    await _invoke(tool, "print('x')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    await tool.close()
    assert sandbox.closed is True
    # Owning client must also be closed — the SDK's own ``close()`` does not
    # close the Client that ``Sandbox.create`` allocated, leaking the channel.
    assert sandbox._client.closed is True


async def test_close_preserves_handle_on_terminate_failure(fake_sdk: _FakeSandboxFactory) -> None:
    """Failed terminate must not silently discard the sandbox handle.

    Otherwise the sandbox stays live server-side, we can't retry, and the
    caller has no way to force cleanup.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="close-fail")
    await _invoke(tool, "print('x')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None
    sandbox.close_raises = RuntimeError("terminate rpc unavailable")

    with pytest.raises(RuntimeError, match="terminate rpc unavailable"):
        await tool.close()

    # Handle preserved — caller can retry ``close()``.
    assert tool._sandbox is sandbox
    assert sandbox._client.closed is False

    # Retry succeeds after the transient error clears.
    await tool.close()
    assert sandbox.closed is True
    assert sandbox._client.closed is True


async def test_close_serializes_with_concurrent_run(
    fake_sdk: _FakeSandboxFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``close()`` holds the sandbox lock for the whole terminate, so a concurrent
    run cannot race it — it blocks until close completes, then provisions fresh."""
    tool = TenkiExecuteCodeTool(sandbox_name="race")
    await _invoke(tool, "print('a')")
    first = fake_sdk.last_sandbox
    assert first is not None

    close_entered = threading.Event()
    release_close = threading.Event()
    original_close_if_open = first.close_if_open

    def slow_close() -> None:
        close_entered.set()
        assert release_close.wait(timeout=5), "close was never released"
        original_close_if_open()

    monkeypatch.setattr(first, "close_if_open", slow_close)

    close_task = asyncio.create_task(tool.close())
    assert await asyncio.to_thread(close_entered.wait, 5)

    # A run started mid-close must block on the lock, not interleave.
    invoke_task = asyncio.create_task(_invoke(tool, "print('b')"))
    await asyncio.sleep(0.05)
    assert not invoke_task.done()

    release_close.set()
    await close_task
    await invoke_task

    assert first.closed is True
    assert first._client.closed is True
    second = fake_sdk.last_sandbox
    assert second is not None
    assert second is not first
    assert second.closed is False


async def test_close_waits_for_in_flight_exec(fake_sdk: _FakeSandboxFactory) -> None:
    """``close()`` must block until an in-flight exec finishes, not terminate under it.

    Reconcile + exec run under the sandbox lock in a worker thread; ``close()``
    takes the same lock, so it cannot terminate the sandbox (or close its gRPC
    client) while ``sandbox.exec`` is still running.
    """
    tool = TenkiExecuteCodeTool(sandbox_name="exec-close")
    await _invoke(tool, "print('warm-up')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    exec_entered = threading.Event()
    release_exec = threading.Event()

    def blocking_exec(args: Any, kwargs: Any) -> _FakeExecResult:
        exec_entered.set()
        assert release_exec.wait(timeout=5), "exec was never released"
        return _FakeExecResult(stdout_text="slow done\n")

    sandbox.script_handler = blocking_exec

    invoke_task = asyncio.create_task(_invoke(tool, "print('slow')"))
    assert await asyncio.to_thread(exec_entered.wait, 5)

    close_task = asyncio.create_task(tool.close())
    await asyncio.sleep(0.05)
    # The exec is mid-flight — close() must be parked on the lock, sandbox untouched.
    assert not close_task.done()
    assert sandbox.closed is False
    assert sandbox._client.closed is False

    release_exec.set()
    contents = await invoke_task
    await close_task

    # The exec completed normally *before* the terminate ran.
    assert any("slow done" in (c.text or "") for c in contents if c.type == "text")
    assert sandbox.closed is True
    assert sandbox._client.closed is True


async def test_close_is_idempotent(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="idempotent")
    await tool.close()  # no sandbox yet — no-op
    await _invoke(tool, "print('x')")
    await tool.close()
    await tool.close()  # second close — no-op
    assert fake_sdk.last_sandbox is not None
    assert fake_sdk.last_sandbox.closed is True


async def test_close_and_next_call_creates_new_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    tool = TenkiExecuteCodeTool(sandbox_name="cycle")
    await _invoke(tool, "print('a')")
    first_sandbox = fake_sdk.last_sandbox
    assert first_sandbox is not None
    await tool.close()
    assert first_sandbox.closed is True

    await _invoke(tool, "print('b')")
    assert len(fake_sdk.create_calls) == 2
    assert fake_sdk.last_sandbox is not first_sandbox


async def test_async_context_manager_closes_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    async with TenkiExecuteCodeTool(sandbox_name="cm") as tool:
        await _invoke(tool, "print('inside')")
    assert fake_sdk.last_sandbox is not None
    assert fake_sdk.last_sandbox.closed is True


# ---------------------------------------------------------------------------
# Provider run-scoping — before_run / after_run / close cleanup
# ---------------------------------------------------------------------------


class _StubContext:
    """Structurally compatible with ``SessionContext``. Records the extended tools/instructions."""

    def __init__(self) -> None:
        self.tools_calls: list[tuple[str, list[Any]]] = []
        self.instructions_calls: list[tuple[str, str]] = []

    def extend_tools(self, source_id: str, tools: list[Any]) -> None:
        self.tools_calls.append((source_id, tools))

    def extend_instructions(self, source_id: str, instructions: str) -> None:
        self.instructions_calls.append((source_id, instructions))


def _run_tool_from(context: _StubContext) -> TenkiExecuteCodeTool:
    """Extract the run-scoped tool that ``before_run`` extended onto the context."""
    _, tools = context.tools_calls[-1]
    assert len(tools) == 1
    assert isinstance(tools[0], TenkiExecuteCodeTool)
    return tools[0]


async def test_provider_before_run_mints_fresh_run_scoped_tool(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    provider = TenkiCodeActProvider(sandbox_name="run-scope")
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)

    # Extended tools carry a NEW ``TenkiExecuteCodeTool`` instance, not the base template.
    assert len(context.tools_calls) == 1
    run_tool = _run_tool_from(context)
    assert run_tool is not provider.execute_code_tool

    # Provider state is serialized with the session, so it holds only the
    # sandbox name (a plain string); the live handle stays on the provider.
    assert state[provider.source_id] == run_tool.sandbox_name
    assert isinstance(state[provider.source_id], str)
    assert provider._live_run_tools[run_tool.sandbox_name] is run_tool


async def test_provider_run_tool_uses_sandbox_name_as_prefix(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """Explicit ``sandbox_name`` on the provider becomes the prefix for run-scoped names."""
    provider = TenkiCodeActProvider(sandbox_name="analysis-agent")
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)

    run_tool = _run_tool_from(context)
    assert run_tool.sandbox_name.startswith("analysis-agent-")
    suffix = run_tool.sandbox_name.rsplit("-", 1)[-1]
    assert len(suffix) == 8
    int(suffix, 16)


async def test_provider_run_tool_uses_default_prefix_when_unset(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    provider = TenkiCodeActProvider()
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)

    run_tool = _run_tool_from(context)
    assert run_tool.sandbox_name.startswith("agent-framework-")


async def test_provider_run_tool_gets_short_pause_retention(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """Provider-minted run tools inherit the short run-scoped pause retention."""
    provider = TenkiCodeActProvider(sandbox_name="retention-prov")
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
    run_tool = _run_tool_from(context)
    await _invoke(run_tool, "pass")
    expected = _tenki_module._DEFAULT_RUN_SCOPED_PAUSE_RETENTION_SECONDS
    assert fake_sdk.create_calls[0]["pause_retention"] == expected


async def test_provider_explicit_pause_retention_reaches_run_tool(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    provider = TenkiCodeActProvider(sandbox_name="retention-prov", pause_retention_seconds=1800)
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
    run_tool = _run_tool_from(context)
    await _invoke(run_tool, "pass")
    assert fake_sdk.create_calls[0]["pause_retention"] == 1800


async def test_provider_after_run_terminates_run_scoped_sandbox(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """The run's sandbox must be terminated by ``after_run`` — no cross-run bleed."""
    provider = TenkiCodeActProvider(sandbox_name="isolated")
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
    run_tool = _run_tool_from(context)

    # Exercise the run tool so it actually provisions a sandbox.
    await _invoke(run_tool, "print('hi')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None
    assert sandbox.closed is False

    await provider.after_run(agent=None, session=None, context=cast(Any, context), state=state)
    assert sandbox.closed is True
    assert provider.source_id not in state


async def test_provider_after_run_retains_tool_on_close_failure(fake_sdk: _FakeSandboxFactory) -> None:
    """When ``after_run`` fails to terminate, the tool must stay in the live-set.

    Preserves the "handle survives a failed terminate" contract from
    :meth:`TenkiExecuteCodeTool.close` on the provider path — otherwise
    ``provider.close()`` has no reference to retry against and the sandbox
    leaks until ``max_duration`` reaps it.
    """
    provider = TenkiCodeActProvider(sandbox_name="retry")
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
    run_tool = _run_tool_from(context)
    await _invoke(run_tool, "print('hi')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    sandbox.close_raises = RuntimeError("terminate rpc unavailable")
    await provider.after_run(agent=None, session=None, context=cast(Any, context), state=state)
    assert sandbox.closed is False
    assert provider.source_id not in state  # framework won't call after_run twice
    assert provider._live_run_tools.get(run_tool.sandbox_name) is run_tool

    # provider.close() retries the failed terminate.
    await provider.close()
    assert sandbox.closed is True


async def test_provider_two_runs_get_distinct_sandboxes(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """Consecutive runs on the same provider must get isolated sandboxes."""
    provider = TenkiCodeActProvider(sandbox_name="two-run")

    # Run 1
    state1: dict[str, Any] = {}
    context1 = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context1), state=state1)
    tool1 = _run_tool_from(context1)
    await _invoke(tool1, "x = 1")
    sandbox1 = fake_sdk.last_sandbox
    await provider.after_run(agent=None, session=None, context=cast(Any, context1), state=state1)

    # Run 2
    state2: dict[str, Any] = {}
    context2 = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context2), state=state2)
    tool2 = _run_tool_from(context2)
    await _invoke(tool2, "x = 2")
    sandbox2 = fake_sdk.last_sandbox

    assert tool1 is not tool2
    assert sandbox1 is not sandbox2
    assert sandbox1 is not None and sandbox1.closed is True
    assert sandbox2 is not None and sandbox2.closed is False
    assert sandbox1.name != sandbox2.name  # per-run suffix keeps dashboard names distinguishable


async def test_provider_close_cleans_up_orphaned_run_tools(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """If ``after_run`` is skipped (e.g. mid-run exception), ``close()`` still cleans up."""
    provider = TenkiCodeActProvider(sandbox_name="orphan")
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
    run_tool = _run_tool_from(context)
    await _invoke(run_tool, "print('hi')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    # Simulate the agent-framework runtime bailing out before after_run fires:
    # user calls provider.close() to clean up.
    await provider.close()
    assert sandbox.closed is True


async def test_provider_close_retains_tool_on_failure_and_retries(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """A terminate that fails during ``close()`` must stay in the live-set and raise.

    ``close()`` removes entries only on success and surfaces the failure to the
    caller — a silently-swallowed error would tell ``async with`` users the
    cleanup succeeded while the microVM is still live, and dropping the
    reference would make a second ``close()`` a no-op.
    """
    provider = TenkiCodeActProvider(sandbox_name="close-retry")
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
    run_tool = _run_tool_from(context)
    await _invoke(run_tool, "print('hi')")
    sandbox = fake_sdk.last_sandbox
    assert sandbox is not None

    sandbox.close_raises = RuntimeError("terminate rpc unavailable")
    with pytest.raises(RuntimeError, match="run-scoped Tenki sandbox"):
        await provider.close()
    assert sandbox.closed is False
    assert provider._live_run_tools.get(run_tool.sandbox_name) is run_tool

    # The transient error cleared — a second close() retries and succeeds.
    await provider.close()
    assert sandbox.closed is True
    assert provider._live_run_tools == {}


async def test_provider_close_attempts_every_tool_before_raising(
    fake_sdk: _FakeSandboxFactory,
) -> None:
    """One failing terminate must not stop ``close()`` from closing the others."""
    provider = TenkiCodeActProvider(sandbox_name="close-all")

    tools: list[TenkiExecuteCodeTool] = []
    for _ in range(2):
        state: dict[str, Any] = {}
        context = _StubContext()
        await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
        run_tool = _run_tool_from(context)
        await _invoke(run_tool, "print('hi')")
        tools.append(run_tool)
    failing_sandbox, ok_sandbox = fake_sdk.sandboxes[0], fake_sdk.sandboxes[1]

    failing_sandbox.close_raises = RuntimeError("terminate rpc unavailable")
    with pytest.raises(RuntimeError, match="1 run-scoped Tenki sandbox"):
        await provider.close()

    # The healthy sandbox was still closed; only the failed one stays tracked.
    assert ok_sandbox.closed is True
    assert failing_sandbox.closed is False
    assert set(provider._live_run_tools) == {tools[0].sandbox_name}


async def test_provider_async_context_manager_closes_sandbox(fake_sdk: _FakeSandboxFactory) -> None:
    async with TenkiCodeActProvider(sandbox_name="prov-cm") as provider:
        state: dict[str, Any] = {}
        context = _StubContext()
        await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)
        run_tool = _run_tool_from(context)
        await _invoke(run_tool, "print('x')")
        assert fake_sdk.last_sandbox is not None
        assert fake_sdk.last_sandbox.closed is False
    # Exiting the ``async with`` should have terminated the run tool's sandbox
    # (even without an explicit after_run).
    assert fake_sdk.last_sandbox is not None
    assert fake_sdk.last_sandbox.closed is True


async def test_provider_injects_codeact_instructions(fake_sdk: _FakeSandboxFactory) -> None:
    provider = TenkiCodeActProvider()
    state: dict[str, Any] = {}
    context = _StubContext()
    await provider.before_run(agent=None, session=None, context=cast(Any, context), state=state)

    assert len(context.instructions_calls) == 1
    source_id, instructions = context.instructions_calls[0]
    assert source_id == TenkiCodeActProvider.DEFAULT_SOURCE_ID
    # Sanity: the injected instructions still cover the field-observed footguns.
    assert "print(" in instructions
    assert "python3 -c" in instructions
    assert "filesystem persists" in instructions
    assert "subprocess" in instructions
    assert "!command" in instructions
    assert "compound statements" in instructions
    assert "with open('/tmp/x.txt') as f: print(f.read())" in instructions


async def test_tool_name_and_description() -> None:
    tool = TenkiExecuteCodeTool()
    assert tool.name == "execute_code"
    assert "Tenki" in tool.description


# ---------------------------------------------------------------------------
# Integration test — real Tenki service. Requires TENKI_API_KEY. Marked as
# integration so ``pytest -m "not integration"`` (the default suite) skips it.
# Only the integration test is POSIX-only; unit tests above work on any OS.
# ---------------------------------------------------------------------------


def _tenki_integration_skip_reason() -> str | None:
    if sys.platform == "win32":
        return "Tenki integration tests use POSIX-style shell invocations."
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
@pytest.mark.flaky(reruns=2, reruns_delay=5)
@skip_if_tenki_integration_disabled
async def test_integration_execute_hello_world() -> None:
    # "or None": CI expands an unconfigured ``vars.TENKI_PROJECT_ID`` to "", and an
    # explicit empty-string constructor arg would win over the env fallback.
    project_id = os.environ.get("TENKI_PROJECT_ID") or None
    async with TenkiExecuteCodeTool(
        sandbox_name=f"agent-framework-ci-{os.getpid()}",
        project_id=project_id,
        max_duration_seconds=300,
    ) as tool:
        contents = await _invoke(tool, "print('hello from tenki')")
    text_contents = [c for c in contents if c.type == "text"]
    assert any("hello from tenki" in (c.text or "") for c in text_contents)


@pytest.mark.integration
@pytest.mark.flaky(reruns=2, reruns_delay=5)
@skip_if_tenki_integration_disabled
async def test_integration_filesystem_persists_across_calls() -> None:
    """Files written in one ``execute_code`` call are visible in the next."""
    # "or None": CI expands an unconfigured ``vars.TENKI_PROJECT_ID`` to "", and an
    # explicit empty-string constructor arg would win over the env fallback.
    project_id = os.environ.get("TENKI_PROJECT_ID") or None
    async with TenkiExecuteCodeTool(
        sandbox_name=f"agent-framework-ci-fs-{os.getpid()}",
        project_id=project_id,
        max_duration_seconds=300,
    ) as tool:
        marker = f"hello-{os.getpid()}"
        write_contents = await _invoke(tool, f"open('/tmp/marker', 'w').write({marker!r}); print('wrote')")
        assert any("wrote" in (c.text or "") for c in write_contents if c.type == "text")

        read_contents = await _invoke(tool, "print(open('/tmp/marker').read())")
        assert any(marker in (c.text or "") for c in read_contents if c.type == "text")


@pytest.mark.integration
@pytest.mark.flaky(reruns=2, reruns_delay=5)
@skip_if_tenki_integration_disabled
async def test_integration_failure_diagnostics_carry_signal_and_exit_code() -> None:
    """A killed subprocess must surface ``signal``/``exit_code`` in the error content."""
    # "or None": CI expands an unconfigured ``vars.TENKI_PROJECT_ID`` to "", and an
    # explicit empty-string constructor arg would win over the env fallback.
    project_id = os.environ.get("TENKI_PROJECT_ID") or None
    async with TenkiExecuteCodeTool(
        sandbox_name=f"agent-framework-ci-fail-{os.getpid()}",
        project_id=project_id,
        max_duration_seconds=300,
    ) as tool:
        # Force a non-zero exit so we can verify the diagnostic fields flow through.
        contents = await _invoke(tool, "import sys; sys.exit(42)")
    error_contents = [c for c in contents if c.type == "error"]
    assert len(error_contents) == 1
    assert "status 42" in (error_contents[0].message or "")


@pytest.mark.integration
@pytest.mark.flaky(reruns=2, reruns_delay=5)
@skip_if_tenki_integration_disabled
async def test_integration_close_removes_sandbox_from_workspace() -> None:
    """After ``close()``, the sandbox reaches ``TERMINATED`` server-side.

    Guards against two vacuous passes: provisioning/exec failure (the old
    version never asserted the invoke succeeded, so a create error also
    "removed" the sandbox from the list) and incomplete cleanup (a sandbox
    left ``PAUSED`` or stuck ``TERMINATING`` is not RUNNING either). Verifies
    by sandbox id, not by name absence from a filtered list.
    """
    from tenki_sandbox import Client

    # "or None": CI expands an unconfigured ``vars.TENKI_PROJECT_ID`` to "", and an
    # explicit empty-string constructor arg would win over the env fallback.
    project_id = os.environ.get("TENKI_PROJECT_ID") or None
    unique_name = f"agent-framework-ci-teardown-{os.getpid()}"

    async with TenkiExecuteCodeTool(
        sandbox_name=unique_name,
        project_id=project_id,
        max_duration_seconds=300,
    ) as tool:
        contents = await _invoke(tool, "print('provisioned')")
        errors = [c for c in contents if c.type == "error"]
        assert not errors, f"provisioning/exec failed: {[e.message for e in errors]}"
        assert any("provisioned" in (c.text or "") for c in contents if c.type == "text")
        sandbox = tool._sandbox
        assert sandbox is not None, "expected a live sandbox handle after a successful exec"
        sandbox_id = sandbox.id

    client = Client()
    try:
        deadline = time.monotonic() + 30
        while True:
            state = client.get(sandbox_id).state
            if state == "TERMINATED":
                break
            assert time.monotonic() < deadline, (
                f"sandbox {unique_name} ({sandbox_id}) still in state={state} 30s after close()"
            )
            await asyncio.sleep(1)
    finally:
        client.close()
