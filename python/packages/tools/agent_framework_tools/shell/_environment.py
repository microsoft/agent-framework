# Copyright (c) Microsoft. All rights reserved.

"""Shell environment context provider.

Probes the underlying shell (OS, family/version, working directory,
configured CLI tools) once per provider lifetime and injects an
instructions block so the agent emits commands in the correct shell
idiom rather than defaulting to bash syntax inside a PowerShell session
or vice versa. The probe runs through any :class:`ShellExecutor`, so the
same provider works with both :class:`LocalShellTool` and
:class:`DockerShellTool`.
"""

from __future__ import annotations

import asyncio
import platform
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from agent_framework import AgentSession, ContextProvider, SessionContext, SupportsAgentRun

from ._executor_base import ShellExecutor
from ._types import ShellCommandError, ShellExecutionError, ShellResult, ShellTimeoutError


class ShellFamily(str, Enum):
    """Shell families recognised by the provider."""

    POSIX = "posix"
    POWERSHELL = "powershell"


@dataclass(frozen=True)
class ShellEnvironmentSnapshot:
    """Point-in-time snapshot of the shell environment.

    Attributes:
        family: Detected (or configured) shell family.
        os_description: A short OS description from :mod:`platform`.
        shell_version: Reported shell version, or ``None`` when probing
            failed or the shell did not report one.
        working_directory: CWD reported by the shell, or empty string
            when probing failed.
        tool_versions: Map of probed CLI tool name to reported version.
            ``None`` values indicate the tool was not installed or did
            not respond to ``--version`` within the probe timeout.
    """

    family: ShellFamily
    os_description: str
    shell_version: str | None
    working_directory: str
    tool_versions: Mapping[str, str | None]


@dataclass(frozen=True)
class ShellEnvironmentProviderOptions:
    """Configuration for :class:`ShellEnvironmentProvider`.

    Attributes:
        probe_tools: CLI tools whose ``--version`` output is probed.
        override_family: Optional override for the auto-detected family.
            When ``None``, the family is inferred from :data:`sys.platform`
            (Windows → PowerShell, otherwise POSIX). Set this when
            running against a non-default shell (e.g. bash on Windows
            via WSL, or pwsh on Linux).
        probe_timeout: Per-probe execution timeout in seconds. Probes
            that exceed this are recorded as missing rather than raised
            to the agent.
        instructions_formatter: Optional callable that renders the
            snapshot as the instructions block. When ``None``, the
            built-in :func:`default_instructions_formatter` is used.
    """

    probe_tools: Sequence[str] = field(
        default_factory=lambda: ("git", "node", "python", "docker"),
    )
    override_family: ShellFamily | None = None
    probe_timeout: float = 5.0
    instructions_formatter: Callable[[ShellEnvironmentSnapshot], str] | None = None


_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _detect_family() -> ShellFamily:
    return ShellFamily.POWERSHELL if sys.platform == "win32" else ShellFamily.POSIX


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


