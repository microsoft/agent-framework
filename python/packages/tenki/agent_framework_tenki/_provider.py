# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, Optional

from agent_framework import AgentSession, ContextProvider, SessionContext
from agent_framework._tools import ApprovalMode

from ._execute_code_tool import TenkiExecuteCodeTool

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
    """Inject a Tenki-backed CodeAct surface using a provider-owned execute_code tool.

    On every agent run, the provider exposes its underlying :class:`TenkiExecuteCodeTool`
    to the context so the model can run Python inside a Tenki sandbox.

    The sandbox is reused across runs of the same provider — its filesystem and installed
    packages persist across calls, though each individual ``execute_code`` invocation is
    a fresh Python process. Instantiate a new provider per agent instance when you need
    isolation between agents.
    """

    DEFAULT_SOURCE_ID = "tenki_codeact"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        approval_mode: Optional[ApprovalMode] = None,
        api_key: Optional[str] = None,
        sandbox_name: Optional[str] = None,
        image: Optional[str] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        cpu_cores: Optional[int] = None,
        memory_mb: Optional[int] = None,
        disk_size_gb: Optional[int] = None,
        max_duration_seconds: Optional[int] = None,
        exec_timeout_seconds: int = 60,
        extra_create_kwargs: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(source_id)
        self._execute_code_tool = TenkiExecuteCodeTool(
            approval_mode=approval_mode,
            api_key=api_key,
            sandbox_name=sandbox_name,
            image=image,
            project_id=project_id,
            workspace_id=workspace_id,
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
            disk_size_gb=disk_size_gb,
            max_duration_seconds=max_duration_seconds,
            exec_timeout_seconds=exec_timeout_seconds,
            extra_create_kwargs=extra_create_kwargs,
        )

    @property
    def execute_code_tool(self) -> TenkiExecuteCodeTool:
        """The underlying execute_code tool. Exposed for advanced integration."""
        return self._execute_code_tool

    async def close(self) -> None:
        """Terminate the underlying Tenki sandbox and release its resources."""
        await self._execute_code_tool.close()

    async def __aenter__(self) -> TenkiCodeActProvider:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject the execute_code tool and its usage instructions for this run."""
        context.extend_instructions(self.source_id, TENKI_CODEACT_INSTRUCTIONS)
        context.extend_tools(self.source_id, [self._execute_code_tool])
