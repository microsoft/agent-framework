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
import contextlib
import os
import signal
import subprocess  # noqa: S404  (executing user shell commands is the whole point)
import sys
import time
from collections.abc import Mapping, Sequence

from ._resolve import is_powershell
from ._types import ShellResult


def _truncate(data: bytes, cap: int) -> tuple[str, bool]:
    if len(data) <= cap:
        return data.decode("utf-8", errors="replace"), False
    # Keep the tail — most useful for tool output where the error message
    # tends to trail stdout.
    head = data[: cap // 2].decode("utf-8", errors="replace")
    tail = data[-cap // 2 :].decode("utf-8", errors="replace")
    return f"{head}\n[... truncated {len(data) - cap} bytes ...]\n{tail}", True


def _popen_kwargs_for_group() -> dict[str, object]:
    """Platform-specific process-group isolation so we can kill children too."""
    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP lets CTRL_BREAK_EVENT hit the whole group.
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}  # type: ignore[attr-defined]
    return {"start_new_session": True}


async def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        # Walk the tree via taskkill /T /F; falls back to direct kill.
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/T",
                "/F",
                "/PID",
                str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                killer.kill()
        except (FileNotFoundError, OSError):
            pass
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.kill()
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=2.0)
            return
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


async def run_stateless(
    argv: Sequence[str],
    command: str,
    *,
    workdir: str | None,
    env: Mapping[str, str] | None,
    timeout: float | None,
    max_output_bytes: int,
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
        max_output_bytes: Combined byte cap per stream before truncation.
    """
    # For PowerShell we prepend a UTF-8 encoding preamble so powershell.exe
    # on Windows (cp1252 by default) doesn't mojibake non-ASCII output.
    if is_powershell(argv):
        command = (
            "$OutputEncoding = [Console]::OutputEncoding = "
            "[System.Text.UTF8Encoding]::new($false); " + command
        )
    full_argv = [*argv, command]
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *full_argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
        env=dict(env) if env is not None else None,
        **_popen_kwargs_for_group(),  # type: ignore[arg-type]
    )

    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        timed_out = True
        await _kill_tree(proc)
        # Drain any queued output.
        try:
            stdout_bytes, stderr_bytes = await proc.communicate()
        except Exception:
            stdout_bytes, stderr_bytes = b"", b""

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_str, stdout_truncated = _truncate(stdout_bytes or b"", max_output_bytes)
    stderr_str, stderr_truncated = _truncate(stderr_bytes or b"", max_output_bytes)

    return ShellResult(
        stdout=stdout_str,
        stderr=stderr_str,
        exit_code=proc.returncode if proc.returncode is not None else -1,
        duration_ms=duration_ms,
        truncated=stdout_truncated or stderr_truncated,
        timed_out=timed_out,
    )
