# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from agent_framework_tools.shell._killtree import (
    _kill_via_psutil,
    _kill_via_stdlib,
    _resolve_taskkill,
    kill_process_tree,
)


class _FakeAsyncProcess:
    def __init__(self, *, pid: int = 101, returncode: int | None = None) -> None:
        self.pid = pid
        self.returncode = returncode
        self.killed = False

    async def wait(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class _FakeExecProcess(_FakeAsyncProcess):
    def __init__(
        self,
        *,
        returncode: int | None = 0,
        communicate_results: list[tuple[bytes, bytes] | BaseException] | None = None,
    ) -> None:
        super().__init__(returncode=returncode)
        self.stdout = object()
        self.stderr = object()
        self._communicate_results = list(communicate_results or [(b"", b"")])

    async def communicate(self) -> tuple[bytes, bytes]:
        result = self._communicate_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        stdout, stderr = result
        return stdout, stderr


def test_resolve_taskkill_uses_systemroot_and_caches(monkeypatch) -> None:
    import agent_framework_tools.shell._killtree as killtree_module

    monkeypatch.setattr(killtree_module, "_taskkill_path", None)
    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    monkeypatch.setattr(killtree_module.os.path, "isfile", lambda path: path.endswith("taskkill.exe"))

    expected_path = os.path.join("C:\\Windows", "System32", "taskkill.exe")
    assert _resolve_taskkill() == expected_path
    assert _resolve_taskkill() == expected_path


async def test_kill_process_tree_short_circuits_or_delegates() -> None:
    proc = cast(asyncio.subprocess.Process, _FakeAsyncProcess(returncode=0))
    await kill_process_tree(proc)

    live = cast(asyncio.subprocess.Process, _FakeAsyncProcess(returncode=None))
    with (
        patch("agent_framework_tools.shell._killtree._kill_via_psutil", AsyncMock()) as via_psutil,
        patch("agent_framework_tools.shell._killtree._has_psutil", True),
    ):
        await kill_process_tree(live)

    via_psutil.assert_awaited_once_with(live, grace=2.0)


async def test_kill_via_psutil_terminates_parent_and_children() -> None:
    import agent_framework_tools.shell._killtree as killtree_module

    no_such_process = type("NoSuchProcess", (Exception,), {})
    access_denied = type("AccessDenied", (Exception,), {})
    child = MagicMock(is_running=MagicMock(return_value=True))
    parent = MagicMock(children=MagicMock(return_value=[child]), is_running=MagicMock(return_value=True))
    fake_psutil = MagicMock(
        Process=MagicMock(return_value=parent),
        NoSuchProcess=no_such_process,
        AccessDenied=access_denied,
    )
    proc = cast(asyncio.subprocess.Process, _FakeAsyncProcess(pid=4321, returncode=None))

    with patch.object(killtree_module, "psutil", fake_psutil):
        await _kill_via_psutil(proc, grace=0.01)

    parent.terminate.assert_called_once()
    child.terminate.assert_called_once()
    parent.kill.assert_called_once()
    child.kill.assert_called_once()


async def test_kill_via_psutil_handles_missing_parent_process() -> None:
    import agent_framework_tools.shell._killtree as killtree_module

    no_such_process = type("NoSuchProcess", (Exception,), {})
    fake_psutil = MagicMock(Process=MagicMock(side_effect=no_such_process()), NoSuchProcess=no_such_process)
    proc = cast(asyncio.subprocess.Process, _FakeAsyncProcess(pid=9999, returncode=None))

    with patch.object(killtree_module, "psutil", fake_psutil):
        await _kill_via_psutil(proc, grace=0.01)


async def test_kill_via_stdlib_windows_uses_taskkill_and_proc_kill(monkeypatch) -> None:
    import agent_framework_tools.shell._killtree as killtree_module

    monkeypatch.setattr(killtree_module.sys, "platform", "win32")
    monkeypatch.setattr(killtree_module, "_resolve_taskkill", lambda: "C:\\Windows\\System32\\taskkill.exe")
    killer = _FakeExecProcess(returncode=None)
    raw_proc = _FakeAsyncProcess(pid=55, returncode=None)
    proc = cast(asyncio.subprocess.Process, raw_proc)

    with patch("agent_framework_tools.shell._killtree.asyncio.create_subprocess_exec", AsyncMock(return_value=killer)):
        await _kill_via_stdlib(proc, grace=0.01)

    assert killer.killed is True
    assert raw_proc.killed is True


async def test_kill_via_stdlib_posix_escalates_to_sigkill(monkeypatch) -> None:
    import agent_framework_tools.shell._killtree as killtree_module

    monkeypatch.setattr(killtree_module.sys, "platform", "darwin")
    killpg = MagicMock()
    monkeypatch.setattr(killtree_module.os, "getpgid", lambda pid: 99, raising=False)
    monkeypatch.setattr(killtree_module.os, "killpg", killpg, raising=False)

    calls = {"count": 0}

    async def fake_wait_for(awaitable: Any, timeout: float) -> None:
        del timeout
        calls["count"] += 1
        if calls["count"] == 1:
            awaitable.close()
            raise asyncio.TimeoutError
        await awaitable

    proc = cast(asyncio.subprocess.Process, _FakeAsyncProcess(pid=12, returncode=None))

    with patch("agent_framework_tools.shell._killtree.asyncio.wait_for", side_effect=fake_wait_for):
        await _kill_via_stdlib(proc, grace=0.01)

    assert killpg.call_args_list[0].args == (99, killtree_module.signal.SIGTERM)
    assert killpg.call_args_list[1].args == (99, killtree_module.signal.SIGKILL)
