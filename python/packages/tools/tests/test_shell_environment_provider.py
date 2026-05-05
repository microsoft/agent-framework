# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for :class:`ShellEnvironmentProvider`."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agent_framework_tools.shell import (
    ShellCommandError,
    ShellEnvironmentProvider,
    ShellEnvironmentProviderOptions,
    ShellExecutionError,
    ShellFamily,
    ShellResult,
    default_instructions_formatter,
)

pytestmark = pytest.mark.asyncio


class _FakeExecutor:
    """In-memory ShellExecutor stub. Maps command-prefix -> response."""

    def __init__(self, responses: dict[str, ShellResult | Exception | float]) -> None:
        self._responses = responses
        self.start_calls = 0
        self.run_calls: list[str] = []

    async def start(self) -> None:
        self.start_calls += 1

    async def close(self) -> None: ...

    async def __aenter__(self) -> "_FakeExecutor":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def run(self, command: str) -> ShellResult:
        self.run_calls.append(command)
        for prefix, response in self._responses.items():
            if command.startswith(prefix) or prefix in command:
                if isinstance(response, Exception):
                    raise response
                if isinstance(response, (int, float)):
                    await asyncio.sleep(float(response))
                    return ShellResult(stdout="", stderr="", exit_code=0, duration_ms=0)
                return response
        return ShellResult(stdout="", stderr="", exit_code=127, duration_ms=0)


def _ok(stdout: str = "", stderr: str = "", exit_code: int = 0) -> ShellResult:
    return ShellResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=1)


async def test_probe_collects_shell_version_cwd_and_tools() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=5.2.21\nCWD=/repo\n"),
        "git --version": _ok(stdout="git version 2.40.0\n"),
        "node --version": _ok(stdout="v20.11.1\n"),
    })
    options = ShellEnvironmentProviderOptions(
        probe_tools=("git", "node", "missing-tool"),
        override_family=ShellFamily.POSIX,
    )
    provider = ShellEnvironmentProvider(executor, options)

    snapshot = await provider.refresh()

    assert snapshot.family is ShellFamily.POSIX
    assert snapshot.shell_version == "5.2.21"
    assert snapshot.working_directory == "/repo"
    assert snapshot.tool_versions["git"] == "git version 2.40.0"
    assert snapshot.tool_versions["node"] == "v20.11.1"
    assert snapshot.tool_versions["missing-tool"] is None
    assert executor.start_calls >= 1


async def test_probe_falls_back_to_stderr_for_version_when_stdout_empty() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=unknown\nCWD=/x\n"),
        "java --version": _ok(stdout="", stderr="openjdk 21 2024-09-17\n"),
    })
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=("java",),
            override_family=ShellFamily.POSIX,
        ),
    )

    snapshot = await provider.refresh()
    assert snapshot.tool_versions["java"] == "openjdk 21 2024-09-17"
    assert snapshot.shell_version is None  # "unknown" is normalised away


async def test_probe_timeout_yields_none_field_not_exception() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=5.0\nCWD=/r\n"),
        "git --version": 5.0,  # sleeps 5s, probe_timeout below is 0.05s
    })
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=("git",),
            override_family=ShellFamily.POSIX,
            probe_timeout=0.05,
        ),
    )

    snapshot = await provider.refresh()
    assert snapshot.tool_versions["git"] is None


async def test_probe_swallows_expected_executor_failures() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=5\nCWD=/r\n"),
        "git --version": ShellCommandError("blocked"),
        "node --version": ShellExecutionError("spawn failed"),
    })
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=("git", "node"),
            override_family=ShellFamily.POSIX,
        ),
    )

    snapshot = await provider.refresh()
    assert snapshot.tool_versions == {"git": None, "node": None}


async def test_unexpected_exception_propagates() -> None:
    class Boom(RuntimeError): ...
    executor = _FakeExecutor({"echo": Boom("kaboom")})
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=(),
            override_family=ShellFamily.POSIX,
        ),
    )
    with pytest.raises(Boom):
        await provider.refresh()


async def test_invalid_tool_name_is_rejected_before_probing() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=5\nCWD=/r\n"),
    })
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=("git; rm -rf /", "good", ""),
            override_family=ShellFamily.POSIX,
        ),
    )

    snapshot = await provider.refresh()
    assert snapshot.tool_versions["git; rm -rf /"] is None
    # Verify no probe command was actually issued for the malicious entry.
    assert not any("git; rm -rf /" in c for c in executor.run_calls)


