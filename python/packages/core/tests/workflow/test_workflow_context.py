# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from typing_extensions import Never

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    executor,
    handler,
)

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture

    from agent_framework._workflow._runner_context import InProcRunnerContext


@asynccontextmanager
async def make_context(
    executor_id: str = "exec",
) -> AsyncIterator[tuple[WorkflowContext[object], "InProcRunnerContext"]]:
    from agent_framework._workflow._runner_context import InProcRunnerContext
    from agent_framework._workflow._shared_state import SharedState

    runner_ctx = InProcRunnerContext()
    shared_state = SharedState()
    workflow_ctx: WorkflowContext[object] = WorkflowContext(
        executor_id,
        ["source"],
        shared_state,
        runner_ctx,
    )
    try:
        yield workflow_ctx, runner_ctx
    finally:
        await asyncio.sleep(0)


async def test_executor_cannot_emit_framework_lifecycle_event(caplog: "LogCaptureFixture") -> None:
    async with make_context() as (ctx, runner_ctx):
        caplog.clear()
        with caplog.at_level("WARNING"):
            await ctx.add_event(WorkflowStatusEvent(state=WorkflowRunState.IN_PROGRESS))

        events: list[WorkflowEvent] = await runner_ctx.drain_events()
        assert len(events) == 1
        assert type(events[0]).__name__ == "WorkflowWarningEvent"
        data = getattr(events[0], "data", None)
        assert isinstance(data, str)
        assert "reserved for framework lifecycle notifications" in data
        assert any("attempted to emit WorkflowStatusEvent" in message for message in list(caplog.messages))


async def test_executor_emits_normal_event() -> None:
    async with make_context() as (ctx, runner_ctx):
        # Create a normal event to test event emission
        await ctx.add_event(_TestEvent())

        events: list[WorkflowEvent] = await runner_ctx.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], _TestEvent)


class _TestEvent(WorkflowEvent):
    pass


async def test_workflow_context_type_annotations_no_parameter() -> None:
    # Test function-based executor
    @executor(id="func1")
    async def func1(text: str, ctx: WorkflowContext) -> None:
        await ctx.add_event(_TestEvent())

    wf = WorkflowBuilder().set_start_executor(func1).build()
    events = await wf.run("hello")
    test_events = [e for e in events if isinstance(e, _TestEvent)]
    assert len(test_events) == 1

    # Test class-based executor
    class _exec1(Executor):
        @handler
        async def func1(self, text: str, ctx: WorkflowContext) -> None:
            await ctx.add_event(_TestEvent())

    executor1 = _exec1(id="exec1")

    assert executor1.input_types == [str]
    assert executor1.output_types == []
    assert executor1.workflow_output_types == []

    wf2 = WorkflowBuilder().set_start_executor(executor1).build()
    events2 = await wf2.run("hello")
    test_events2 = [e for e in events2 if isinstance(e, _TestEvent)]
    assert len(test_events2) == 1


