# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from agent_framework import AgentSession, ContextProvider, FunctionTool, SessionContext
from agent_framework._tools import ApprovalMode

from ._execute_code_tool import HyperlightExecuteCodeTool, SandboxRuntime
from ._types import AllowedDomain, AllowedDomainInput, FileMount, FileMountInput


class HyperlightCodeActProvider(ContextProvider):
    """Inject a Hyperlight-backed CodeAct surface using provider-owned tools."""

    DEFAULT_SOURCE_ID = "hyperlight_codeact"

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        approval_mode: ApprovalMode | None = None,
        workspace_root: str | Path | None = None,
        file_mounts: FileMountInput | Sequence[FileMountInput] | None = None,
        allowed_domains: AllowedDomainInput | Sequence[AllowedDomainInput] | None = None,
        backend: str = "wasm",
        module: str | None = "python_guest.path",
        module_path: str | None = None,
        _registry: SandboxRuntime | None = None,
    ) -> None:
        super().__init__(source_id)
        self._execute_code_tool = HyperlightExecuteCodeTool(
            tools=tools,
            approval_mode=approval_mode,
            workspace_root=workspace_root,
            file_mounts=file_mounts,
            allowed_domains=allowed_domains,
            backend=backend,
            module=module,
            module_path=module_path,
            _registry=_registry,
        )

    def add_tools(
        self,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]],
    ) -> None:
        """Add provider-owned sandbox tools."""
        self._execute_code_tool.add_tools(tools)

    def get_tools(self) -> list[FunctionTool]:
        """Return the provider-owned sandbox tools."""
        return self._execute_code_tool.get_tools()

    def remove_tool(self, name: str) -> None:
        """Remove one provider-owned sandbox tool by name."""
        self._execute_code_tool.remove_tool(name)

    def clear_tools(self) -> None:
        """Remove all provider-owned sandbox tools."""
        self._execute_code_tool.clear_tools()

    def add_file_mounts(self, file_mounts: FileMountInput | Sequence[FileMountInput]) -> None:
        """Add provider-managed file mounts."""
        self._execute_code_tool.add_file_mounts(file_mounts)

    def get_file_mounts(self) -> list[FileMount]:
        """Return the provider-managed file mounts."""
        return self._execute_code_tool.get_file_mounts()

    def remove_file_mount(self, mount_path: str) -> None:
        """Remove one provider-managed file mount."""
        self._execute_code_tool.remove_file_mount(mount_path)

    def clear_file_mounts(self) -> None:
        """Remove all provider-managed file mounts."""
        self._execute_code_tool.clear_file_mounts()

    def add_allowed_domains(self, domains: AllowedDomainInput | Sequence[AllowedDomainInput]) -> None:
        """Add provider-managed outbound allow-list entries."""
        self._execute_code_tool.add_allowed_domains(domains)

    def get_allowed_domains(self) -> list[AllowedDomain]:
        """Return the provider-managed outbound allow-list entries."""
        return self._execute_code_tool.get_allowed_domains()

    def remove_allowed_domain(self, domain: str) -> None:
        """Remove one provider-managed outbound allow-list entry."""
        self._execute_code_tool.remove_allowed_domain(domain)

    def clear_allowed_domains(self) -> None:
        """Remove all provider-managed outbound allow-list entries."""
        self._execute_code_tool.clear_allowed_domains()

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
