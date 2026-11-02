# Copyright (c) Microsoft. All rights reserved.

"""Stateless shell executor.

Each call to :func:`run_stateless` spawns a fresh subprocess, captures
stdout/stderr concurrently, enforces a timeout by killing the whole process
tree, and truncates oversized output. Matches the behaviour of AutoGen's
``LocalCommandLineCodeExecutor`` and OpenAI Agents SDK's ``local_shell``
protocol.
"""

from __future__ import annotations

import asyncio
import subprocess  # ruff:ignore[suspicious-subprocess-import]  # nosec B404 - executing user shell commands is the whole point
import sys
import time
from collections.abc import Mapping, Sequence

from ._capture import _ProcessOutput  # pyright: ignore[reportPrivateUsage] - shared shell capture
from ._killtree import kill_process_tree
from ._resolve import is_powershell
from ._truncate import _validate_output_limit  # pyright: ignore[reportPrivateUsage] - shared limit validation
from ._types import ShellResult


def _popen_kwargs_for_group() -> dict[str, object]:
    """Platform-specific process-group isolation so we can kill children too."""
    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP lets CTRL_BREAK_EVENT hit the whole group.
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


async def run_stateless(
    argv: Sequence[str],
    command: str,
    *,
    workdir: str | None,
    env: Mapping[str, str] | None,
    timeout: float | None,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> ShellResult:
    """Execute ``command`` via ``argv`` + ``-c``/``-Command`` + command.

    Args:
        argv: Base shell invocation (from :func:`resolve_shell` with
            ``interactive=False``).
        command: User command string.
        workdir: Working directory, or ``None`` to inherit.
        env: Environment variables, or ``None`` to inherit the current
            process environment.
        timeout: Seconds before the process tree is killed; ``None`` disables.
        max_stdout_bytes: Positive retained byte allowance for normal output.
        max_stderr_bytes: Positive retained byte allowance for error output.
    """
    _validate_output_limit(max_stdout_bytes, name="max_stdout_bytes")
    _validate_output_limit(max_stderr_bytes, name="max_stderr_bytes")
    # For PowerShell we prepend a UTF-8 encoding preamble so powershell.exe
    # on Windows (cp1252 by default) doesn't mojibake non-ASCII output.
    if is_powershell(argv):
        command = "$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); " + command
    full_argv = [*argv, command]
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *full_argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
        env=dict(env) if env is not None else None,
        **_popen_kwargs_for_group(),  # type: ignore[arg-type]
    )

    timed_out = False
    output = _ProcessOutput(proc, max_stdout_bytes=max_stdout_bytes, max_stderr_bytes=max_stderr_bytes)
    try:
        try:
            await output.wait(timeout)
        except asyncio.TimeoutError:
            timed_out = True
            await kill_process_tree(proc)
            await output.finish()
        except BaseException:
            await kill_process_tree(proc)
            raise
    finally:
        await output.close()

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_str, stdout_truncated = output.stdout.format()
    stderr_str, stderr_truncated = output.stderr.format()

    return ShellResult(
        stdout=stdout_str,
        stderr=stderr_str,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        duration_ms=duration_ms,
        truncated=stdout_truncated or stderr_truncated,
        timed_out=timed_out,
    )
