# Copyright (c) Microsoft. All rights reserved.

"""``MontyCodeActProvider`` - context provider injecting Monty-backed CodeAct."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from agent_framework import AgentSession, ContextProvider, FunctionTool, SessionContext
from agent_framework._tools import ApprovalMode

from ._execute_code_tool import MontyExecuteCodeTool
from ._types import FileMount, FileMountInput


class MontyCodeActProvider(ContextProvider):
    """Inject a Monty-backed CodeAct surface using provider-owned tools.

    Mirrors :class:`agent_framework_hyperlight.HyperlightCodeActProvider` for
    the subset of capabilities that apply to the Monty interpreter:
    ``tools``, ``approval_mode``, ``workspace_root``, ``file_mounts``, and
    ``resource_limits`` (Monty-only).
    """

    DEFAULT_SOURCE_ID = "monty_codeact"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        approval_mode: ApprovalMode | None = None,
        workspace_root: str | Path | None = None,
        file_mounts: FileMountInput | Sequence[FileMountInput] | None = None,
        resource_limits: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(source_id)
        self._execute_code_tool = MontyExecuteCodeTool(
            tools=tools,
            approval_mode=approval_mode,
            workspace_root=workspace_root,
            file_mounts=file_mounts,
            resource_limits=resource_limits,
        )

    def add_tools(
        self,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]],
    ) -> None:
        """Add provider-owned Monty tools."""
        self._execute_code_tool.add_tools(tools)

    def get_tools(self) -> list[FunctionTool]:
        """Return the provider-owned Monty tools."""
        return self._execute_code_tool.get_tools()

    def remove_tool(self, name: str) -> None:
        """Remove one provider-owned Monty tool by name."""
        self._execute_code_tool.remove_tool(name)

    def clear_tools(self) -> None:
        """Remove all provider-owned Monty tools."""
        self._execute_code_tool.clear_tools()

    def add_file_mounts(self, file_mounts: FileMountInput | Sequence[FileMountInput]) -> None:
        """Add provider-managed file mounts."""
        self._execute_code_tool.add_file_mounts(file_mounts)

    def get_file_mounts(self) -> list[FileMount]:
        """Return the provider-managed file mounts (excluding ``workspace_root``)."""
        return self._execute_code_tool.get_file_mounts()

    def remove_file_mount(self, mount_path: str) -> None:
        """Remove one provider-managed file mount by its sandbox path."""
        self._execute_code_tool.remove_file_mount(mount_path)

    def clear_file_mounts(self) -> None:
        """Remove all provider-managed file mounts."""
        self._execute_code_tool.clear_file_mounts()

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject CodeAct instructions and a run-scoped execute_code tool before each run."""
        run_tool = self._execute_code_tool.create_run_tool()
        state[self.source_id] = run_tool.build_serializable_state()
        context.extend_instructions(self.source_id, run_tool.build_instructions(tools_visible_to_model=False))
        context.extend_tools(self.source_id, [run_tool])
