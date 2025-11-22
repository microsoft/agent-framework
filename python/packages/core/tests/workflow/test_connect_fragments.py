# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import pytest

from agent_framework import (
    ConnectionHandle,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowConnection,
    WorkflowContext,
    handler,
)


class _Source(Executor):
    @handler
    async def start(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text)


class _Upper(Executor):
    @handler
    async def elevate(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text.upper())


class _AppendBang(Executor):
    @handler
    async def punctuate(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"{text}!")


class _Sink(Executor):
    @handler
    async def finish(self, text: str, ctx: WorkflowContext[Any, str]) -> None:
        await ctx.yield_output(text)


async def test_connect_merges_fragments_and_runs() -> None:
    connection_one = (
        WorkflowBuilder()
        .add_edge(_Source(id="src"), _Upper(id="up"))
        .set_start_executor("src")
        .as_connection()
    )

    connection_two = (
        WorkflowBuilder()
        .add_edge(_Source(id="forward"), _AppendBang(id="bang"))
        .set_start_executor("forward")
        .as_connection()
    )

    sink = _Sink(id="sink")
    builder = WorkflowBuilder()
    handle_one = builder.add_connection(connection_one, prefix="f1")
    handle_two = builder.add_connection(connection_two, prefix="f2")
    builder.connect(handle_one.output_points[0], handle_two.start_id)
    builder.connect(handle_two.output_points[0], sink)
    builder.set_start_executor(handle_one.start_id)

    workflow: Workflow = builder.build()
    result = await workflow.run("hello")

    assert result.get_outputs() == ["HELLO!"]
    assert any(exec_id.startswith("f1/") for exec_id in workflow.executors)
    assert any(exec_id.startswith("f2/") for exec_id in workflow.executors)


async def test_connect_detects_id_collision() -> None:
    connection = (
        WorkflowBuilder()
        .add_edge(_Source(id="dup"), _Upper(id="dup_upper"))
        .set_start_executor("dup")
        .as_connection()
    )

    builder = WorkflowBuilder()
    builder.add_edge(_Source(id="dup"), _Sink(id="terminal"))
    builder.set_start_executor("dup")

    with pytest.raises(ValueError):
        builder.add_connection(connection)


async def test_workflow_as_connection_round_trip() -> None:
    inner = (
        WorkflowBuilder()
        .add_edge(_Source(id="inner_src"), _Sink(id="inner_sink"))
        .set_start_executor("inner_src")
        .build()
    )

    connection = inner.as_connection(prefix="wrapped")
    outer = WorkflowBuilder()
    handle = outer.add_connection(connection)
    outer.set_start_executor(handle.start_id)
    workflow = outer.build()

    result = await workflow.run("pipeline")
    assert result.get_outputs() == ["pipeline"]
    assert any(exec_id.startswith("wrapped/") for exec_id in workflow.executors)
