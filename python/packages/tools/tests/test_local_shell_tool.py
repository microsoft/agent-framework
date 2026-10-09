# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
import shlex
import shutil
import signal
import sys
from collections.abc import Awaitable, Mapping, Sequence
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import Agent, AgentSession, BaseChatClient, ChatResponse, Content, FunctionInvocationLayer, Message
from agent_framework.security import (
    ContentLabel,
    IntegrityLabel,
    LabelTrackingFunctionMiddleware,
    PolicyEnforcementFunctionMiddleware,
)

from agent_framework_tools._feature_usage import FeatureIndex
from agent_framework_tools.shell import LocalShellTool, ShellCommandError, ShellPolicy, ShellResult
from agent_framework_tools.shell._executor import _popen_kwargs_for_group, run_stateless

_TEST_SHELL = "agent-framework-test-shell"
_APPROVED_COMMAND = "printf '%s' approved-value"
_ALTERNATE_COMMAND = "printf '%s' alternate-value"
_POWERSHELL = shutil.which("pwsh") or (shutil.which("powershell") if sys.platform == "win32" else None)


class _FakeExecProcess:
    def __init__(
        self,
        *,
        returncode: int | None = 0,
        communicate_results: list[tuple[bytes, bytes] | BaseException] | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = object()
        self.stderr = object()
        self._communicate_results = list(communicate_results or [(b"", b"")])

    async def communicate(self) -> tuple[bytes, bytes]:
        result = self._communicate_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        stdout, stderr = result
        return stdout, stderr


class _ScriptedFunctionClient(FunctionInvocationLayer, BaseChatClient):
    def __init__(self, responses: Sequence[ChatResponse]) -> None:
        super().__init__()
        self._responses = list(responses)

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse]:
        assert not stream

        async def get_response() -> ChatResponse:
            if self._responses:
                return self._responses.pop(0)
            return ChatResponse(messages=Message(role="assistant", contents=["done"]))

        return get_response()


async def _request_variable_shell_approval(
    session_id: str,
) -> tuple[Agent[Any], AgentSession, Content, str, LabelTrackingFunctionMiddleware]:
    tracker = LabelTrackingFunctionMiddleware()
    session = AgentSession(session_id=session_id)
    variable_id = tracker.get_variable_store(session).store(
        _APPROVED_COMMAND,
        ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
    )
    function_call = Content.from_function_call(
        call_id="provider-shell-call",
        name="run_shell",
        arguments={"command": f"[{variable_id}]"},
        id="shell-call-occurrence",
    )
    client = _ScriptedFunctionClient([
        ChatResponse(messages=Message(role="assistant", contents=[function_call])),
    ])
    # Isolate the variable-aware policy approval from the tool's independent blanket approval.
    shell = LocalShellTool(
        mode="stateless",
        shell=[_TEST_SHELL],
        approval_mode="never_require",
        acknowledge_unsafe=True,
    )
    agent = Agent(
        client=client,
        tools=[shell.as_function()],
        middleware=[
            tracker,
            PolicyEnforcementFunctionMiddleware(approval_on_violation=True),
        ],
    )

    response = await agent.run("Run the hidden command", session=session)

    assert len(response.user_input_requests) == 1
    return agent, session, response.user_input_requests[0], variable_id, tracker


async def test_stateless_echo() -> None:
    tool = LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True)
    cmd = "Write-Output hello" if sys.platform == "win32" else "echo hello"
    with patch("agent_framework_tools.shell._tool.mark_feature_used") as mark_feature_used:
        result = await tool.run(cmd)

    mark_feature_used.assert_called_once_with(FeatureIndex.TOOLS_SHELL)
    assert "hello" in result.stdout
    assert result.exit_code == 0
    assert result.timed_out is False


async def test_stateless_exit_code_propagates() -> None:
    tool = LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True)
    cmd = "exit 7" if sys.platform == "win32" else "sh -c 'exit 7'"
    result = await tool.run(cmd)
    assert result.exit_code == 7


async def test_stateless_timeout_kills_long_command() -> None:
    tool = LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True, timeout=0.5)
    cmd = "Start-Sleep -Seconds 5" if sys.platform == "win32" else "sleep 5"
    result = await tool.run(cmd)
    assert result.timed_out is True


