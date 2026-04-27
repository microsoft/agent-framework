# Copyright (c) Microsoft. All rights reserved.

"""Tests for DockerShellTool.

Argv-builder tests are pure-functional and run everywhere. Integration
tests that actually spawn containers are gated on
:func:`is_docker_available` and skipped otherwise (Docker is rarely
available in CI / dev sandboxes).
"""

from __future__ import annotations

import pytest

from agent_framework_tools.shell import (
    DockerShellTool,
    ShellExecutor,
    is_docker_available,
)
from agent_framework_tools.shell._docker import (
    build_exec_argv,
    build_run_argv,
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


def test_build_exec_argv_non_interactive_appends_dash_c():
    argv = build_exec_argv(binary="docker", container_name="c", interactive=False)
    assert argv == ["docker", "exec", "-i", "c", "bash", "-c"]


# --------------------------------------------------------------------- DockerShellTool


def test_docker_shell_tool_validates_mode():
    with pytest.raises(ValueError, match="mode must be"):
        DockerShellTool(mode="bogus")  # type: ignore[arg-type]


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
    assert getattr(fn, "additional_properties", {}).get("kind") == SHELL_TOOL_KIND_VALUE or \
        getattr(fn, "kind", None) == SHELL_TOOL_KIND_VALUE or \
        SHELL_TOOL_KIND_VALUE in str(getattr(fn, "_kind", ""))


# --------------------------------------------------------------------- integration


@pytest.mark.skipif(not is_docker_available(), reason="docker daemon unavailable")
async def test_docker_persistent_session_preserves_state():
    async with DockerShellTool(image="alpine:3", network="none") as shell:
        r1 = await shell.run("export AF_X=hello")
        assert r1.exit_code == 0
        r2 = await shell.run("echo $AF_X")
        assert r2.exit_code == 0
        assert "hello" in r2.stdout


@pytest.mark.skipif(not is_docker_available(), reason="docker daemon unavailable")
async def test_docker_stateless_each_command_isolated():
    shell = DockerShellTool(mode="stateless", image="alpine:3", network="none")
    r1 = await shell.run("export AF_X=hello")
    assert r1 is not None  # noqa: S101
    r2 = await shell.run('echo "${AF_X:-unset}"')
    assert "unset" in r2.stdout


@pytest.mark.skipif(not is_docker_available(), reason="docker daemon unavailable")
async def test_docker_no_network_by_default():
    async with DockerShellTool(image="alpine:3") as shell:
        # busybox wget against a host that should be unreachable with --network none
        r = await shell.run("wget -q -T 2 -O- http://example.com || echo NOACCESS")
        assert "NOACCESS" in r.stdout
