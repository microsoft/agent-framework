# Copyright (c) Microsoft. All rights reserved.

"""Tests for DockerShellTool.

Argv-builder tests are pure-functional and run everywhere. Integration
tests that actually spawn containers are gated on
:func:`is_docker_available` and skipped otherwise (Docker is rarely
available in CI / dev sandboxes).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TypeAlias, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_framework_tools._feature_usage import FeatureIndex
from agent_framework_tools.shell import (
    DockerNotAvailableError,
    DockerShellTool,
    ShellCommandError,
    ShellExecutor,
    ShellResult,
    is_docker_available,
)
from agent_framework_tools.shell._docker import build_exec_argv, build_run_argv
from agent_framework_tools.shell._resolve import find_executable

_CommunicateOutcome: TypeAlias = tuple[bytes, bytes] | BaseException
_WaitOutcome: TypeAlias = int | None | BaseException
_FakeWindowsHost: TypeAlias = Callable[[str, Iterable[str]], None]

_DOCKER = r"C:\Runtimes\docker.exe" if sys.platform == "win32" else "/usr/bin/docker"
_PODMAN = r"C:\Runtimes\podman.exe" if sys.platform == "win32" else "/usr/bin/podman"
_HOST_DOCKER = find_executable("docker") or ""
_CREATE_PROCESS = "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec"


class _FakeProcess:
    def __init__(
        self,
        *,
        pid: int = 1234,
        returncode: int | None = 0,
        communicate_results: Sequence[_CommunicateOutcome] | None = None,
        wait_results: Sequence[_WaitOutcome] | None = None,
    ) -> None:
        self.pid = pid
        self.returncode = returncode
        self._transport = MagicMock(spec=asyncio.SubprocessTransport)
        self.stdout_transport = MagicMock(spec=asyncio.ReadTransport)
        self.stderr_transport = MagicMock(spec=asyncio.ReadTransport)
        self._transport.get_pipe_transport.side_effect = {1: self.stdout_transport, 2: self.stderr_transport}.get
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.killed = False
        self._communicate_results = list(communicate_results or [(b"", b"")])
        first = self._communicate_results[0]
        self._wait_results = list(
            wait_results or ([first, returncode] if isinstance(first, BaseException) else [returncode])
        )
        output = next((item for item in self._communicate_results if isinstance(item, tuple)), (b"", b""))
        self.stdout.feed_data(output[0])
        self.stderr.feed_data(output[1])
        self.stdout.feed_eof()
        self.stderr.feed_eof()

    async def communicate(self) -> tuple[bytes, bytes]:
        result = self._communicate_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        stdout, stderr = result
        return stdout, stderr

    async def wait(self) -> int | None:
        result = self._wait_results.pop(0) if self._wait_results else self.returncode
        if isinstance(result, BaseException):
            raise result
        self.returncode = result
        return result

    def kill(self) -> None:
        self.killed = True


def _docker_image_available(image: str) -> bool:
    if not _HOST_DOCKER or not is_docker_available(_HOST_DOCKER):
        return False
    try:
        result = subprocess.run(
            [_HOST_DOCKER, "image", "inspect", image],
            capture_output=True,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


# Integration tests use Linux container images (alpine) that don't run
# under Docker Desktop's default Windows-container mode.
_skip_if_no_linux_docker = pytest.mark.skipif(
    not _docker_image_available("alpine:3") or sys.platform == "win32",
    reason="docker daemon unavailable, alpine:3 image missing, or running Windows containers",
)

# --------------------------------------------------------------------- argv builders


def test_build_run_argv_minimal_defaults():
    argv = build_run_argv(
        binary="docker",
        image="ubuntu:24.04",
        container_name="af-shell-test",
        user="65534:65534",
        network="none",
        memory="512m",
        pids_limit=256,
        workdir="/workspace",
        host_workdir=None,
        mount_readonly=True,
        read_only_root=True,
        extra_env=None,
        extra_args=None,
    )
    assert argv[0] == "docker"
    assert argv[1] == "run"
    assert "-d" in argv
    assert "--rm" in argv
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--user" in argv and argv[argv.index("--user") + 1] == "65534:65534"
    assert "--cap-drop" in argv and argv[argv.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges" in argv
    assert "--read-only" in argv
    # Image and the trailing sleep are last.
    assert argv[-3:] == ["ubuntu:24.04", "sleep", "infinity"]


def test_build_run_argv_with_host_workdir_readonly():
    argv = build_run_argv(
        binary="docker",
        image="img",
        container_name="x",
        user="u",
        network="none",
        memory="1g",
        pids_limit=64,
        workdir="/work",
        host_workdir="/tmp/host",
        mount_readonly=True,
        read_only_root=True,
        extra_env=None,
        extra_args=None,
    )
    assert "-v" in argv
    mount = argv[argv.index("-v") + 1]
    assert mount == "/tmp/host:/work:ro"


def test_build_run_argv_with_host_workdir_writable():
    argv = build_run_argv(
        binary="docker",
        image="img",
        container_name="x",
        user="u",
        network="none",
        memory="1g",
        pids_limit=64,
        workdir="/work",
        host_workdir="/data",
        mount_readonly=False,
        read_only_root=False,
        extra_env=None,
        extra_args=None,
    )
    mount = argv[argv.index("-v") + 1]
    assert mount == "/data:/work:rw"
    assert "--read-only" not in argv


def test_build_run_argv_passes_extra_env_and_args():
    argv = build_run_argv(
        binary="podman",
        image="alpine",
        container_name="c",
        user="0:0",
        network="bridge",
        memory="64m",
        pids_limit=16,
        workdir="/w",
        host_workdir=None,
        mount_readonly=True,
        read_only_root=True,
        extra_env={"FOO": "bar", "X": "y z"},
        extra_args=("--label", "team=af"),
    )
    assert argv[0] == "podman"
    assert "-e" in argv
    # Both env vars present.
    env_pairs = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    assert "FOO=bar" in env_pairs
    assert "X=y z" in env_pairs
    # Extra args land before image+sleep.
    image_idx = argv.index("alpine")
    assert "--label" in argv[:image_idx]
    assert "team=af" in argv[:image_idx]
    # ...and after every enforced isolation default, so docker's last-flag-wins
    # never lets an extra arg be overridden by one of the tool's own flags.
    assert argv.index("--label") > max(
        argv.index(flag)
        for flag in ("--user", "--network", "--memory", "--pids-limit", "--cap-drop", "--security-opt", "--read-only")
    )


def test_build_exec_argv_interactive():
    argv = build_exec_argv(binary="docker", container_name="c", interactive=True)
    assert argv == ["docker", "exec", "-i", "c", "bash", "--noprofile", "--norc"]


# --------------------------------------------------------------------- unsafe_extra_run_args validation


@pytest.mark.parametrize("token", [None, 42])
def test_dockershell_rejects_non_string_unsafe_extra_run_args(token):
    with pytest.raises(ValueError, match="unsafe_extra_run_args contains a non-string token"):
        DockerShellTool(docker_binary=_DOCKER, unsafe_extra_run_args=[token])  # type: ignore[list-item]


def test_dockershell_snapshots_unsafe_extra_run_args():
    unsafe = ["--network", "host"]
    unsafe_tool = DockerShellTool(docker_binary=_DOCKER, unsafe_extra_run_args=unsafe)
    unsafe.append("--privileged")
    assert unsafe_tool._unsafe_extra_run_args == ("--network", "host")


def test_build_exec_argv_non_interactive_appends_dash_c():
    argv = build_exec_argv(binary="docker", container_name="c", interactive=False)
    assert argv == ["docker", "exec", "-i", "c", "bash", "-c"]


# --------------------------------------------------------------------- DockerShellTool


def test_docker_shell_tool_validates_mode():
    with pytest.raises(ValueError, match="mode must be"):
        DockerShellTool(docker_binary=_DOCKER, mode="bogus")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_docker_shell_tool_does_not_require_acknowledge_unsafe():
    """The container is the boundary; never_require should NOT raise."""
    # No exception means the security model is trusting the sandbox, as
    # advertised in the docstring.
    DockerShellTool(docker_binary=_DOCKER, approval_mode="never_require")


def test_docker_shell_tool_generates_unique_container_names():
    a = DockerShellTool(docker_binary=_DOCKER)
    b = DockerShellTool(docker_binary=_DOCKER)
    assert a._container_name != b._container_name
    assert a._container_name.startswith("af-shell-")


def test_docker_shell_tool_implements_shell_executor_protocol():
    tool = DockerShellTool(docker_binary=_DOCKER)
    assert isinstance(tool, ShellExecutor)


def test_as_function_carries_shell_kind():
    from agent_framework._tools import SHELL_TOOL_KIND_VALUE

    fn = DockerShellTool(docker_binary=_DOCKER).as_function()
    # Approval mode flows through; tool is tagged as a shell tool.
    assert (
        getattr(fn, "additional_properties", {}).get("kind") == SHELL_TOOL_KIND_VALUE
        or getattr(fn, "kind", None) == SHELL_TOOL_KIND_VALUE
        or SHELL_TOOL_KIND_VALUE in str(getattr(fn, "_kind", ""))
    )


async def test_as_function_preserves_structured_shell_result() -> None:
    shell_result = ShellResult(
        stdout="container output",
        stderr="container error",
        exit_code=7,
        duration_ms=25,
    )
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")

    with patch.object(tool, "run", AsyncMock(return_value=shell_result)):
        function = tool.as_function()
        result = await function.invoke(arguments={"command": "ignored"})
        raw_result = await function.invoke(arguments={"command": "ignored"}, skip_parsing=True)

    assert len(result) == 1
    assert result[0].type == "text"
    assert result[0].text == shell_result.format_for_model()
    assert result[0].additional_properties == {
        "stdout": "container output",
        "stderr": "container error",
        "exit_code": 7,
        "truncated": False,
        "timed_out": False,
    }
    assert isinstance(raw_result, str)
    assert raw_result == shell_result.format_for_model()
    assert json.loads(json.dumps(raw_result)) == shell_result.format_for_model()


async def test_start_and_close_are_noops_in_stateless_mode() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")

    with (
        patch.object(tool, "_start_container", AsyncMock()) as start_container,
        patch.object(tool, "_stop_container", AsyncMock()) as stop_container,
    ):
        await tool.start()
        await tool.close()

    start_container.assert_not_called()
    stop_container.assert_not_called()


async def test_start_creates_and_reuses_persistent_session() -> None:
    tool = DockerShellTool(docker_binary=_PODMAN, shell="sh", max_stdout_bytes=1024, max_stderr_bytes=2048)
    session = AsyncMock()

    with (
        patch.object(tool, "_start_container", AsyncMock()) as start_container,
        patch("agent_framework_tools.shell._docker.ShellSession", return_value=session) as shell_session,
    ):
        await tool.start()
        await tool.start()

    start_container.assert_awaited_once()
    shell_session.assert_called_once_with(
        [_PODMAN, "exec", "-i", tool._container_name, "sh"],
        workdir=None,
        env=None,
        max_stdout_bytes=1024,
        max_stderr_bytes=2048,
    )
    assert session.start.await_count == 2


async def test_start_container_passes_unsafe_extra_run_args_verbatim() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, unsafe_extra_run_args=("--network", "host"))
    proc = _FakeProcess(returncode=0)

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ) as create_proc:
        await tool._start_container()

    assert create_proc.await_args is not None
    argv = create_proc.await_args.args
    assert argv[argv.index("--network", argv.index("--network") + 1) + 1] == "host"


async def test_close_terminates_session_and_container() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER)
    tool._container_started = True
    session = AsyncMock()
    tool._session = session

    with patch.object(tool, "_stop_container", AsyncMock()) as stop_container:
        await tool.close()

    session.close.assert_awaited_once()
    stop_container.assert_awaited_once()
    assert tool._session is None
    assert tool._container_started is False


async def test_run_rejects_denied_commands() -> None:
    tool = DockerShellTool(
        docker_binary=_DOCKER,
        policy=MagicMock(evaluate=MagicMock(return_value=MagicMock(decision="deny", reason="blocked"))),
    )

    with pytest.raises(ShellCommandError, match="blocked"):
        await tool.run("danger")


async def test_run_logs_audit_hook_failures_and_executes_persistent_command(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken_hook(command: str) -> None:
        raise RuntimeError(f"boom:{command}")

    tool = DockerShellTool(docker_binary=_DOCKER, on_command=broken_hook)
    tool._session = AsyncMock(run=AsyncMock(return_value=ShellResult("", "", 0, 1)))

    result = await tool.run("echo hi")

    assert result.exit_code == 0
    assert "on_command hook raised" in caplog.text
    tool._session.run.assert_awaited_once_with("echo hi", timeout=30.0)


async def test_run_raises_if_start_did_not_create_persistent_session() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER)

    with patch.object(tool, "start", AsyncMock()), pytest.raises(RuntimeError, match="session failed to start"):
        await tool.run("echo hi")


async def test_run_dispatches_to_private_stateless_runner() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")
    expected = ShellResult(stdout="ok", stderr="", exit_code=0, duration_ms=1)

    with (
        patch.object(tool, "_run_stateless", AsyncMock(return_value=expected)) as run_stateless,
        patch("agent_framework_tools.shell._docker.mark_feature_used") as mark_feature_used,
    ):
        result = await tool.run("echo hi", timeout=9.0)

    assert result is expected
    mark_feature_used.assert_called_once_with(FeatureIndex.TOOLS_SHELL)
    run_stateless.assert_awaited_once_with("echo hi", timeout=9.0)


async def test_run_stateless_builds_expected_argv() -> None:
    tool = DockerShellTool(
        docker_binary=_PODMAN,
        mode="stateless",
        image="alpine:3",
        shell="sh",
        host_workdir="/repo",
        workdir="/workspace",
        mount_readonly=False,
        env={"AF_TEST": "1"},
    )
    proc = _FakeProcess(returncode=3, communicate_results=[(b"hello\n", b"warning\n")])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ) as create_proc:
        result = await tool._run_stateless("echo hi", timeout=12.0)

    assert create_proc.await_args is not None
    argv = create_proc.await_args.args
    assert argv[:4] == (_PODMAN, "run", "--rm", "-i")
    assert "-v" in argv
    assert "/repo:/workspace:rw" in argv
    assert "AF_TEST=1" in argv
    assert argv[-4:] == ("alpine:3", "sh", "-c", "echo hi")
    assert result.stdout == "hello\n"
    assert result.stderr == "warning\n"
    assert result.exit_code == 3
    assert result.timed_out is False


@pytest.mark.parametrize(("max_stdout_bytes", "max_stderr_bytes"), [(17, 33), (33, 17)])
async def test_docker_stateless_bounds_both_host_output_buffers(
    max_stdout_bytes: int, max_stderr_bytes: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_framework_tools.shell._truncate import _OutputBuffer, truncate_head_tail

    append = _OutputBuffer.append
    observed: list[int] = []

    def checked_append(self: _OutputBuffer, data: bytes) -> None:
        append(self, data)
        retained = len(self._head) + len(self._tail)
        assert self._cap in (max_stdout_bytes, max_stderr_bytes)
        assert retained <= self._cap
        observed.append(retained)

    monkeypatch.setattr(_OutputBuffer, "append", checked_append)
    tool = DockerShellTool(
        docker_binary=_DOCKER, mode="stateless", max_stdout_bytes=max_stdout_bytes, max_stderr_bytes=max_stderr_bytes
    )
    proc = _FakeProcess(communicate_results=[(b"a" * 65536, b"b" * 65536)])
    with patch("agent_framework_tools.shell._docker.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await tool.run("unused")
    assert result.truncated and result.exit_code == 0
    assert result.stdout == truncate_head_tail(b"a" * 65536, max_stdout_bytes)[0]
    assert result.stderr == truncate_head_tail(b"b" * 65536, max_stderr_bytes)[0]
    assert observed


@pytest.mark.parametrize("failure", ["cancel", "reader"])
async def test_docker_stateless_failure_stops_container_and_local_client(failure: str) -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")
    proc = _FakeProcess(returncode=None)
    killer = _FakeProcess()
    waiting = asyncio.Event()

    async def wait() -> int:
        waiting.set()
        await asyncio.Event().wait()
        return 0

    if failure == "reader":
        proc.stderr.set_exception(OSError("pipe failed"))
    with (
        patch.object(proc, "wait", wait),
        patch(
            "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=[proc, killer]),
        ) as create_process,
    ):
        task = asyncio.create_task(tool.run("unused", timeout=5))
        await waiting.wait()
        if failure == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(OSError, match="pipe failed"):
                await task
    assert proc.killed
    proc.stdout_transport.close.assert_called()
    proc.stderr_transport.close.assert_called()
    assert create_process.await_count == 2
    assert create_process.await_args_list[1].args[1:4] == ("kill", "--signal", "KILL")


@pytest.mark.parametrize("cap", [0, -1])
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_docker_rejects_invalid_output_limit_before_execution(cap: int, stream: str) -> None:
    with pytest.raises(ValueError, match=f"max_{stream}_bytes must be positive"):
        DockerShellTool(
            docker_binary=_DOCKER,
            max_stdout_bytes=cap if stream == "stdout" else 1024,
            max_stderr_bytes=cap if stream == "stderr" else 1024,
        )


async def test_docker_cleanup_reader_failure_stops_cleanup_process() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")
    proc = _FakeProcess(returncode=None, wait_results=[asyncio.TimeoutError()])
    killer = _FakeProcess(returncode=1)
    reaper = _FakeProcess(returncode=None)
    reaper.stderr.set_exception(OSError("cleanup pipe failed"))
    with (
        patch(
            "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=[proc, killer, reaper]),
        ),
        pytest.raises(OSError, match="cleanup pipe failed"),
    ):
        await tool.run("unused", timeout=5)
    assert reaper.killed and proc.killed


@pytest.mark.parametrize("cleanup_command", ["kill", "rm"])
async def test_docker_cancellation_stops_cleanup_process(cleanup_command: str) -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")
    proc = _FakeProcess(returncode=None, wait_results=[asyncio.TimeoutError()])
    cleanup = _FakeProcess(returncode=None)
    waiting = asyncio.Event()

    async def wait() -> int:
        waiting.set()
        await asyncio.Event().wait()
        return 0

    processes = [proc, cleanup] if cleanup_command == "kill" else [proc, _FakeProcess(returncode=1), cleanup]
    with (
        patch.object(cleanup, "wait", wait),
        patch(
            "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
            AsyncMock(side_effect=processes),
        ),
    ):
        task = asyncio.create_task(tool.run("unused", timeout=5))
        await waiting.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert cleanup.killed and proc.killed


async def test_run_stateless_places_unsafe_extra_args_after_isolation_defaults() -> None:
    tool = DockerShellTool(
        docker_binary=_DOCKER,
        mode="stateless",
        image="alpine:3",
        shell="sh",
        unsafe_extra_run_args=("--label", "team=af"),
    )
    proc = _FakeProcess(returncode=0, communicate_results=[(b"", b"")])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ) as create_proc:
        await tool._run_stateless("echo hi", timeout=5.0)

    assert create_proc.await_args is not None
    argv = create_proc.await_args.args
    assert argv[-4:] == ("alpine:3", "sh", "-c", "echo hi")
    assert argv.index("--label") > max(
        argv.index(flag)
        for flag in ("--user", "--network", "--memory", "--pids-limit", "--cap-drop", "--security-opt", "--read-only")
    )
    assert argv.index("--label") < argv.index("alpine:3")


async def test_run_stateless_passes_unsafe_extra_run_args_verbatim() -> None:
    tool = DockerShellTool(
        docker_binary=_DOCKER,
        mode="stateless",
        image="alpine:3",
        shell="sh",
        unsafe_extra_run_args=("--entrypoint", "/bin/custom"),
    )
    proc = _FakeProcess(returncode=0, communicate_results=[(b"", b"")])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ) as create_proc:
        await tool._run_stateless("echo hi", timeout=5.0)

    assert create_proc.await_args is not None
    argv = create_proc.await_args.args
    assert argv[argv.index("--entrypoint") + 1] == "/bin/custom"
    assert argv.index("--entrypoint") < argv.index("alpine:3")


async def test_run_stateless_timeout_reaps_container_when_kill_fails() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")
    command_proc = _FakeProcess(
        returncode=137,
        communicate_results=[asyncio.TimeoutError(), (b"after-timeout", b"stderr")],
    )
    killer = _FakeProcess(returncode=1)
    reaper = _FakeProcess(returncode=9, communicate_results=[(b"", b"rm failed")])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=[command_proc, killer, reaper]),
    ):
        result = await tool._run_stateless("sleep 5", timeout=0.01)

    assert result.timed_out is True
    assert result.exit_code == 137
    assert result.stdout == "after-timeout"
    assert result.stderr == "stderr"


async def test_run_stateless_timeout_handles_kill_and_reaper_timeouts() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")
    command_proc = _FakeProcess(
        returncode=None,
        communicate_results=[asyncio.TimeoutError(), RuntimeError("drain failed")],
    )
    killer = _FakeProcess(returncode=None, wait_results=[asyncio.TimeoutError()])
    reaper = _FakeProcess(returncode=None, communicate_results=[asyncio.TimeoutError()])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=[command_proc, killer, reaper]),
    ):
        result = await tool._run_stateless("sleep 5", timeout=0.01)

    assert killer.killed is True
    assert reaper.killed is True
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.stdout == ""
    assert result.stderr == ""


async def test_start_container_success_logs_container_id(caplog: pytest.LogCaptureFixture) -> None:
    tool = DockerShellTool(docker_binary=_DOCKER)
    proc = _FakeProcess(returncode=0, communicate_results=[(b"abcdef1234567890\n", b"")])

    with (
        caplog.at_level("INFO", logger="agent_framework_tools.shell._docker"),
        patch("agent_framework_tools.shell._docker.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
    ):
        await tool._start_container()

    assert f"started docker container {tool._container_name}" in caplog.text


async def test_start_container_raises_when_runtime_fails() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER)
    proc = _FakeProcess(returncode=7, communicate_results=[(b"", b"daemon unavailable")])

    with (
        patch("agent_framework_tools.shell._docker.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
        pytest.raises(DockerNotAvailableError, match="daemon unavailable"),
    ):
        await tool._start_container()


async def test_stop_container_returns_after_first_success() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER)
    proc = _FakeProcess(returncode=0, communicate_results=[(b"", b"")])

    with patch("agent_framework_tools.shell._docker.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        await tool._stop_container()


async def test_stop_container_retries_when_first_attempt_fails() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER)
    first = _FakeProcess(returncode=1, communicate_results=[(b"", b"still running")])
    second = _FakeProcess(returncode=2, communicate_results=[(b"", b"still running")])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=[first, second]),
    ) as create_proc:
        await tool._stop_container()

    assert create_proc.await_count == 2


async def test_as_function_surfaces_command_errors() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="persistent")

    with patch.object(tool, "run", AsyncMock(side_effect=ShellCommandError("blocked"))):
        function = tool.as_function()
        assert function.func is not None
        result = await function.func("pwd")

    assert result == "blocked"
    assert "persistent session" in function.description


# --------------------------------------------------------------------- runtime path


@pytest.mark.parametrize("docker_binary", ["docker", "podman", "bin/docker", "./docker"])
def test_docker_binary_must_be_a_full_path_on_posix(monkeypatch: pytest.MonkeyPatch, docker_binary: str) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(ValueError, match="docker_binary must be a full path"):
        DockerShellTool(docker_binary=docker_binary)


@pytest.mark.parametrize(
    "docker_binary",
    ["docker", "docker.exe", r"bin\docker.exe", r".\docker.exe", "C:docker.exe", r"\docker.exe", r"C:\Runtimes\docker"],
)
def test_docker_binary_must_be_a_full_path_with_an_extension_on_windows(
    fake_windows_host: _FakeWindowsHost, docker_binary: str
) -> None:
    fake_windows_host(r"C:\Runtimes", {r"C:\Runtimes\docker.exe", r".\docker.exe", "docker.exe"})

    with pytest.raises(ValueError, match="docker_binary must be a full path"):
        DockerShellTool(docker_binary=docker_binary)


async def test_persistent_lifecycle_launches_the_configured_runtime() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER)
    started = _FakeProcess(returncode=0, communicate_results=[(b"abcdef123456\n", b"")])
    stopped = _FakeProcess(returncode=0, communicate_results=[(b"", b"")])

    with (
        patch(_CREATE_PROCESS, AsyncMock(side_effect=[started, stopped])) as create_proc,
        patch("agent_framework_tools.shell._docker.ShellSession", return_value=AsyncMock()) as shell_session,
    ):
        await tool.start()
        await tool.close()

    assert [call.args[:2] for call in create_proc.await_args_list] == [(_DOCKER, "run"), (_DOCKER, "rm")]
    assert shell_session.call_args.args[0][:2] == [_DOCKER, "exec"]


async def test_stateless_cleanup_launches_the_configured_runtime() -> None:
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless")
    victim = _FakeProcess(returncode=None)
    killer = _FakeProcess(returncode=1)
    reaper = _FakeProcess(returncode=0)

    with patch(_CREATE_PROCESS, AsyncMock(side_effect=[killer, reaper])) as create_proc:
        await tool._terminate_stateless(cast(asyncio.subprocess.Process, victim), "af-shell-test")

    assert [call.args[:2] for call in create_proc.await_args_list] == [(_DOCKER, "kill"), (_DOCKER, "rm")]
    assert victim.killed


def test_is_docker_available_runs_the_given_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "docker.exe"
    runtime.write_text("")
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"27.0.1\n", stderr=b"")

    with patch("agent_framework_tools.shell._docker.subprocess.run", return_value=completed) as run:
        assert is_docker_available(str(runtime)) is True

    assert run.call_args.args[0][0] == str(runtime)


@pytest.mark.parametrize("binary", ["docker", "docker.exe", "./docker.exe"])
def test_is_docker_available_is_false_for_a_short_name_or_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, binary: str
) -> None:
    (tmp_path / "docker").write_text("")
    (tmp_path / "docker.exe").write_text("")
    monkeypatch.chdir(tmp_path)

    with patch("agent_framework_tools.shell._docker.subprocess.run") as run:
        assert is_docker_available(binary) is False

    run.assert_not_called()


def test_is_docker_available_is_false_when_the_runtime_does_not_exist(tmp_path: Path) -> None:
    with patch("agent_framework_tools.shell._docker.subprocess.run") as run:
        assert is_docker_available(str(tmp_path / "docker.exe")) is False

    run.assert_not_called()


# --------------------------------------------------------------------- integration


@_skip_if_no_linux_docker
async def test_docker_persistent_session_preserves_state():
    async with DockerShellTool(docker_binary=_HOST_DOCKER, image="alpine:3", shell="sh", network="none") as shell:
        r1 = await shell.run("export AF_X=hello")
        assert r1.exit_code == 0
        r2 = await shell.run("echo $AF_X")
        assert r2.exit_code == 0
        assert "hello" in r2.stdout


@_skip_if_no_linux_docker
async def test_docker_stateless_each_command_isolated():
    shell = DockerShellTool(docker_binary=_HOST_DOCKER, mode="stateless", image="alpine:3", shell="sh", network="none")
    r1 = await shell.run("export AF_X=hello")
    assert r1 is not None  # noqa: S101
    r2 = await shell.run('echo "${AF_X:-unset}"')
    assert "unset" in r2.stdout


@_skip_if_no_linux_docker
async def test_docker_no_network_by_default():
    async with DockerShellTool(docker_binary=_HOST_DOCKER, image="alpine:3", shell="sh") as shell:
        # busybox wget against a host that should be unreachable with --network none
        r = await shell.run("wget -q -T 2 -O- http://example.com || echo NOACCESS")
        assert "NOACCESS" in r.stdout


async def test_run_stateless_sets_stdin_to_devnull() -> None:
    """Regression: stateless Docker spawns must not inherit host stdin.

    Without stdin=DEVNULL, `docker run -i` forwards the host's stdin into the
    container. Combined with model-chosen commands that read stdin (e.g., `cat`),
    this causes the same input theft/hang bug as the local tool.

    This test asserts the spawn is given stdin=DEVNULL by inspecting the
    asyncio.create_subprocess_exec call.
    """
    tool = DockerShellTool(docker_binary=_DOCKER, mode="stateless", image="alpine:3", shell="sh")
    proc = _FakeProcess(returncode=0, communicate_results=[(b"", b"")])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(return_value=proc),
    ) as create_proc:
        await tool._run_stateless("echo hi", timeout=5.0)

    assert create_proc.await_args is not None
    kwargs = create_proc.await_args.kwargs
    assert kwargs.get("stdin") == asyncio.subprocess.DEVNULL, f"Expected stdin=DEVNULL, got {kwargs.get('stdin')!r}"