async def test_policy_denies_before_execution() -> None:
    tool = LocalShellTool(
        mode="stateless",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        policy=ShellPolicy(denylist=[r"\brm\s+(?:-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(?:/|~|\*)"]),
    )
    with pytest.raises(ShellCommandError):
        await tool.run("rm -rf /")


async def test_allowlist_narrows_to_approved_commands() -> None:
    tool = LocalShellTool(
        mode="stateless",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        policy=ShellPolicy(allowlist=[r"^echo\b", r"^Write-Output\b"]),
    )
    cmd = "Write-Output ok" if sys.platform == "win32" else "echo ok"
    result = await tool.run(cmd)
    assert "ok" in result.stdout
    with pytest.raises(ShellCommandError):
        await tool.run("ls -la")


async def test_audit_hook_fires_for_allowed_commands() -> None:
    seen: list[str] = []
    tool = LocalShellTool(
        mode="stateless",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        on_command=seen.append,
    )
    cmd = "Write-Output hi" if sys.platform == "win32" else "echo hi"
    await tool.run(cmd)
    assert seen == [cmd]


def test_local_shell_tool_handles_mode_and_environment_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="mode must be"):
        LocalShellTool(mode="bogus")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

    monkeypatch.setenv("INHERITED", "yes")
    inherited = LocalShellTool(
        mode="stateless",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        env={"EXTRA": "1"},
    )
    clean = LocalShellTool(
        mode="stateless",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        env={"ONLY": "2"},
        clean_env=True,
    )

    assert inherited._env is not None
    assert inherited._env["INHERITED"] == "yes"
    assert inherited._env["EXTRA"] == "1"
    assert clean._env == {"ONLY": "2"}


async def test_local_shell_tool_stateless_start_is_noop() -> None:
    tool = LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True)
    await tool.start()
    await tool.close()


async def test_local_shell_tool_raises_if_start_did_not_create_session() -> None:
    tool = LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True)

    with patch.object(tool, "start", AsyncMock()), pytest.raises(RuntimeError, match="session failed to start"):
        await tool.run("echo hi")


async def test_local_shell_tool_as_function_returns_policy_errors() -> None:
    tool = LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True)

    with patch.object(tool, "run", AsyncMock(side_effect=ShellCommandError("blocked"))):
        function = tool.as_function(description="custom shell")
        assert function.func is not None
        result = await function.func("pwd")

    assert result == "blocked"
    assert function.description == "custom shell"


def test_local_shell_tool_reanchors_powershell_paths() -> None:
    tool = LocalShellTool(
        mode="persistent",
        shell="pwsh",
        workdir="C:\\repo",
        approval_mode="never_require",
        acknowledge_unsafe=True,
    )

    assert tool._maybe_reanchor("Get-ChildItem").startswith("Set-Location -LiteralPath 'C:\\repo'")


def test_popen_kwargs_for_group_covers_windows_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    import agent_framework_tools.shell._executor as executor_module

    monkeypatch.setattr(executor_module.sys, "platform", "win32")
    monkeypatch.setattr(executor_module.subprocess, "CREATE_NEW_PROCESS_GROUP", 77, raising=False)

    assert _popen_kwargs_for_group() == {"creationflags": 77}


async def test_run_stateless_adds_powershell_encoding_preamble() -> None:
    proc = _FakeExecProcess(returncode=0, communicate_results=[(b"ok", b"")])

    with (
        patch("agent_framework_tools.shell._executor.is_powershell", return_value=True),
        patch(
            "agent_framework_tools.shell._executor.asyncio.create_subprocess_exec",
            AsyncMock(return_value=proc),
        ) as create_proc,
    ):
        result = await run_stateless(
            ["pwsh", "-Command"],
            "Write-Output hi",
            workdir=None,
            env=None,
            timeout=1.0,
            max_output_bytes=1024,
        )

    assert result.stdout == "ok"
    assert create_proc.await_args is not None
    assert create_proc.await_args.args[-1].startswith("$OutputEncoding = [Console]::OutputEncoding")


