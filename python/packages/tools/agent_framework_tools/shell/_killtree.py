# Copyright (c) Microsoft. All rights reserved.

"""Cross-OS process-tree termination.

Delegates to :mod:`psutil` for process introspection when available, with
a stdlib fallback. Tree-kill matters because a timed-out shell command can
spawn child processes (``make``, network tools, watchers, …); leaving
them running would defeat the timeout.

Notes:
* On Windows, ``taskkill.exe`` is resolved to its absolute system path so
  a modified ``PATH`` cannot redirect the call to a different binary.
* psutil's ``Process.children(recursive=True)`` walks parent-child
  relationships via OS APIs (``CreateToolhelp32Snapshot`` on Windows,
  ``/proc`` on Linux, ``proc_listpids`` on macOS), which is why it is
  preferred over a hand-rolled platform-conditional implementation.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

try:  # pragma: no cover - importable on every platform we ship
    import psutil

    _has_psutil = True
except ImportError:  # pragma: no cover
    _has_psutil = False
    psutil = None


_taskkill_path: str | None = None


def _resolve_taskkill() -> str:
    """Absolute path to taskkill.exe to defeat PATH poisoning."""
    global _taskkill_path
    if _taskkill_path is not None:
        return _taskkill_path
    system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"  # noqa: SIM112
    candidate = os.path.join(system_root, "System32", "taskkill.exe")
    _taskkill_path = candidate if os.path.isfile(candidate) else "taskkill"
    return _taskkill_path


async def kill_process_tree(
    proc: asyncio.subprocess.Process,
    *,
    grace: float = 2.0,
) -> None:
    """Terminate ``proc`` and all of its descendants. Best-effort, never raises."""
    if proc.returncode is not None:
        return
    if _has_psutil:
        await _kill_via_psutil(proc, grace=grace)
        return
    await _kill_via_stdlib(proc, grace=grace)


async def _kill_via_psutil(
    proc: asyncio.subprocess.Process,
    *,
    grace: float,
) -> None:
    if psutil is None:
        raise RuntimeError("_kill_via_psutil called without psutil available")
    try:
        parent = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        return
    try:
        descendants = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        descendants = []
    victims = [parent, *descendants]

    # Phase 1: SIGTERM (or terminate() on Windows, which also asks nicely).
    for v in victims:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            v.terminate()

    # Wait briefly for graceful exit.
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(proc.wait(), timeout=grace)

    # Phase 2: SIGKILL anything still alive.
    for v in victims:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            if v.is_running():
                v.kill()
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(proc.wait(), timeout=grace)


async def _kill_via_stdlib(
    proc: asyncio.subprocess.Process,
    *,
    grace: float,
) -> None:
    """Fallback when psutil isn't installed. Less robust on Windows."""
    if sys.platform == "win32":
        try:
            killer = await asyncio.create_subprocess_exec(
                _resolve_taskkill(),
                "/T",
                "/F",
                "/PID",
                str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(killer.wait(), timeout=grace)
            if killer.returncode is None:
                killer.kill()
        except (FileNotFoundError, OSError):
            pass
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.kill()
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=grace)
            return
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
