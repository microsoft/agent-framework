# Copyright (c) Microsoft. All rights reserved.

"""Workflow-backed MCP tool adapter for app-owned servers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Generic, TypeVar, cast

from agent_framework import AgentResponse, Message, Workflow, WorkflowRunResult
from agent_framework_hosting import WorkflowState
from mcp import types
from pydantic import TypeAdapter

from ._conversion import mcp_from_run

WorkflowT = TypeVar("WorkflowT", bound=Workflow)


class MCPWorkflowTool(Generic[WorkflowT]):
    """Expose one Agent Framework workflow through an app-owned MCP server.

    The adapter derives the native MCP input schema from the workflow's start
    executor. It does not create an MCP server, register handlers, choose a
    transport, or manage workflow checkpoints and human-in-the-loop responses.
    """

    def __init__(
        self,
        target: WorkflowT | WorkflowState[WorkflowT],
        *,
        name: str | None = None,
        description: str | None = None,
        argument_name: str = "input",
    ) -> None:
        """Create a workflow-backed MCP tool adapter.

        Args:
            target: Workflow target or existing ``WorkflowState``. Use a
                ``WorkflowState`` factory with ``cache_target=False`` when
                concurrent calls need independent workflow instances.

        Keyword Args:
            name: MCP tool name override. Defaults to a sanitized workflow name.
            description: MCP tool description override. Defaults to the workflow description.
            argument_name: MCP property used when the workflow input is not an object.
        """
        self.state = target if isinstance(target, WorkflowState) else WorkflowState(target)
        self._name = name
        self._description = description
        self.argument_name = argument_name

    async def list_tools(self) -> list[types.Tool]:
        """Return the native MCP tool definition for the target workflow."""
        workflow = await self.state.get_target()
        return [self._tool_for_workflow(workflow)]

    def _tool_for_workflow(self, workflow: WorkflowT) -> types.Tool:
        tool_name = self._name
        if tool_name is None:
            tool_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", workflow.name).strip("_") or "workflow"

        input_adapter = self._input_adapter(workflow)
        input_schema = input_adapter.json_schema()
        if input_schema.get("type") != "object":
            input_schema = {
                "type": "object",
                "properties": {self.argument_name: input_schema},
                "required": [self.argument_name],
                "additionalProperties": False,
            }

        return types.Tool(
            name=tool_name,
            description=self._description if self._description is not None else workflow.description or "",
            inputSchema=input_schema,
        )

    def _input_adapter(self, workflow: WorkflowT) -> TypeAdapter[Any]:
        input_types = workflow.get_start_executor().input_types
        if len(input_types) != 1:
            raise ValueError(
                f"MCP workflow tools require exactly one start-executor input type; found {len(input_types)}."
            )
        return TypeAdapter(input_types[0])

    def _workflow_input(self, workflow: WorkflowT, arguments: Mapping[str, Any] | None) -> Any:
        input_adapter = self._input_adapter(workflow)
        input_schema = input_adapter.json_schema()
        if input_schema.get("type") == "object":
            return input_adapter.validate_python(dict(arguments or {}))
        if arguments is None or self.argument_name not in arguments:
            raise ValueError(f"MCP tool arguments must include '{self.argument_name}'.")
        return input_adapter.validate_python(arguments[self.argument_name])

    def mcp_from_run(self, result: WorkflowRunResult) -> list[types.ContentBlock]:
        """Convert completed workflow outputs into native MCP content blocks."""
        if result.get_request_info_events():
            raise ValueError(
                "The workflow requires external input. MCPWorkflowTool does not manage "
                "human-in-the-loop continuation; handle it in the application contract."
            )

        blocks: list[types.ContentBlock] = []
        for output in result.get_outputs():
            if isinstance(output, (AgentResponse, Message)):
                blocks.extend(mcp_from_run(cast("AgentResponse[Any] | Message", output)))
            elif isinstance(output, str):
                blocks.append(types.TextContent(type="text", text=output))
            else:
                blocks.append(
                    types.TextContent(
                        type="text",
                        text=TypeAdapter[Any](Any).dump_json(output, serialize_as_any=True).decode(),
                    )
                )
        return blocks

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
    ) -> list[types.ContentBlock]:
        """Run the target workflow for a native MCP ``call_tool`` handler.

        Args:
            name: MCP tool name selected by the client.
            arguments: Native MCP tool arguments.

        Returns:
            Native MCP content blocks for the completed workflow result.

        Raises:
            ValueError: If the tool name or workflow input contract is invalid.
        """
        workflow = await self.state.get_target()
        tool = self._tool_for_workflow(workflow)
        if name != tool.name:
            raise ValueError(f"Unknown MCP tool: {name}")

        result = await workflow.run(self._workflow_input(workflow, arguments), stream=False)
        return self.mcp_from_run(result)