async def test_run_stateless_timeout_returns_empty_output_if_drain_fails() -> None:
    proc = _FakeExecProcess(returncode=None, communicate_results=[asyncio.TimeoutError(), RuntimeError("drain failed")])

    with (
        patch("agent_framework_tools.shell._executor.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
        patch("agent_framework_tools.shell._executor.kill_process_tree", AsyncMock()) as kill_tree,
    ):
        result = await run_stateless(
            ["/bin/sh", "-c"],
            "sleep 5",
            workdir=None,
            env=None,
            timeout=0.01,
            max_output_bytes=1024,
        )

    kill_tree.assert_awaited_once_with(proc)
    assert result.timed_out is True
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.skipif(sys.platform == "win32", reason="persistent-mode sentinel on POSIX")
async def test_persistent_preserves_cwd_and_exports_across_calls(tmp_path: os.PathLike[str]) -> None:
    async with LocalShellTool(
        mode="persistent",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        workdir=str(tmp_path),
        confine_workdir=False,
    ) as tool:
        await tool.run("export AGENT_FRAMEWORK_TEST_MARKER=xyz")
        result = await tool.run("echo $AGENT_FRAMEWORK_TEST_MARKER")
        assert "xyz" in result.stdout

        subdir = os.path.join(str(tmp_path), "sub")
        os.mkdir(subdir)
        await tool.run(f"cd {subdir}")
        pwd = await tool.run("pwd")
        # subdir resolves to itself modulo symlinks
        assert os.path.realpath(pwd.stdout.strip()) == os.path.realpath(subdir)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell-specific error handling")
async def test_persistent_powershell_propagates_cmdlet_error() -> None:
    """Cmdlet failures (not just native-process exits) should surface as non-zero rc."""
    async with LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True) as tool:
        # Get-Item on a missing path raises; $ErrorActionPreference='Stop' +
        # our catch block should map this to exit_code != 0.
        result = await tool.run("Get-Item C:\\this\\path\\does\\not\\exist\\for\\af")
        assert result.exit_code != 0
        assert result.stderr  # message surfaced


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell-specific exit-code handling")
async def test_persistent_powershell_does_not_inherit_previous_exit_code() -> None:
    """A cmdlet-only command must not report the rc of an earlier native command.

    ``$LASTEXITCODE`` is a session-wide automatic variable that only native
    (external) executables update, so it stays set after such a command and
    would otherwise be reported for every later cmdlet-only command.
    """
    async with LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True) as tool:
        failing = await tool.run("cmd /c exit 3")
        assert failing.exit_code == 3

        succeeding = await tool.run("Write-Output ok")
        assert succeeding.exit_code == 0, f"inherited stale rc {succeeding.exit_code} from the previous command"
        assert "ok" in succeeding.stdout

        # The fix must not cost the session state persistent mode exists for:
        # the user's own command can still read the previous native exit code,
        # while the command reporting it exits 0 itself.
        readback = await tool.run("Write-Output $LASTEXITCODE")
        assert readback.exit_code == 0
        assert readback.stdout.strip() == "3", (
            f"$LASTEXITCODE no longer visible to the user's command: {readback.stdout!r}"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell-specific encoding")
async def test_persistent_powershell_utf8_roundtrip() -> None:
    """Non-ASCII output should round-trip without mojibake."""
    async with LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True) as tool:
        result = await tool.run("Write-Output 'café'")
        assert "café" in result.stdout


@pytest.mark.skipif(_POWERSHELL is None, reason="PowerShell is not installed")
async def test_persistent_powershell_returns_formatted_object_output(tmp_path: os.PathLike[str]) -> None:
    """Output that pwsh renders as a table must arrive before the sentinel.

    The host formats a script block's output only after the block returns,
    which is after the sentinel has been written, so this output used to be
    dropped, along with any plain string written after the first object.
    Runs wherever PowerShell is installed, not just on Windows.
    """
    assert _POWERSHELL is not None
    async with LocalShellTool(
        mode="persistent",
        shell=[_POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "-"],
        approval_mode="never_require",
        acknowledge_unsafe=True,
        workdir=str(tmp_path),
    ) as tool:
        result = await tool.run("[pscustomobject]@{ Marker = 'af-object' }; Write-Output 'af-trailing'")
        assert result.exit_code == 0
        assert "af-object" in result.stdout
        assert "af-trailing" in result.stdout

        selected = await tool.run(f"Get-Item -LiteralPath '{tmp_path}' | Select-Object Name")
        assert selected.exit_code == 0
        assert os.path.basename(str(tmp_path)) in selected.stdout


