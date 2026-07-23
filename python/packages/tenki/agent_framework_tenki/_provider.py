# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext
from agent_framework._tools import ApprovalMode

from ._execute_code_tool import TenkiExecuteCodeTool

logger = logging.getLogger(__name__)

TENKI_CODEACT_INSTRUCTIONS = (
    "You have access to `execute_code`, which runs Python inside a Tenki microVM "
    "sandbox. Each call runs the code as `python3 -c <code>` — only stdout and "
    "stderr are captured, so wrap results in `print(...)`; bare expressions are "
    "not auto-printed like in a REPL. The sandbox filesystem persists across "
    "calls (files under `/home/tenki` and `/tmp` are visible in later calls), but "
    "Python interpreter state does not — every call starts a fresh Python process, "
    "so persist intermediate state through files or environment variables when a "
    "later call needs it. Do not use Jupyter/IPython magic syntax (`!command`, "
    "`%magic`, `{var}` interpolation) — those do not work in plain `python3 -c` "
    "and will raise `SyntaxError`. Use newlines (not semicolons) to introduce "
    "compound statements like `if`, `for`, `while`, `with`, or `try`: Python's "
    "grammar does not permit compound statements after `;` and `import x; with "
    "open(...) as f: ...` raises `SyntaxError`. Valid single-line form: "
    "`with open('/tmp/x.txt') as f: print(f.read())` — semicolons ARE allowed "
    "between simple statements inside the block body (e.g. `with open(...) as "
    "f: x = f.read(); print(x)`); what's forbidden is a compound statement "
    "following a semicolon. For shell commands, use "
    "`subprocess`; for example, to install a Python package: `import subprocess, "
    "sys; subprocess.check_call([sys.executable, '-m', 'pip', 'install', "
    "'--break-system-packages', '<package>'])`."
)


