# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunResult,
    executor,
    handler,
)
from agent_framework_hosting import WorkflowState
from mcp import types
from pytest import raises

from agent_framework_hosting_mcp import WorkflowMCPTool


@dataclass
class WorkflowInput:
    """Input exposed as MCP tool arguments."""

    text: str
    repeat: int


def create_workflow():
    """Create a workflow with an object-shaped input."""

    @executor(id="repeat")
    async def repeat_text(value: WorkflowInput, ctx: WorkflowContext[object, str]) -> None:
        await ctx.yield_output(value.text * value.repeat)

    return WorkflowBuilder(
        start_executor=repeat_text,
        name="Repeat Workflow",
        description="Repeat text a requested number of times.",
        output_from=[repeat_text],
    ).build()


async def test_workflow_tool_derives_object_schema_and_runs_workflow() -> None:
    tool: WorkflowMCPTool[Any] = WorkflowMCPTool(
        WorkflowState(create_workflow, cache_target=False),
        name="repeat_text",
    )

    definition = (await tool.list_tools())[0]
    result = await tool.call_tool("repeat_text", {"text": "go", "repeat": 2})

    assert definition.description == "Repeat text a requested number of times."
    assert definition.inputSchema["type"] == "object"
    assert definition.inputSchema["properties"]["text"]["type"] == "string"
    assert definition.inputSchema["properties"]["repeat"]["type"] == "integer"
    assert set(definition.inputSchema["required"]) == {"text", "repeat"}
    assert result == [types.TextContent(type="text", text="gogo")]


async def test_workflow_tool_wraps_primitive_input() -> None:
    @executor(id="uppercase")
    async def uppercase(value: str, ctx: WorkflowContext[object, str]) -> None:
        await ctx.yield_output(value.upper())

    workflow = WorkflowBuilder(start_executor=uppercase, name="uppercase", output_from=[uppercase]).build()
    tool: WorkflowMCPTool[Any] = WorkflowMCPTool(workflow, argument_name="text")

    definition = (await tool.list_tools())[0]
    result = await tool.call_tool("uppercase", {"text": "hello"})

    assert definition.inputSchema == {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }
    assert result == [types.TextContent(type="text", text="HELLO")]


async def test_workflow_tool_serializes_structured_output_as_json_text() -> None:
    @executor(id="structured")
    async def structured(value: str, ctx: WorkflowContext[object, dict[str, str]]) -> None:
        await ctx.yield_output({"value": value})

    workflow = WorkflowBuilder(start_executor=structured, name="structured", output_from=[structured]).build()
    tool: WorkflowMCPTool[Any] = WorkflowMCPTool(workflow)

    result = await tool.call_tool("structured", {"input": "hello"})

    assert result == [types.TextContent(type="text", text='{"value":"hello"}')]


def test_workflow_tool_rejects_unhandled_external_input_requests() -> None:
    workflow = create_workflow()
    tool: WorkflowMCPTool[Any] = WorkflowMCPTool(workflow)
    result = WorkflowRunResult([
        WorkflowEvent.request_info(
            request_id="approval",
            source_executor_id="review",
            request_data={"question": "Approve?"},
            response_type=bool,
        )
    ])

    with raises(ValueError, match="requires external input"):
        tool.mcp_from_run(result)


def test_workflow_tool_rejects_multiple_start_input_types() -> None:
    class MultipleInputs(Executor):
        @handler
        async def handle_text(self, value: str, ctx: WorkflowContext[object, str]) -> None:
            await ctx.yield_output(value)

        @handler
        async def handle_number(self, value: int, ctx: WorkflowContext[object, str]) -> None:
            await ctx.yield_output(str(value))

    workflow = WorkflowBuilder(
        start_executor=MultipleInputs(id="multiple"),
        name="multiple",
        output_from="all",
    ).build()
    tool: WorkflowMCPTool[Any] = WorkflowMCPTool(workflow)

    with raises(ValueError, match="exactly one"):
        tool._tool_for_workflow(workflow)  # pyright: ignore[reportPrivateUsage]