async def test_concurrent_first_calls_do_not_spawn_two_sessions() -> None:
    """Regression: startup must be serialised so two concurrent first callers
    don't each spawn their own subprocess."""
    import asyncio as _asyncio

    tool = LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True)
    try:
        cmd = "Write-Output $PID" if sys.platform == "win32" else "echo $$"
        r1, r2 = await _asyncio.gather(tool.run(cmd), tool.run(cmd))
        assert r1.stdout.strip() == r2.stdout.strip(), (
            f"Different PIDs => multiple subprocesses spawned: {r1.stdout!r} vs {r2.stdout!r}"
        )
    finally:
        await tool.close()


@pytest.mark.skipif(sys.platform != "win32", reason="persistent-mode sentinel on PowerShell")
async def test_persistent_preserves_state_powershell(tmp_path: os.PathLike[str]) -> None:
    async with LocalShellTool(
        mode="persistent",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        workdir=str(tmp_path),
        confine_workdir=False,
    ) as tool:
        await tool.run("$env:AGENT_FRAMEWORK_TEST_MARKER = 'xyz'")
        result = await tool.run("Write-Output $env:AGENT_FRAMEWORK_TEST_MARKER")
        assert "xyz" in result.stdout
        r2 = await tool.run("$x = 42; Write-Output $x")
        assert "42" in r2.stdout


async def test_as_function_wires_kind_and_approval() -> None:
    tool = LocalShellTool(approval_mode="always_require")
    ft = tool.as_function(name="shell_exec")
    assert ft.name == "shell_exec"
    assert ft.kind == "shell"
    assert ft.approval_mode == "always_require"


async def test_as_function_preserves_structured_shell_result() -> None:
    shell_result = ShellResult(
        stdout="partial output",
        stderr="command failed",
        exit_code=3,
        duration_ms=12,
        truncated=True,
        timed_out=True,
    )
    tool = LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True)

    with patch.object(tool, "run", AsyncMock(return_value=shell_result)):
        function = tool.as_function()
        result = await function.invoke(arguments={"command": "ignored"})
        raw_result = await function.invoke(arguments={"command": "ignored"}, skip_parsing=True)

    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == shell_result.format_for_model()
    assert result[0].additional_properties == {
        "stdout": "partial output",
        "stderr": "command failed",
        "exit_code": 3,
        "truncated": True,
        "timed_out": True,
    }
    assert isinstance(raw_result, str)
    assert raw_result == shell_result.format_for_model()
    assert json.loads(json.dumps(raw_result)) == shell_result.format_for_model()


async def test_variable_shell_approval_executes_only_the_reviewed_command() -> None:
    agent, session, request, variable_id, _ = await _request_variable_shell_approval("exact-shell-approval")

    assert request.id == "shell-call-occurrence"
    assert request.function_call is not None
    assert request.function_call.call_id == "provider-shell-call"
    assert request.function_call.name == "run_shell"
    assert request.function_call.parse_arguments() == {"command": f"[{variable_id}]"}

    create_process = AsyncMock(return_value=_FakeExecProcess(communicate_results=[(b"approved-value", b"")]))
    with patch("agent_framework_tools.shell._executor.asyncio.create_subprocess_exec", create_process):
        await agent.run(request.to_function_approval_response(True), session=session)

    assert create_process.await_count == 1
    assert create_process.await_args is not None
    assert create_process.await_args.args == (_TEST_SHELL, "-c", _APPROVED_COMMAND)


async def test_variable_shell_approval_blocks_changed_resolved_command() -> None:
    agent, session, request, variable_id, _ = await _request_variable_shell_approval("changed-shell-variable")
    security_state = session.state["__agent_framework_fides_security__"]
    security_state["variables"][variable_id]["content"] = json.dumps(_ALTERNATE_COMMAND)

    create_process = AsyncMock()
    with patch("agent_framework_tools.shell._executor.asyncio.create_subprocess_exec", create_process):
        response = await agent.run(request.to_function_approval_response(True), session=session)

    create_process.assert_not_awaited()
    replacement = response.user_input_requests
    assert len(replacement) == 1
    assert replacement[0].id != request.id
    assert replacement[0].function_call is not None
    assert replacement[0].function_call.parse_arguments() == {"command": f"[{variable_id}]"}


