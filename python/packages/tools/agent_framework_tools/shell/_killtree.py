# Copyright (c) Microsoft. All rights reserved.

"""Cross-OS process-tree termination.

Delegates to :mod:`psutil` (battle-tested across Windows/macOS/Linux for
process introspection) when available, with a stdlib fallback. Tree-kill
matters because a timed-out shell command can spawn arbitrary child
processes (`make`, network tools, watchers, …) and leaving them running
defeats the purpose of the timeout as a safety mechanism.

Security notes:

* On Windows we resolve ``taskkill.exe`` to its absolute system path so a
  PATH-poisoned environment cannot redirect us to an attacker-supplied
  binary.
* psutil's ``Process.children(recursive=True)`` walks the parent-child
  relationships via the OS APIs (``CreateToolhelp32Snapshot`` on Windows,
  ``/proc`` on Linux, ``proc_listpids`` on macOS) — which is why we
  prefer it over our own platform-conditional code.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys

try:  # pragma: no cover - importable on every platform we ship
    import psutil

    _HAS_PSUTIL = True
except ImportError:  # pragma: no cover
    _HAS_PSUTIL = False


_TASKKILL_PATH: str | None = None


def _resolve_taskkill() -> str:
    """Absolute path to taskkill.exe to defeat PATH poisoning."""
    global _TASKKILL_PATH
    if _TASKKILL_PATH is not None:
        return _TASKKILL_PATH
    system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"  # noqa: SIM112
    candidate = os.path.join(system_root, "System32", "taskkill.exe")
    _TASKKILL_PATH = candidate if os.path.isfile(candidate) else "taskkill"
    return _TASKKILL_PATH


async def kill_process_tree(
    proc: asyncio.subprocess.Process,
    *,
    grace: float = 2.0,
) -> None:
    """Terminate ``proc`` and all of its descendants. Best-effort, never raises."""
    if proc.returncode is not None:
        return
    if _HAS_PSUTIL:
        await _kill_via_psutil(proc, grace=grace)
        return
    await _kill_via_stdlib(proc, grace=grace)


async def _kill_via_psutil(
    proc: asyncio.subprocess.Process,
    *,
    grace: float,
) -> None:
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