class TenkiCodeActProvider(ContextProvider):
    """Inject a Tenki-backed CodeAct surface with a **run-scoped** execute_code tool.

    On every agent run, `before_run` mints a fresh `TenkiExecuteCodeTool` via
    `TenkiExecuteCodeTool.create_run_tool` and exposes it to the model.
    `after_run` terminates that run-scoped tool's sandbox so state does not leak
    across runs.

    Sandbox naming: an explicit ``sandbox_name`` on the provider is used as the
    **prefix** for run-scoped sandboxes (e.g. ``sandbox_name="analysis-agent"`` →
    ``"analysis-agent-<8-hex>"`` per run). Without an explicit name, run-scoped
    sandboxes get ``agent-framework-<8-hex>``.

    Cost implication: every agent run provisions and terminates a new Tenki microVM.
    Provisioning adds a few seconds of startup latency (~2s measured with the
    default image) and consumes credits for the run's duration. Use the standalone
    `TenkiExecuteCodeTool` directly (bypassing the provider) if you need to reuse
    a sandbox across runs.

    ``max_duration_seconds=None`` (the default) means "use the tool's own default"
    (see ``TenkiExecuteCodeTool``); there is no way to opt out of a max duration
    through the provider. Likewise ``pause_retention_seconds=None`` (the default)
    means "use the run-scoped default" (1 hour): a run-scoped sandbox that
    outlives its run is an orphan of a failed cleanup, so its pause snapshot is
    GC'd by Tenki after an hour instead of the server default of 7 days.
    """

    DEFAULT_SOURCE_ID = "tenki_codeact"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        approval_mode: ApprovalMode | None = None,
        api_key: str | None = None,
        sandbox_name: str | None = None,
        image: str | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
        cpu_cores: int | None = None,
        memory_mb: int | None = None,
        disk_size_gb: int | None = None,
        max_duration_seconds: int | None = None,
        pause_retention_seconds: int | None = None,
        exec_timeout_seconds: int = 60,
        extra_create_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(source_id)
        # ``max_duration_seconds=None`` here means "use the tool's own default"
        # (see ``_execute_code_tool._DEFAULT_MAX_DURATION_SECONDS``).
        tool_kwargs: dict[str, Any] = {
            "approval_mode": approval_mode,
            "api_key": api_key,
            "sandbox_name": sandbox_name,
            "image": image,
            "project_id": project_id,
            "workspace_id": workspace_id,
            "cpu_cores": cpu_cores,
            "memory_mb": memory_mb,
            "disk_size_gb": disk_size_gb,
            "pause_retention_seconds": pause_retention_seconds,
            "exec_timeout_seconds": exec_timeout_seconds,
            "extra_create_kwargs": extra_create_kwargs,
        }
        if max_duration_seconds is not None:
            tool_kwargs["max_duration_seconds"] = max_duration_seconds
        # Base tool acts as a template config-holder; it never provisions a
        # sandbox itself. Run-scoped copies are minted per agent run.
        self._execute_code_tool = TenkiExecuteCodeTool(**tool_kwargs)

        # Live run-scoped tools keyed by sandbox name, so ``close`` can terminate
        # any that leaked past ``after_run`` (e.g. mid-run exception). The
        # contract is "no new runs after ``close()``" — callers running
        # concurrent agent runs on one provider must let all runs finish before
        # invoking ``close()``.
        self._live_run_tools: dict[str, TenkiExecuteCodeTool] = {}

    @property
    def execute_code_tool(self) -> TenkiExecuteCodeTool:
        """The base template tool. Advanced: use as a config template, not for direct exec."""
        return self._execute_code_tool

    async def close(self) -> None:
        """Terminate any lingering run-scoped sandboxes and the base template tool.

        Called when the provider goes out of scope (via ``async with`` or an
        explicit ``close()``). Sandboxes for completed runs are already terminated
        by ``after_run``; this cleans up any that leaked past that hook due to
        an in-run exception.

        Raises:
            RuntimeError: If terminating one or more run-scoped sandboxes failed
                — raised only after every close was attempted. Failed entries
                stay tracked, so a second ``close()`` retries exactly those.
        """
        leaked = list(self._live_run_tools.items())
        # Terminate orphans in parallel — each ``close()`` is one terminate RPC
        # (seconds of latency), and a crashed run that leaked multiple sandboxes
        # would otherwise pay N * latency on provider teardown. Entries are
        # removed only on success so a failed terminate stays retryable via a
        # second ``close()`` — mirroring the handle-preserving contract of
        # ``TenkiExecuteCodeTool.close`` and ``after_run``.
        results = await asyncio.gather(*(tool.close() for _, tool in leaked), return_exceptions=True)
        failures: list[tuple[str, BaseException]] = []
        for (sandbox_name, _), result in zip(leaked, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to close orphaned run-scoped Tenki sandbox %s: %s",
                    sandbox_name,
                    result,
                )
                failures.append((sandbox_name, result))
            else:
                self._live_run_tools.pop(sandbox_name, None)
        # Base template tool never provisions, so this is a no-op in practice —
        # kept for symmetry with the standalone-tool ``async with`` pattern.
        await self._execute_code_tool.close()
        if failures:
            # Surface the failure so ``async with`` callers learn a sandbox may
            # still be live; every close was already attempted above.
            names = ", ".join(sorted(name for name, _ in failures))
            raise RuntimeError(
                f"Failed to terminate {len(failures)} run-scoped Tenki sandbox(es): {names}. "
                "The handles are retained; call close() again to retry."
            ) from failures[0][1]

    async def __aenter__(self) -> TenkiCodeActProvider:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject a fresh run-scoped ``execute_code`` tool for this agent run."""
        run_tool = self._execute_code_tool.create_run_tool()
        self._live_run_tools[run_tool.sandbox_name] = run_tool
        # Provider state is serialized with the session, so store only the
        # sandbox name; the live tool handle stays in ``_live_run_tools``.
        state[self.source_id] = run_tool.sandbox_name
        context.extend_instructions(self.source_id, TENKI_CODEACT_INSTRUCTIONS)
        context.extend_tools(self.source_id, [run_tool])

    async def after_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Terminate this run's sandbox so state cannot leak to the next run."""
        sandbox_name = state.pop(self.source_id, None)
        if sandbox_name is None:
            return
        run_tool = self._live_run_tools.get(sandbox_name)
        if run_tool is None:
            return
        try:
            await run_tool.close()
        except Exception as exc:
            # Preserve the handle so ``provider.close()`` can retry; the
            # sandbox's max_duration eventually stops billing as a backstop
            # (unscoped sandboxes terminate; project/workspace-scoped ones pause).
            logger.warning(
                "Failed to terminate run-scoped Tenki sandbox %s: %s",
                sandbox_name,
                exc,
            )
        else:
            self._live_run_tools.pop(sandbox_name, None)