async def test_duplicate_tools_are_deduplicated_case_insensitively() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=5\nCWD=/r\n"),
        "git --version": _ok(stdout="git version 2\n"),
    })
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=("git", "GIT", "Git"),
            override_family=ShellFamily.POSIX,
        ),
    )

    snapshot = await provider.refresh()
    assert list(snapshot.tool_versions.keys()) == ["git"]


async def test_failed_probe_does_not_poison_subsequent_calls() -> None:
    calls = {"n": 0}

    class Flaky:
        start_calls = 0

        async def start(self) -> None:
            self.start_calls += 1

        async def close(self) -> None: ...

        async def __aenter__(self) -> "Flaky":
            return self

        async def __aexit__(self, *_: object) -> None: ...

        async def run(self, command: str) -> ShellResult:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            return _ok(stdout="VERSION=5\nCWD=/r\n")

    provider = ShellEnvironmentProvider(
        Flaky(),
        ShellEnvironmentProviderOptions(
            probe_tools=(),
            override_family=ShellFamily.POSIX,
        ),
    )

    with pytest.raises(RuntimeError):
        await provider._get_or_probe()  # type: ignore[attr-defined]

    snapshot = await provider._get_or_probe()  # type: ignore[attr-defined]
    assert snapshot.shell_version == "5"


async def test_concurrent_first_callers_share_a_single_probe() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    call_count = {"n": 0}

    class Slow:
        async def start(self) -> None: ...
        async def close(self) -> None: ...
        async def __aenter__(self) -> "Slow":
            return self

        async def __aexit__(self, *_: object) -> None: ...
        async def run(self, command: str) -> ShellResult:
            if command.startswith("echo"):
                call_count["n"] += 1
                started.set()
                await release.wait()
                return _ok(stdout="VERSION=5\nCWD=/r\n")
            return _ok()

    provider = ShellEnvironmentProvider(
        Slow(),
        ShellEnvironmentProviderOptions(
            probe_tools=(),
            override_family=ShellFamily.POSIX,
        ),
    )

    a = asyncio.create_task(provider._get_or_probe())  # type: ignore[attr-defined]
    b = asyncio.create_task(provider._get_or_probe())  # type: ignore[attr-defined]
    await started.wait()
    release.set()
    s1, s2 = await asyncio.gather(a, b)

    assert s1 is s2
    assert call_count["n"] == 1


async def test_before_run_extends_instructions() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=5.2.21\nCWD=/repo\n"),
        "git --version": _ok(stdout="git version 2.40.0\n"),
    })
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=("git",),
            override_family=ShellFamily.POSIX,
        ),
    )

    received: list[tuple[str, Any]] = []

    class FakeContext:
        def extend_instructions(self, source_id: str, instructions: Any) -> None:
            received.append((source_id, instructions))

    await provider.before_run(
        agent=None,  # type: ignore[arg-type]
        session=None,  # type: ignore[arg-type]
        context=FakeContext(),  # type: ignore[arg-type]
        state={},
    )

    assert len(received) == 1
    src, text = received[0]
    assert src == "shell_environment"
    assert "POSIX shell 5.2.21" in text
    assert "Working directory: /repo" in text
    assert "git (git version 2.40.0)" in text


async def test_default_formatter_powershell_block_uses_pwsh_idioms() -> None:
    from agent_framework_tools.shell import ShellEnvironmentSnapshot

    snapshot = ShellEnvironmentSnapshot(
        family=ShellFamily.POWERSHELL,
        os_description="Windows 11",
        shell_version="7.4.0",
        working_directory=r"C:\repo",
        tool_versions={"git": "2.40", "rust": None},
    )
    text = default_instructions_formatter(snapshot)
    assert "PowerShell 7.4.0" in text
    assert "$env:NAME" in text
    assert r"C:\repo" in text
    assert "Available CLIs: git (2.40)" in text
    assert "Not installed: rust" in text


async def test_custom_formatter_is_used_when_provided() -> None:
    executor = _FakeExecutor({
        "echo": _ok(stdout="VERSION=5\nCWD=/r\n"),
    })
    provider = ShellEnvironmentProvider(
        executor,
        ShellEnvironmentProviderOptions(
            probe_tools=(),
            override_family=ShellFamily.POSIX,
            instructions_formatter=lambda snap: f"FAMILY={snap.family.value}",
        ),
    )

    received: list[tuple[str, Any]] = []

    class FakeContext:
        def extend_instructions(self, source_id: str, instructions: Any) -> None:
            received.append((source_id, instructions))

    await provider.before_run(
        agent=None,  # type: ignore[arg-type]
        session=None,  # type: ignore[arg-type]
        context=FakeContext(),  # type: ignore[arg-type]
        state={},
    )

    assert received[0][1] == "FAMILY=posix"