async def test_workflow_context_type_annotations_message_type_parameter() -> None:
    # Test function-based executor
    @executor(id="func1")
    async def func1(text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message("world")

    @executor(id="func2")
    async def func2(text: str, ctx: WorkflowContext) -> None:
        await ctx.add_event(_TestEvent(data=text))

    wf = WorkflowBuilder().add_edge(func1, func2).set_start_executor(func1).build()
    events = await wf.run("hello")
    test_events = [e for e in events if isinstance(e, _TestEvent)]
    assert len(test_events) == 1
    assert test_events[0].data == "world"

    # Test class-based executor
    class _exec1(Executor):
        @handler
        async def func1(self, text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message("world")

    class _exec2(Executor):
        @handler
        async def func2(self, text: str, ctx: WorkflowContext) -> None:
            await ctx.add_event(_TestEvent(data=text))

    executor1 = _exec1(id="exec1")
    executor2 = _exec2(id="exec2")

    assert executor1.input_types == [str]
    assert executor1.output_types == [str]
    assert executor1.workflow_output_types == []
    assert executor2.input_types == [str]
    assert executor2.output_types == []
    assert executor2.workflow_output_types == []

    wf2 = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()
    events2 = await wf2.run("hello")
    test_events2 = [e for e in events2 if isinstance(e, _TestEvent)]
    assert len(test_events2) == 1
    assert test_events2[0].data == "world"


async def test_workflow_context_type_annotations_message_and_output_type_parameters() -> None:
    # Test function-based executor
    @executor(id="func1")
    async def func1(text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message("world")

    @executor(id="func2")
    async def func2(text: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.add_event(_TestEvent(data=text))
        await ctx.yield_output(text)

    wf = WorkflowBuilder().add_edge(func1, func2).set_start_executor(func1).build()
    events = await wf.run("hello")
    outputs = events.get_outputs()
    assert len(outputs) == 1
    assert outputs[0] == "world"

    # Test class-based executor
    class _exec1(Executor):
        @handler
        async def func1(self, text: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message("world")

    class _exec2(Executor):
        @handler
        async def func2(self, text: str, ctx: WorkflowContext[Never, str]) -> None:
            await ctx.add_event(_TestEvent(data=text))
            await ctx.yield_output(text)

    executor1 = _exec1(id="exec1")
    executor2 = _exec2(id="exec2")

    assert executor1.input_types == [str]
    assert executor1.output_types == [str]
    assert executor1.workflow_output_types == []
    assert executor2.input_types == [str]
    assert executor2.output_types == []
    assert executor2.workflow_output_types == [str]

    wf2 = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()
    events2 = await wf2.run("hello")
    outputs2 = events2.get_outputs()
    assert len(outputs2) == 1
    assert outputs2[0] == "world"


async def test_workflow_context_type_annotations_any() -> None:
    class _exec1(Executor):
        @handler
        async def func1(self, text: str, ctx: WorkflowContext[Any]) -> None:
            await ctx.add_event(_TestEvent())
            await ctx.send_message(123)

    executor1 = _exec1(id="exec1")
    assert executor1.input_types == [str]
    assert executor1.output_types == [Any]

    class _exec2(Executor):
        @handler
        async def func2(self, number: int, ctx: WorkflowContext[Any, Any]) -> None:
            await ctx.add_event(_TestEvent())
            await ctx.send_message(456)
            await ctx.yield_output(3.14)

    executor2 = _exec2(id="exec2")
    assert executor2.input_types == [int]
    assert executor2.output_types == [Any]
    assert executor2.workflow_output_types == [Any]


async def test_workflow_context_missing_annotation_error() -> None:
    """Test that missing WorkflowContext annotation raises appropriate error."""
    import pytest

    # Test function-based executor with missing ctx annotation
    with pytest.raises(ValueError, match="must have a WorkflowContext"):

        @executor(id="bad_func")
        async def bad_func(text: str, ctx) -> None:  # type: ignore[no-untyped-def]
            pass

    # Test class-based executor with missing ctx annotation
    with pytest.raises(ValueError, match="must have a WorkflowContext"):

        class _BadExecutor(Executor):
            @handler
            async def bad_handler(self, text: str, ctx) -> None:  # type: ignore[no-untyped-def]
                pass


async def test_workflow_context_invalid_type_parameter_error() -> None:
    """Test that invalid type parameters like int values raise appropriate errors."""
    import pytest

    # Test function-based executor with invalid type parameter (int value instead of type)
    with pytest.raises(ValueError, match="invalid type entry"):

        @executor(id="bad_func")
        async def bad_func(text: str, ctx: WorkflowContext[123]) -> None:  # type: ignore[valid-type]
            pass

    # Test class-based executor with invalid type parameter
    with pytest.raises(ValueError, match="invalid type entry"):

        class _BadExecutor(Executor):
            @handler
            async def bad_handler(self, text: str, ctx: WorkflowContext[456]) -> None:  # type: ignore[valid-type]
                pass

    # Test two-parameter WorkflowContext with invalid workflow output type
    with pytest.raises(ValueError, match="invalid type entry"):

        @executor(id="bad_func2")
        async def bad_func2(text: str, ctx: WorkflowContext[str, 789]) -> None:  # type: ignore[valid-type]
            pass
