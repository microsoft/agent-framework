# Copyright (c) Microsoft. All rights reserved.

"""High-level :class:`LocalShellTool` facade."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from agent_framework import FunctionTool, tool
from agent_framework._tools import SHELL_TOOL_KIND_VALUE

from ._executor import run_stateless
from ._policy import ShellPolicy, ShellRequest
from ._resolve import resolve_shell
from ._session import ShellSession
from ._types import ShellCommandError, ShellMode, ShellResult

logger = logging.getLogger(__name__)

_DEFAULT_DESCRIPTION = (
    "Execute a single shell command on the local machine and return its "
    "stdout, stderr, and exit code. Commands run in a persistent session so "
    "`cd` and environment variables from previous calls are preserved. "
    "Destructive commands are blocked and approval is required by default."
)


class LocalShellTool:
    """A safe, cross-OS local shell tool that plugs into any agent-framework chat client.

    Typical use::

        shell = LocalShellTool()
        agent = Agent(
            client=client,
            tools=[client.get_shell_tool(func=shell.as_function())],
        )

    Or as an async context manager (recommended in persistent mode so the
    session is cleaned up on exit)::

        async with LocalShellTool() as shell:
            ...

    Args:
        mode: ``"persistent"`` (default) keeps a single long-lived shell
            subprocess so ``cd`` / ``export`` carry across calls.
            ``"stateless"`` spawns a fresh subprocess per call.
        shell: Optional shell argv override. String values are tokenised.
            When omitted, the platform default is used (``pwsh`` or
            ``powershell`` on Windows, ``bash`` or ``sh`` on Unix). May also
            be overridden via the ``AGENT_FRAMEWORK_SHELL`` env var.
        workdir: Working directory for commands. Defaults to the current
            working directory. In persistent mode, ``cd`` outside this
            directory is blocked when ``confine_workdir=True``.
        confine_workdir: When ``True`` (default), each command in persistent
            mode is prefixed with a ``cd`` back into ``workdir`` so
            ``cd``-wandering in one call does not leak to the next. This is
            a **re-anchor**, not a hard confinement — a command that does
            ``cd /tmp && rm -rf .`` in one call can still touch ``/tmp``.
            Use :class:`ShellPolicy` or a sandboxed executor for true
            confinement.
        env: Seed environment. In stateless mode this replaces the child's
            environment unless ``clean_env=False``. In persistent mode the
            variables are exported before the session is used.
        clean_env: When ``True``, do **not** inherit ``os.environ``; only
            the variables supplied in ``env`` are visible to commands.
        policy: Policy applied before approval. Defaults to
            :class:`ShellPolicy()` which denies common destructive patterns.
        timeout: Per-command timeout in seconds. ``None`` disables. Default
            30 s.
        max_output_bytes: Combined stdout/stderr byte cap before truncation.
            Default 64 KiB.
        approval_mode: ``"always_require"`` (default) or ``"never_require"``.
            Controls the ``FunctionTool.approval_mode`` on the returned
            function, which the framework uses to gate execution via
            ``user_input_requests``.
        on_command: Optional audit hook called with the command string for
            every command that passes policy. Use for logging / telemetry.
    """

    def __init__(
        self,
        *,
        mode: ShellMode = "persistent",
        shell: str | Sequence[str] | None = None,
        workdir: str | os.PathLike[str] | None = None,
        confine_workdir: bool = True,
        env: Mapping[str, str] | None = None,
        clean_env: bool = False,
        policy: ShellPolicy | None = None,
        timeout: float | None = 30.0,
        max_output_bytes: int = 64 * 1024,
        approval_mode: Literal["always_require", "never_require"] = "always_require",
        on_command: Callable[[str], None] | None = None,
    ) -> None:
        if mode not in ("persistent", "stateless"):
            raise ValueError(f"mode must be 'persistent' or 'stateless', got {mode!r}")
        self._mode: ShellMode = mode
        self._shell_override = shell
        self._workdir: str | None = os.fspath(workdir) if workdir is not None else None
        self._confine_workdir = confine_workdir
        self._policy = policy or ShellPolicy()
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._approval_mode = approval_mode
        self._on_command = on_command

        merged_env: dict[str, str] | None
        if env is None and not clean_env:
            merged_env = None  # inherit
        elif clean_env:
            merged_env = dict(env) if env is not None else {}
        else:
            merged_env = {**os.environ, **dict(env or {})}
        self._env = merged_env

        self._interactive_argv = resolve_shell(self._shell_override, interactive=True)
        self._stateless_argv = resolve_shell(self._shell_override, interactive=False)
        self._session: ShellSession | None = None
        self._session_lock: "asyncio.Lock | None" = None

    def _get_session_lock(self) -> "asyncio.Lock":
        # Lazily create in the running loop so construction outside a loop is fine.
        if self._session_lock is None:
            self._session_lock = asyncio.Lock()
        return self._session_lock

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Eagerly spawn the persistent session (no-op in stateless mode)."""
        if self._mode != "persistent":
            return
        async with self._get_session_lock():
            if self._session is None:
                self._session = ShellSession(
                    self._interactive_argv,
                    workdir=self._workdir,
                    env=self._env,
                    max_output_bytes=self._max_output_bytes,
                )
            await self._session.start()

    async def close(self) -> None:
        """Terminate the persistent session if any."""
        async with self._get_session_lock():
            if self._session is not None:
                try:
                    await self._session.close()
                finally:
                    self._session = None

    async def __aenter__(self) -> "LocalShellTool":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------ core run

    async def run(self, command: str) -> ShellResult:
        """Execute ``command`` directly and return its :class:`ShellResult`.

        Applies policy and the audit hook, but **not** approval (that is
        handled by the framework when this tool is wrapped via
        :meth:`as_function`).
        """
        request = ShellRequest(command=command, workdir=self._workdir)
        decision = self._policy.evaluate(request)
        if decision.decision == "deny":
            raise ShellCommandError(f"Command rejected by policy: {decision.reason}")
        if self._on_command is not None:
            try:
                self._on_command(command)
            except Exception:
                logger.exception("on_command hook raised")

        if self._mode == "persistent":
            if self._session is None:
                await self.start()
            assert self._session is not None
            effective = self._maybe_reanchor(command)
            return await self._session.run(effective, timeout=self._timeout)

        return await run_stateless(
            self._stateless_argv,
            command,
            workdir=self._workdir,
            env=self._env,
            timeout=self._timeout,
            max_output_bytes=self._max_output_bytes,
        )

    # ------------------------------------------------------------------ AF wiring

    def as_function(
        self,
        *,
        name: str = "run_shell",
        description: str | None = None,
    ) -> FunctionTool:
        """Return an :class:`~agent_framework.FunctionTool` bound to this instance.

        The returned tool has ``kind="shell"`` so provider-specific
        ``get_shell_tool(func=...)`` factories recognise it as a local shell.
        """

        async def _run_shell(command: str) -> str:
            try:
                result = await self.run(command)
            except ShellCommandError as exc:
                return f"Command blocked by policy: {exc}"
            return result.format_for_model()

        _run_shell.__doc__ = description or _DEFAULT_DESCRIPTION
        return tool(
            func=_run_shell,
            name=name,
            description=description or _DEFAULT_DESCRIPTION,
            approval_mode=self._approval_mode,
            kind=SHELL_TOOL_KIND_VALUE,
        )

    # ------------------------------------------------------------------ helpers

    def _maybe_reanchor(self, command: str) -> str:
        """Prefix ``cd`` when confinement is enabled and workdir is set."""
        if not self._confine_workdir or self._workdir is None:
            return command
        # Idempotent prefix: always cd back before running the user command
        # so wandering with ``cd`` in one command doesn't leak to the next.
        # This matches what Claude Code does for its Bash tool.
        quoted = self._workdir.replace('"', '\\"')
        if self._interactive_argv and "pwsh" in os.path.basename(self._interactive_argv[0]).lower():
            return f'Set-Location -LiteralPath "{quoted}"\n{command}'
        return f'cd -- "{quoted}"\n{command}'