@pytest.mark.parametrize("mutation", ["reference", "command", "arguments", "request_id", "call_id"])
async def test_variable_shell_approval_substitutions_cannot_change_executed_argv(mutation: str) -> None:
    agent, session, request, _, tracker = await _request_variable_shell_approval(f"substituted-shell-{mutation}")
    response = Content.from_dict(request.to_function_approval_response(True).to_dict())
    assert response.function_call is not None

    if mutation == "reference":
        alternate_variable_id = tracker.get_variable_store(session).store(
            _ALTERNATE_COMMAND,
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        response.function_call.arguments = {"command": f"[{alternate_variable_id}]"}
    elif mutation == "command":
        response.function_call.arguments = {"command": _ALTERNATE_COMMAND}
    elif mutation == "arguments":
        response.function_call.arguments = {
            "command": _ALTERNATE_COMMAND,
            "unexpected": "substituted",
        }
    elif mutation == "request_id":
        response.id = "different-request"
    else:
        response.function_call.call_id = "different-provider-call"

    create_process = AsyncMock(
        side_effect=lambda *_args, **_kwargs: _FakeExecProcess(communicate_results=[(b"approved-value", b"")])
    )
    with patch("agent_framework_tools.shell._executor.asyncio.create_subprocess_exec", create_process):
        await agent.run(response, session=session)

    if mutation == "request_id":
        create_process.assert_not_awaited()
    else:
        assert create_process.await_count == 1
        assert create_process.await_args is not None
        assert create_process.await_args.args == (_TEST_SHELL, "-c", _APPROVED_COMMAND)


async def test_variable_shell_approval_cannot_be_replayed_on_later_turn_or_session() -> None:
    agent, session, request, _, _ = await _request_variable_shell_approval("shell-approval-replay")
    approval = request.to_function_approval_response(True)
    create_process = AsyncMock(
        side_effect=lambda *_args, **_kwargs: _FakeExecProcess(communicate_results=[(b"approved-value", b"")])
    )

    with patch("agent_framework_tools.shell._executor.asyncio.create_subprocess_exec", create_process):
        await agent.run(approval, session=session)
        await agent.run(approval, session=session)
        await agent.run(approval, session=AgentSession(session_id="different-shell-session"))

    assert create_process.await_count == 1
    assert create_process.await_args is not None
    assert create_process.await_args.args == (_TEST_SHELL, "-c", _APPROVED_COMMAND)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX persistent reanchor test")
async def test_persistent_confines_workdir_by_default(tmp_path: os.PathLike[str]) -> None:
    """With the default ``confine_workdir=True``, a ``cd`` in one call
    must not leak into the next: each command is reanchored to ``workdir``."""
    subdir = os.path.join(str(tmp_path), "sub")
    os.mkdir(subdir)
    async with LocalShellTool(
        mode="persistent",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        workdir=str(tmp_path),
    ) as tool:
        await tool.run(f"cd {subdir}")
        pwd = await tool.run("pwd")
        assert os.path.realpath(pwd.stdout.strip()) == os.path.realpath(str(tmp_path))


@pytest.mark.parametrize("failure", ["timeout", "unrecoverable_timeout", "overflow"])
async def test_persistent_queued_command_restarts_after_session_recovery(failure: str) -> None:
    is_timeout = failure != "overflow"
    if sys.platform == "win32":
        command = (
            "[System.Threading.Thread]::Sleep(30000)"
            if is_timeout
            else "while ($true) { [Console]::Write('overflow') }"
        )
        followup = "Write-Output recovered"
    else:
        command = "trap '' INT; sleep 30" if is_timeout else "while :; do printf 'overflow'; done"
        followup = "printf 'recovered'"

    async with LocalShellTool(
        mode="persistent",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        max_output_bytes=128,
    ) as tool:
        session = tool._session
        assert session is not None
        original_process = session._proc
        assert original_process is not None
        # Keep the real interrupt case, and separately guarantee an
        # unrecoverable timeout: PowerShell may emit its finally sentinel on
        # CTRL_BREAK. Only suppress the graceful signal in this extra case;
        # process shutdown and restart still use real subprocesses.
        interrupt = (
            patch.object(session, "_interrupt_current_command", new=AsyncMock())
            if failure == "unrecoverable_timeout"
            else nullcontext()
        )
        with interrupt:
            failed, recovered = await asyncio.gather(
                tool.run(command, timeout=0.5 if is_timeout else 10.0),
                tool.run(followup, timeout=10.0),
                return_exceptions=True,
            )
        assert original_process.returncode is not None
        assert session._proc is not original_process

    assert isinstance(failed, ShellResult)
    assert failed.timed_out if is_timeout else failed.truncated
    assert isinstance(recovered, ShellResult), recovered
    assert recovered.stdout.strip() == "recovered"
    assert recovered.exit_code == 0


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX inherited-pipe regression")
async def test_persistent_restart_cancels_readers_from_exited_shell(tmp_path: Path) -> None:
    from agent_framework_tools.shell._session import ShellSession

    release_child = tmp_path / "release-child"
    release_followup = tmp_path / "release-followup"

    class ExitWithInheritedPipes(ShellSession):
        def _build_script(self, command: str, sentinel: str) -> str:
            if command == "exit-with-child":
                # Keep stdout alive beyond the parent shell's exit. The child
                # is released only after the replacement shell starts.
                return (
                    f"(while [ ! -e {shlex.quote(str(release_child))} ]; do sleep 0.01; done; "
                    "printf stale-child-output) & "
                    f"printf '\\n{sentinel}_0\\n'; exit 0\n"
                )
            return super()._build_script(command, sentinel)

    async with ExitWithInheritedPipes(["/bin/sh"]) as session:
        original_process = session._proc
        original_reader = session._stdout_reader
        assert original_process is not None
        assert original_reader is not None
        followup: asyncio.Task[ShellResult] | None = None
        try:
            first = await session.run("exit-with-child", timeout=10.0)
            assert first.exit_code == 0

            async def wait_for_exit() -> None:
                while original_process.returncode is None:  # noqa: ASYNC110 - wait() also waits for the inherited pipes
                    await asyncio.sleep(0)

            await asyncio.wait_for(wait_for_exit(), timeout=10.0)
            assert not original_reader.done()
            followup = asyncio.create_task(
                session.run(
                    f"printf started; while [ ! -e {shlex.quote(str(release_followup))} ]; "
                    "do sleep 0.01; done; printf recovered",
                    timeout=10.0,
                )
            )

            async def wait_for_replacement() -> None:
                while session._proc is original_process or b"started" not in session._stdout_buf:  # noqa: ASYNC110
                    await asyncio.sleep(0)

            await asyncio.wait_for(wait_for_replacement(), timeout=10.0)
            release_child.touch()

            await asyncio.wait_for(asyncio.gather(original_reader, return_exceptions=True), timeout=10.0)
            release_followup.touch()
            result = await asyncio.wait_for(followup, timeout=10.0)
            assert result.stdout == "startedrecovered"
            assert result.exit_code == 0
            assert original_reader.cancelled()
        finally:
            release_child.touch()
            release_followup.touch()
            if followup is not None:
                followup.cancel()
                await asyncio.gather(followup, return_exceptions=True)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX subprocess simulates Windows recovery policy")
async def test_windows_timeout_sentinel_does_not_reuse_exiting_process() -> None:
    from agent_framework_tools.shell import _session
    from agent_framework_tools.shell._session import ShellSession

    class SentinelThenExit(ShellSession):
        def _build_script(self, command: str, sentinel: str) -> str:
            if command == "interrupt-me":
                # Real SIGINT flushes the completion marker, then waits for
                # one stdin line before exiting. This deterministically
                # models a marker preceding process exit: the next line
                # must be cleanup's exit, not the queued user command.
                return f"trap 'printf \"\\n{sentinel}_130\\n\"; read ignored; exit 130' INT; sleep 30\n"
            return super()._build_script(command, sentinel)

        async def _interrupt_current_command(self) -> None:
            assert self._proc is not None
            os.killpg(os.getpgid(self._proc.pid), signal.SIGINT)

        async def _run_locked(self, command: str, *, timeout: float | None) -> ShellResult:
            if command == "interrupt-me":
                # Exercise only the Windows recovery decision on this POSIX
                # runner; spawn, signal, pipes, readers and shutdown are real.
                with patch.object(_session, "sys", SimpleNamespace(platform="win32")):
                    return await super()._run_locked(command, timeout=timeout)
            return await super()._run_locked(command, timeout=timeout)

    async with SentinelThenExit(["/bin/sh"]) as session:
        original_process = session._proc
        assert original_process is not None
        first, followup = await asyncio.gather(
            session.run("interrupt-me", timeout=0.5),
            session.run("printf recovered", timeout=5),
            return_exceptions=True,
        )
        assert isinstance(first, ShellResult), first
        assert first.timed_out
        assert first.exit_code == 130
        assert isinstance(followup, ShellResult), followup
        assert followup.stdout == "recovered"
        assert followup.exit_code == 0
        assert original_process.returncode is not None
        assert session._proc is not original_process


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX graceful interrupt contract")
async def test_posix_graceful_timeout_preserves_shell_state() -> None:
    from agent_framework_tools.shell._session import ShellSession

    async with ShellSession(["/bin/sh"]) as session:
        original_process = session._proc
        first = await session.run("export RETAINED=value; trap ':' INT; sleep 30", timeout=0.5)
        assert first.timed_out
        followup = await session.run('printf "$RETAINED"', timeout=5)
        assert followup.stdout == "value"
        assert session._proc is original_process


@pytest.mark.parametrize("queue_during_close", [False, True])
async def test_persistent_close_rejects_queued_commands(queue_during_close: bool) -> None:
    if sys.platform == "win32":
        command = "[Console]::WriteLine('running'); [Console]::Out.Flush(); [System.Threading.Thread]::Sleep(30000)"
        followup = "Write-Output queued"
        reopened = "Write-Output reopened"
    else:
        command = "printf 'running\\n'; sleep 30"
        followup = "printf 'queued'"
        reopened = "printf 'reopened'"

    tool = LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True)
    await tool.start()
    session = tool._session
    assert session is not None
    tasks = [asyncio.create_task(tool.run(command, timeout=10.0))]
    try:

        async def wait_until_running() -> None:
            while b"running" not in session._stdout_buf:
                session._stdout_event.clear()
                await session._stdout_event.wait()

        await asyncio.wait_for(wait_until_running(), timeout=10.0)
        if not queue_during_close:
            tasks.append(asyncio.create_task(tool.run(followup, timeout=10.0)))
            await asyncio.sleep(0)

        closing = asyncio.create_task(tool.close())
        await asyncio.sleep(0)
        assert tool._get_session_lock().locked()
        if queue_during_close:
            tasks.append(asyncio.create_task(tool.run(followup, timeout=10.0)))
            await asyncio.sleep(0)

        await asyncio.wait_for(closing, timeout=10.0)
        _, queued = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=15.0)
        assert isinstance(queued, RuntimeError), queued
        assert tool._session is None
        assert session._proc is None

        result = await session.run(reopened, timeout=10.0)
        assert result.stdout.strip() == "reopened"
        assert result.exit_code == 0
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await tool.close()
        await session.close()


