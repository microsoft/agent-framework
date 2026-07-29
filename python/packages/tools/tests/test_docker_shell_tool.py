# Copyright (c) Microsoft. All rights reserved.

"""Tests for DockerShellTool.

Argv-builder tests are pure-functional and run everywhere. Integration
tests that actually spawn containers are gated on
:func:`is_docker_available` and skipped otherwise (Docker is rarely
available in CI / dev sandboxes).
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Sequence
from typing import TypeAlias
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_framework_tools.shell import (
    DockerNotAvailableError,
    DockerShellTool,
    ShellCommandError,
    ShellExecutor,
    ShellResult,
    is_docker_available,
)
from agent_framework_tools.shell._docker import (
    build_exec_argv,
    build_run_argv,
)

_CommunicateOutcome: TypeAlias = tuple[bytes, bytes] | BaseException
_WaitOutcome: TypeAlias = int | None | BaseException


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
        self.stdout = object()
        self.stderr = object()
        self.killed = False
        self._communicate_results = list(communicate_results or [(b"", b"")])
        self._wait_results = list(wait_results or [returncode])

    async def communicate(self) -> tuple[bytes, bytes]:
        result = self._communicate_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        stdout, stderr = result
        return stdout, stderr

    async def wait(self) -> int | None:
        result = self._wait_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        self.returncode = result
        return result

    def kill(self) -> None:
        self.killed = True


def _docker_image_available(image: str) -> bool:
    if not is_docker_available():
        return False
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
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


def test_build_exec_argv_interactive():
    argv = build_exec_argv(binary="docker", container_name="c", interactive=True)
    assert argv == ["docker", "exec", "-i", "c", "bash", "--noprofile", "--norc"]


# --------------------------------------------------------------------- extra_run_args validation


@pytest.mark.parametrize(
    "extra",
    [
        ("--privileged",),
        ("--network=host",),
        ("--network", "host"),
        ("--net=host",),
        ("-v", "/:/host:rw"),
        ("--volume=/etc:/etc",),
        ("--cap-add=ALL",),
        ("--cap-add", "SYS_ADMIN"),
        ("--security-opt", "seccomp=unconfined"),
        ("--device", "/dev/kvm"),
        ("--pid=host",),
        ("--ipc=host",),
        ("--userns=host",),
        ("--user=0:0",),
        ("--read-only=false",),
        ("--tmpfs", "/var:rw"),
        ("--gpus", "all"),
        ("--add-host", "evil:1.2.3.4"),
        ("--label", "x=1", "--privileged"),  # mixed safe + unsafe
    ],
)
def test_dockershell_rejects_isolation_breaking_extra_run_args(extra):
    with pytest.raises(ValueError, match="isolation defaults"):
        DockerShellTool(extra_run_args=list(extra))


def test_dockershell_accepts_benign_extra_run_args():
    # Should not raise.
    DockerShellTool(extra_run_args=("--label", "team=af", "--name-suffix", "x"))


def test_build_exec_argv_non_interactive_appends_dash_c():
    argv = build_exec_argv(binary="docker", container_name="c", interactive=False)
    assert argv == ["docker", "exec", "-i", "c", "bash", "-c"]


# --------------------------------------------------------------------- DockerShellTool


def test_docker_shell_tool_validates_mode():
    with pytest.raises(ValueError, match="mode must be"):
        DockerShellTool(mode="bogus")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_docker_shell_tool_does_not_require_acknowledge_unsafe():
    """The container is the boundary; never_require should NOT raise."""
    # No exception means the security model is trusting the sandbox, as
    # advertised in the docstring.
    DockerShellTool(approval_mode="never_require")


def test_docker_shell_tool_generates_unique_container_names():
    a = DockerShellTool()
    b = DockerShellTool()
    assert a._container_name != b._container_name
    assert a._container_name.startswith("af-shell-")


def test_docker_shell_tool_implements_shell_executor_protocol():
    tool = DockerShellTool()
    assert isinstance(tool, ShellExecutor)


def test_as_function_carries_shell_kind():
    from agent_framework._tools import SHELL_TOOL_KIND_VALUE

    fn = DockerShellTool().as_function()
    # Approval mode flows through; tool is tagged as a shell tool.
    assert (
        getattr(fn, "additional_properties", {}).get("kind") == SHELL_TOOL_KIND_VALUE
        or getattr(fn, "kind", None) == SHELL_TOOL_KIND_VALUE
        or SHELL_TOOL_KIND_VALUE in str(getattr(fn, "_kind", ""))
    )


async def test_start_and_close_are_noops_in_stateless_mode() -> None:
    tool = DockerShellTool(mode="stateless")

    with (
        patch.object(tool, "_start_container", AsyncMock()) as start_container,
        patch.object(tool, "_stop_container", AsyncMock()) as stop_container,
    ):
        await tool.start()
        await tool.close()

    start_container.assert_not_called()
    stop_container.assert_not_called()


async def test_start_creates_and_reuses_persistent_session() -> None:
    tool = DockerShellTool(docker_binary="podman", shell="sh")
    session = AsyncMock()

    with (
        patch.object(tool, "_start_container", AsyncMock()) as start_container,
        patch("agent_framework_tools.shell._docker.ShellSession", return_value=session) as shell_session,
    ):
        await tool.start()
        await tool.start()

    start_container.assert_awaited_once()
    shell_session.assert_called_once_with(
        ["podman", "exec", "-i", tool._container_name, "sh"],
        workdir=None,
        env=None,
        max_output_bytes=tool._max_output_bytes,
    )
    assert session.start.await_count == 2


async def test_close_terminates_session_and_container() -> None:
    tool = DockerShellTool()
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
        policy=MagicMock(evaluate=MagicMock(return_value=MagicMock(decision="deny", reason="blocked")))
    )

    with pytest.raises(ShellCommandError, match="blocked"):
        await tool.run("danger")


async def test_run_logs_audit_hook_failures_and_executes_persistent_command(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken_hook(command: str) -> None:
        raise RuntimeError(f"boom:{command}")

    tool = DockerShellTool(on_command=broken_hook)
    tool._session = AsyncMock(run=AsyncMock(return_value=ShellResult("", "", 0, 1)))

    result = await tool.run("echo hi")

    assert result.exit_code == 0
    assert "on_command hook raised" in caplog.text
    tool._session.run.assert_awaited_once_with("echo hi", timeout=30.0)


async def test_run_raises_if_start_did_not_create_persistent_session() -> None:
    tool = DockerShellTool()

    with patch.object(tool, "start", AsyncMock()), pytest.raises(RuntimeError, match="session failed to start"):
        await tool.run("echo hi")


async def test_run_dispatches_to_private_stateless_runner() -> None:
    tool = DockerShellTool(mode="stateless")
    expected = ShellResult(stdout="ok", stderr="", exit_code=0, duration_ms=1)

    with patch.object(tool, "_run_stateless", AsyncMock(return_value=expected)) as run_stateless:
        result = await tool.run("echo hi", timeout=9.0)

    assert result is expected
    run_stateless.assert_awaited_once_with("echo hi", timeout=9.0)


async def test_run_stateless_builds_expected_argv() -> None:
    tool = DockerShellTool(
        mode="stateless",
        docker_binary="podman",
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
    assert argv[:4] == ("podman", "run", "--rm", "-i")
    assert "-v" in argv
    assert "/repo:/workspace:rw" in argv
    assert "AF_TEST=1" in argv
    assert argv[-4:] == ("alpine:3", "sh", "-c", "echo hi")
    assert result.stdout == "hello\n"
    assert result.stderr == "warning\n"
    assert result.exit_code == 3
    assert result.timed_out is False


async def test_run_stateless_timeout_reaps_container_when_kill_fails() -> None:
    tool = DockerShellTool(mode="stateless")
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
    tool = DockerShellTool(mode="stateless")
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
    tool = DockerShellTool()
    proc = _FakeProcess(returncode=0, communicate_results=[(b"abcdef1234567890\n", b"")])

    with (
        caplog.at_level("INFO", logger="agent_framework_tools.shell._docker"),
        patch("agent_framework_tools.shell._docker.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
    ):
        await tool._start_container()

    assert f"started docker container {tool._container_name}" in caplog.text


async def test_start_container_raises_when_runtime_fails() -> None:
    tool = DockerShellTool()
    proc = _FakeProcess(returncode=7, communicate_results=[(b"", b"daemon unavailable")])

    with (
        patch("agent_framework_tools.shell._docker.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
        pytest.raises(DockerNotAvailableError, match="daemon unavailable"),
    ):
        await tool._start_container()


async def test_stop_container_returns_after_first_success() -> None:
    tool = DockerShellTool()
    proc = _FakeProcess(returncode=0, communicate_results=[(b"", b"")])

    with patch("agent_framework_tools.shell._docker.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        await tool._stop_container()


async def test_stop_container_retries_when_first_attempt_fails() -> None:
    tool = DockerShellTool()
    first = _FakeProcess(returncode=1, communicate_results=[(b"", b"still running")])
    second = _FakeProcess(returncode=2, communicate_results=[(b"", b"still running")])

    with patch(
        "agent_framework_tools.shell._docker.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=[first, second]),
    ) as create_proc:
        await tool._stop_container()

    assert create_proc.await_count == 2


async def test_as_function_surfaces_command_errors() -> None:
    tool = DockerShellTool(mode="persistent")

    with patch.object(tool, "run", AsyncMock(side_effect=ShellCommandError("blocked"))):
        function = tool.as_function()
        assert function.func is not None
        result = await function.func("pwd")

    assert result == "blocked"
    assert "persistent session" in function.description


# --------------------------------------------------------------------- integration


@_skip_if_no_linux_docker
async def test_docker_persistent_session_preserves_state():
    async with DockerShellTool(image="alpine:3", shell="sh", network="none") as shell:
        r1 = await shell.run("export AF_X=hello")
        assert r1.exit_code == 0
        r2 = await shell.run("echo $AF_X")
        assert r2.exit_code == 0
        assert "hello" in r2.stdout


@_skip_if_no_linux_docker
async def test_docker_stateless_each_command_isolated():
    shell = DockerShellTool(mode="stateless", image="alpine:3", shell="sh", network="none")
    r1 = await shell.run("export AF_X=hello")
    assert r1 is not None  # noqa: S101
    r2 = await shell.run('echo "${AF_X:-unset}"')
    assert "unset" in r2.stdout


@_skip_if_no_linux_docker
async def test_docker_no_network_by_default():
    async with DockerShellTool(image="alpine:3", shell="sh") as shell:
        # busybox wget against a host that should be unreachable with --network none
        r = await shell.run("wget -q -T 2 -O- http://example.com || echo NOACCESS")
        assert "NOACCESS" in r.stdout
