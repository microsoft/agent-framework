# Copyright (c) Microsoft. All rights reserved.

import sys
import tempfile

import pytest
from agent_framework import ShellTool

from agent_framework_shell_local import LocalShellExecutor


@pytest.fixture
def executor() -> LocalShellExecutor:
    return LocalShellExecutor()


async def test_local_shell_executor_basic_command(executor: LocalShellExecutor) -> None:
    result = await executor.execute("echo hello")

    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert not result.timed_out
    assert not result.truncated


async def test_local_shell_executor_failed_command(executor: LocalShellExecutor) -> None:
    if sys.platform == "win32":
        result = await executor.execute("cmd /c exit 1")
    else:
        result = await executor.execute("exit 1")

    assert result.exit_code != 0
    assert not result.timed_out


async def test_local_shell_executor_timeout(executor: LocalShellExecutor) -> None:
    if sys.platform == "win32":
        result = await executor.execute("ping -n 10 127.0.0.1", timeout_seconds=1)
    else:
        result = await executor.execute("sleep 10", timeout_seconds=1)

    assert result.timed_out


async def test_local_shell_executor_truncation(executor: LocalShellExecutor) -> None:
    if sys.platform == "win32":
        result = await executor.execute(
            "python -c \"print('x' * 1000)\"",
            max_output_bytes=100,
        )
    else:
        result = await executor.execute(
            "python3 -c \"print('x' * 1000)\"",
            max_output_bytes=100,
        )

    assert result.truncated
    assert len(result.stdout.encode("utf-8")) <= 100


async def test_local_shell_executor_working_directory(executor: LocalShellExecutor) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        if sys.platform == "win32":
            result = await executor.execute("cd", working_directory=tmpdir)
            # On Windows, compare using the temp directory base name to avoid short path issues
            tmpdir_basename = tmpdir.split("\\")[-1]
        else:
            result = await executor.execute("pwd", working_directory=tmpdir)
            tmpdir_basename = tmpdir.split("/")[-1]

        assert result.exit_code == 0
        assert tmpdir_basename in result.stdout


async def test_local_shell_executor_invalid_working_directory(executor: LocalShellExecutor) -> None:
    result = await executor.execute("echo hello", working_directory="/nonexistent/path/12345")

    assert result.exit_code == -1
    assert "Working directory does not exist" in result.stderr


async def test_local_shell_executor_stderr_captured(executor: LocalShellExecutor) -> None:
    if sys.platform == "win32":
        result = await executor.execute(
            "python -c \"import sys; sys.stderr.write('error\\n')\"",
            capture_stderr=True,
        )
    else:
        result = await executor.execute(
            "python3 -c \"import sys; sys.stderr.write('error\\n')\"",
            capture_stderr=True,
        )

    assert "error" in result.stderr


async def test_local_shell_executor_stderr_not_captured(executor: LocalShellExecutor) -> None:
    if sys.platform == "win32":
        result = await executor.execute(
            "python -c \"import sys; sys.stderr.write('error\\n')\"",
            capture_stderr=False,
        )
    else:
        result = await executor.execute(
            "python3 -c \"import sys; sys.stderr.write('error\\n')\"",
            capture_stderr=False,
        )

    assert result.stderr == ""


async def test_shell_tool_with_local_executor(executor: LocalShellExecutor) -> None:
    shell_tool = ShellTool(executor=executor)
    result = await shell_tool.execute("echo integration test")

    assert result.exit_code == 0
    assert "integration test" in result.stdout