async def test_persistent_close_during_start_does_not_dispatch_command() -> None:
    tool = LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True)
    await tool.start()
    session = tool._session
    assert session is not None
    await tool.close()
    created = asyncio.Event()
    finish_start = asyncio.Event()
    create_process = asyncio.create_subprocess_exec

    async def delayed_create_process(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        proc = await create_process(*args, **kwargs)
        created.set()
        await finish_start.wait()
        return proc

    command = "Write-Output unexpected" if sys.platform == "win32" else "printf unexpected"
    tasks: list[asyncio.Task[Any]] = []
    try:
        with (
            patch("agent_framework_tools.shell._session.asyncio.create_subprocess_exec", delayed_create_process),
            patch.object(session, "_run_locked", wraps=session._run_locked) as run_command,
        ):
            tasks.append(asyncio.create_task(session.run(command, timeout=10.0)))
            await asyncio.wait_for(created.wait(), timeout=10.0)
            tasks.append(asyncio.create_task(session.close()))
            await asyncio.sleep(0)
            finish_start.set()
            result, _ = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10.0)

        assert isinstance(result, RuntimeError), result
        run_command.assert_not_awaited()
        assert session._proc is None
    finally:
        finish_start.set()
        await session.close()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell persistent reanchor test")
async def test_persistent_confines_workdir_by_default_powershell(tmp_path: os.PathLike[str]) -> None:
    """PowerShell counterpart of the POSIX confinement check."""
    subdir = os.path.join(str(tmp_path), "sub")
    os.mkdir(subdir)
    async with LocalShellTool(
        mode="persistent",
        approval_mode="never_require",
        acknowledge_unsafe=True,
        workdir=str(tmp_path),
    ) as tool:
        await tool.run(f"Set-Location -LiteralPath '{subdir}'")
        pwd = await tool.run("(Get-Location).Path")
        assert os.path.realpath(pwd.stdout.strip()) == os.path.realpath(str(tmp_path))