class ShellEnvironmentProvider(ContextProvider):
    """:class:`ContextProvider` that injects a shell-environment block.

    The provider runs a small set of probe commands against the supplied
    :class:`ShellExecutor` once, caches the resulting
    :class:`ShellEnvironmentSnapshot`, and on every ``before_run`` adds a
    formatted instructions block to the session context. It does not
    register any tools.

    Probe failures from a narrow set of expected error types are recorded
    as ``None`` fields in the snapshot (per-probe timeout, policy
    rejection, executor spawn failure). Other exceptions propagate so
    bugs are not silently swallowed.

    A missing CLI never fails the agent: the model simply sees fewer
    hints in its system prompt.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "shell_environment"

    def __init__(
        self,
        executor: ShellExecutor,
        options: ShellEnvironmentProviderOptions | None = None,
        *,
        source_id: str | None = None,
    ) -> None:
        super().__init__(source_id or self.DEFAULT_SOURCE_ID)
        self._executor = executor
        self._options = options or ShellEnvironmentProviderOptions()
        self._snapshot: ShellEnvironmentSnapshot | None = None
        self._lock = asyncio.Lock()

    @property
    def current_snapshot(self) -> ShellEnvironmentSnapshot | None:
        """The most recent snapshot, or ``None`` before the first probe."""
        return self._snapshot

    async def refresh(self) -> ShellEnvironmentSnapshot:
        """Force a re-probe and replace the cached snapshot.

        Useful when the agent has changed something the snapshot depends
        on, e.g. installed a new CLI mid-session.
        """
        async with self._lock:
            snapshot = await self._probe()
            self._snapshot = snapshot
            return snapshot

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        snapshot = await self._get_or_probe()
        formatter = self._options.instructions_formatter or default_instructions_formatter
        context.extend_instructions(self.source_id, formatter(snapshot))

    async def _get_or_probe(self) -> ShellEnvironmentSnapshot:
        # Double-checked: return any already-cached snapshot without
        # acquiring the lock; otherwise serialize the first probe so
        # concurrent first-callers wait for a single result. A failed
        # probe leaves _snapshot as None so the next call retries.
        if self._snapshot is not None:
            return self._snapshot
        async with self._lock:
            if self._snapshot is None:
                self._snapshot = await self._probe()
            return self._snapshot

    async def _probe(self) -> ShellEnvironmentSnapshot:
        family = self._options.override_family or _detect_family()
        await self._executor.start()

        shell_version, working_dir = await self._probe_shell_and_cwd(family)

        tool_versions: dict[str, str | None] = {}
        for tool in self._options.probe_tools:
            # Skip case-insensitive duplicates so a caller passing
            # ("git", "GIT") does not probe twice.
            if tool.lower() in {existing.lower() for existing in tool_versions}:
                continue
            tool_versions[tool] = await self._probe_tool_version(tool)

        return ShellEnvironmentSnapshot(
            family=family,
            os_description=platform.platform(),
            shell_version=shell_version,
            working_directory=working_dir,
            tool_versions=tool_versions,
        )

    async def _probe_shell_and_cwd(self, family: ShellFamily) -> tuple[str | None, str]:
        if family is ShellFamily.POWERSHELL:
            command = (
                'Write-Output ("VERSION=" + $PSVersionTable.PSVersion.ToString()); '
                'Write-Output ("CWD=" + (Get-Location).Path)'
            )
        else:
            command = (
                'echo "VERSION=${BASH_VERSION:-${ZSH_VERSION:-unknown}}"; '
                'echo "CWD=$PWD"'
            )

        result = await self._run_probe(command)
        if result is None:
            return None, ""

        version: str | None = None
        cwd = ""
        for raw in result.stdout.splitlines():
            line = raw.strip()
            if line.startswith("VERSION="):
                value = line[len("VERSION="):].strip()
                version = None if not value or value == "unknown" else value
            elif line.startswith("CWD="):
                cwd = line[len("CWD="):].strip()
        return version, cwd

    async def _probe_tool_version(self, tool: str) -> str | None:
        # Reject anything that is not a plain identifier — the tool name
        # is interpolated into a shell command, so quotes, $, ;, |, &,
        # whitespace, etc. would allow command injection if the tool list
        # were sourced from untrusted input.
        if not tool or not _TOOL_NAME_PATTERN.match(tool):
            return None

        result = await self._run_probe(f"{tool} --version")
        if result is None or result.exit_code != 0:
            return None

        # Some CLIs (older java, gcc) emit --version on stderr.
        line = _first_non_empty_line(result.stdout) or _first_non_empty_line(result.stderr)
        return line if line else None

    async def _run_probe(self, command: str) -> ShellResult | None:
        try:
            return await asyncio.wait_for(
                self._executor.run(command),
                timeout=self._options.probe_timeout,
            )
        except asyncio.TimeoutError:
            return None
        except (ShellCommandError, ShellExecutionError, ShellTimeoutError):
            return None


def default_instructions_formatter(snapshot: ShellEnvironmentSnapshot) -> str:
    """Render ``snapshot`` as the default instructions block.

    Public so callers that want to wrap or extend the default can call
    it from a custom ``instructions_formatter``.
    """
    lines: list[str] = ["## Shell environment"]
    version_suffix = f" {snapshot.shell_version}" if snapshot.shell_version else ""

    if snapshot.family is ShellFamily.POWERSHELL:
        lines.append(
            f"You are operating a PowerShell{version_suffix} session on {snapshot.os_description}."
        )
        lines.append("Use PowerShell idioms, NOT bash:")
        lines.append("- Set environment variables with `$env:NAME = 'value'` (NOT `NAME=value`).")
        lines.append("- Change directory with `Set-Location` or `cd`. Paths use `\\` separators.")
        lines.append("- Reference environment variables as `$env:NAME` (NOT `$NAME`).")
        lines.append("- The system temp directory is `[System.IO.Path]::GetTempPath()` (NOT `/tmp`).")
        lines.append("- Pipe to `Out-Null` to suppress output (NOT `> /dev/null`).")
    else:
        lines.append(
            f"You are operating a POSIX shell{version_suffix} session on {snapshot.os_description}."
        )
        lines.append("Use POSIX shell idioms (bash/sh).")
        lines.append("- Set environment variables for the next command with `export NAME=value`.")
        lines.append("- Reference environment variables as `$NAME` or `${NAME}`.")
        lines.append("- Paths use `/` separators.")

    if snapshot.working_directory:
        lines.append(f"Working directory: {snapshot.working_directory}")

    installed = [f"{name} ({version})" for name, version in snapshot.tool_versions.items() if version]
    missing = [name for name, version in snapshot.tool_versions.items() if version is None]
    if installed:
        lines.append("Available CLIs: " + ", ".join(installed))
    if missing:
        lines.append("Not installed: " + ", ".join(missing))

    return "\n".join(lines)
