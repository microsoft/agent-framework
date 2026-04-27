# Copyright (c) Microsoft. All rights reserved.

import os
import sys

import pytest

from agent_framework_tools.shell import LocalShellTool, ShellCommandError, ShellPolicy

pytestmark = pytest.mark.asyncio


async def test_stateless_echo() -> None:
    tool = LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True)
    cmd = "Write-Output hello" if sys.platform == "win32" else "echo hello"
    result = await tool.run(cmd)
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
    tool = LocalShellTool(mode="stateless", approval_mode="never_require", acknowledge_unsafe=True)
    with pytest.raises(ShellCommandError):
        await tool.run("rm -rf /")


async def test_allowlist_narrows_to_approved_commands() -> None:
    tool = LocalShellTool(
        mode="stateless",
        approval_mode="never_require", acknowledge_unsafe=True,
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
        approval_mode="never_require", acknowledge_unsafe=True,
        on_command=seen.append,
    )
    cmd = "Write-Output hi" if sys.platform == "win32" else "echo hi"
    await tool.run(cmd)
    assert seen == [cmd]


@pytest.mark.skipif(sys.platform == "win32", reason="persistent-mode sentinel on POSIX")
async def test_persistent_preserves_cwd_and_exports_across_calls(tmp_path: os.PathLike[str]) -> None:
    async with LocalShellTool(
        mode="persistent",
        approval_mode="never_require", acknowledge_unsafe=True,
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


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell-specific encoding")
async def test_persistent_powershell_utf8_roundtrip() -> None:
    """Non-ASCII output should round-trip without mojibake."""
    async with LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True) as tool:
        result = await tool.run("Write-Output 'café'")
        assert "café" in result.stdout


async def test_concurrent_first_calls_do_not_spawn_two_sessions() -> None:
    """Regression: startup must be serialised so two concurrent first callers
    don't each spawn their own subprocess."""
    import asyncio as _asyncio

    tool = LocalShellTool(mode="persistent", approval_mode="never_require", acknowledge_unsafe=True)
    try:
        cmd = (
            "Write-Output $PID" if sys.platform == "win32" else "echo $$"
        )
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
        approval_mode="never_require", acknowledge_unsafe=True,
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
