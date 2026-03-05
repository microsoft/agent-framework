# Copyright (c) Microsoft. All rights reserved.

"""Tests for the functional workflow API (@workflow, @step, RunContext)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from agent_framework import (
    AgentResponseUpdate,
    FunctionalWorkflow,
    InMemoryCheckpointStorage,
    RunContext,
    StepWrapper,
    WorkflowEvent,
    WorkflowRunResult,
    WorkflowRunState,
    step,
    workflow,
)
from agent_framework._workflows._functional import (
    RunContext as _RunContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@step
async def add_one(x: int) -> int:
    return x + 1


@step
async def double(x: int) -> int:
    return x * 2


@step
async def to_upper(s: str) -> str:
    return s.upper()


@step(name="custom_name")
async def named_step(x: int) -> int:
    return x + 10


@step
async def failing_step(x: int) -> int:
    raise ValueError(f"step failed with {x}")


# ---------------------------------------------------------------------------
# Basic execution
# ---------------------------------------------------------------------------


class TestBasicExecution:
    async def test_simple_sequential_pipeline(self):
        @workflow
        async def pipeline(x: int) -> int:
            a = await add_one(x)
            return await double(a)

        result = await pipeline.run(5)
        assert isinstance(result, WorkflowRunResult)
        outputs = result.get_outputs()
        assert outputs == [12]  # (5+1)*2

    async def test_workflow_with_string_data(self):
        @workflow
        async def upper_pipeline(text: str) -> str:
            return await to_upper(text)

        result = await upper_pipeline.run("hello")
        assert result.get_outputs() == ["HELLO"]

    async def test_workflow_returns_result(self):
        @workflow
        async def simple(x: int) -> int:
            return await add_one(x)

        result = await simple.run(10)
        assert result.get_outputs() == [11]

    async def test_workflow_name_defaults_to_function_name(self):
        @workflow
        async def my_pipeline(x: int) -> int:
            return x

        assert my_pipeline.name == "my_pipeline"

    async def test_workflow_custom_name(self):
        @workflow(name="custom_wf", description="A test workflow")
        async def wf(x: int) -> int:
            return x

        assert wf.name == "custom_wf"
        assert wf.description == "A test workflow"


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


class TestEventEmission:
    async def test_step_events_emitted(self):
        @workflow
        async def pipeline(x: int) -> int:
            return await add_one(x)

        result = await pipeline.run(5)
        event_types = [e.type for e in result]
        assert "executor_invoked" in event_types
        assert "executor_completed" in event_types
        assert "output" in event_types

    async def test_step_events_carry_executor_id(self):
        @workflow
        async def pipeline(x: int) -> int:
            return await add_one(x)

        result = await pipeline.run(5)
        invoked_events = [e for e in result if e.type == "executor_invoked"]
        assert len(invoked_events) == 1
        assert invoked_events[0].executor_id == "add_one"

        completed_events = [e for e in result if e.type == "executor_completed"]
        assert len(completed_events) == 1
        assert completed_events[0].executor_id == "add_one"
        assert completed_events[0].data == 6

    async def test_status_events_in_timeline(self):
        @workflow
        async def pipeline(x: int) -> int:
            return x

        result = await pipeline.run(1)
        states = [e.state for e in result.status_timeline()]
        assert WorkflowRunState.IN_PROGRESS in states
        assert WorkflowRunState.IDLE in states

    async def test_final_state_is_idle(self):
        @workflow
        async def pipeline(x: int) -> int:
            return x

        result = await pipeline.run(1)
        assert result.get_final_state() == WorkflowRunState.IDLE

    async def test_custom_event(self):
        from agent_framework import WorkflowEvent

        @workflow
        async def pipeline(x: int, ctx: RunContext) -> int:
            await ctx.add_event(WorkflowEvent.emit("pipeline", "custom_data"))
            return x

        result = await pipeline.run(1)
        data_events = [e for e in result if e.type == "data"]
        assert len(data_events) == 1
        assert data_events[0].data == "custom_data"


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    async def test_parallel_tasks_with_gather(self):
        @step
        async def slow_add(x: int) -> int:
            await asyncio.sleep(0.01)
            return x + 1

        @step
        async def slow_double(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 2

        @workflow
        async def parallel_wf(x: int) -> list[int]:
            a, b = await asyncio.gather(slow_add(x), slow_double(x))
            return [a, b]

        result = await parallel_wf.run(5)
        outputs = result.get_outputs()
        assert outputs == [[6, 10]]

    async def test_parallel_events_all_emitted(self):
        @step
        async def task_a(x: int) -> int:
            return x + 1

        @step
        async def task_b(x: int) -> int:
            return x * 2

        @workflow
        async def par_wf(x: int) -> tuple[int, int]:
            a, b = await asyncio.gather(task_a(x), task_b(x))
            return (a, b)

        result = await par_wf.run(3)
        invoked = [e for e in result if e.type == "executor_invoked"]
        completed = [e for e in result if e.type == "executor_completed"]
        assert len(invoked) == 2
        assert len(completed) == 2


# ---------------------------------------------------------------------------
# HITL (request_info / resume)
# ---------------------------------------------------------------------------


class TestHITL:
    async def test_request_info_interrupts(self):
        @workflow
        async def review_wf(doc: str, ctx: RunContext) -> str:
            feedback = await ctx.request_info({"draft": doc}, response_type=str, request_id="req1")
            return f"Final: {feedback}"

        # Phase 1: should interrupt with pending request
        result = await review_wf.run("my doc")
        assert result.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
        request_events = result.get_request_info_events()
        assert len(request_events) == 1
        assert request_events[0].request_id == "req1"

    async def test_request_info_resume(self):
        @workflow
        async def review_wf(doc: str, ctx: RunContext) -> str:
            feedback = await ctx.request_info({"draft": doc}, response_type=str, request_id="req1")
            return f"Final: {feedback}"

        # Phase 1
        result1 = await review_wf.run("my doc")
        assert result1.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

        # Phase 2: resume with response
        result2 = await review_wf.run(responses={"req1": "Looks great!"})
        outputs = result2.get_outputs()
        assert outputs == ["Final: Looks great!"]
        assert result2.get_final_state() == WorkflowRunState.IDLE

    async def test_untyped_ctx_parameter(self):
        """ctx is injected by parameter name even without a RunContext annotation."""

        @workflow  # pyright: ignore[reportUnknownArgumentType]
        async def review_wf(doc: str, ctx) -> str:  # pyright: ignore[reportUnknownParameterType,reportMissingParameterType]
            feedback: str = await ctx.request_info({"draft": doc}, response_type=str, request_id="req1")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            return f"Final: {feedback}"

        result1 = await review_wf.run("my doc")
        assert result1.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

        result2 = await review_wf.run(responses={"req1": "LGTM"})
        assert result2.get_outputs() == ["Final: LGTM"]

    async def test_multiple_sequential_interrupts(self):
        @workflow
        async def multi_hitl(data: str, ctx: RunContext) -> str:
            r1 = await ctx.request_info("step1", response_type=str, request_id="r1")
            r2 = await ctx.request_info("step2", response_type=str, request_id="r2")
            return f"{r1}+{r2}"

        # Phase 1: first interrupt
        result1 = await multi_hitl.run("start")
        assert len(result1.get_request_info_events()) == 1
        assert result1.get_request_info_events()[0].request_id == "r1"

        # Phase 2: respond to first, hits second
        result2 = await multi_hitl.run(responses={"r1": "A"})
        assert len(result2.get_request_info_events()) == 1
        assert result2.get_request_info_events()[0].request_id == "r2"

        # Phase 3: respond to second
        result3 = await multi_hitl.run(responses={"r1": "A", "r2": "B"})
        assert result3.get_outputs() == ["A+B"]

    async def test_request_info_auto_generates_id(self):
        @workflow
        async def auto_id_wf(x: int, ctx: RunContext) -> None:
            await ctx.request_info("need data", response_type=str)

        result = await auto_id_wf.run(1)
        events = result.get_request_info_events()
        assert len(events) == 1
        assert events[0].request_id  # should be a non-empty uuid string


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_step_failure_propagates(self):
        @workflow
        async def failing_wf(x: int) -> None:
            await failing_step(x)

        with pytest.raises(ValueError, match="step failed with 42"):
            await failing_wf.run(42)

    async def test_step_failure_emits_executor_failed(self):
        @workflow
        async def failing_wf(x: int) -> None:
            await failing_step(x)

        # Use stream to collect events before the raise
        stream = failing_wf.run(42, stream=True)
        events: list[WorkflowEvent[object]] = []
        with pytest.raises(ValueError):
            async for event in stream:
                events.append(event)

        failed_events = [e for e in events if e.type == "executor_failed"]
        assert len(failed_events) == 1
        assert failed_events[0].executor_id == "failing_step"

    async def test_workflow_failure_emits_failed_status(self):
        @workflow
        async def bad_wf(x: int) -> None:
            raise RuntimeError("workflow broke")

        stream = bad_wf.run(42, stream=True)
        events: list[WorkflowEvent[object]] = []
        with pytest.raises(RuntimeError, match="workflow broke"):
            async for event in stream:
                events.append(event)

        failed_events = [e for e in events if e.type == "failed"]
        assert len(failed_events) == 1
        status_events = [e for e in events if e.type == "status"]
        assert any(e.state == WorkflowRunState.FAILED for e in status_events)

    async def test_invalid_params_message_and_responses(self):
        @workflow
        async def wf(x: int) -> None:
            pass

        with pytest.raises(ValueError, match="Cannot provide both"):
            await wf.run("hello", responses={"r1": "val"})

    async def test_invalid_params_message_and_checkpoint(self):
        @workflow
        async def wf(x: int) -> None:
            pass

        with pytest.raises(ValueError, match="Cannot provide both"):
            await wf.run("hello", checkpoint_id="abc")

    async def test_invalid_params_nothing(self):
        @workflow
        async def wf(x: int) -> None:
            pass

        with pytest.raises(ValueError, match="Must provide at least one"):
            await wf.run()


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


class TestStreaming:
    async def test_streaming_yields_events(self):
        @workflow
        async def pipeline(x: int) -> int:
            return await add_one(x)

        stream = pipeline.run(5, stream=True)
        events: list[WorkflowEvent[object]] = []
        async for event in stream:
            events.append(event)

        event_types = [e.type for e in events]
        assert "started" in event_types
        assert "executor_invoked" in event_types
        assert "executor_completed" in event_types
        assert "output" in event_types

    async def test_streaming_final_response(self):
        @workflow
        async def pipeline(x: int) -> int:
            return await add_one(x)

        stream = pipeline.run(5, stream=True)
        final = await stream.get_final_response()
        assert isinstance(final, WorkflowRunResult)
        assert final.get_outputs() == [6]

    async def test_streaming_context_reports_streaming(self):
        streaming_flag = None

        @workflow
        async def wf(x: int, ctx: RunContext) -> int:
            nonlocal streaming_flag
            streaming_flag = ctx.is_streaming()
            return x

        stream = wf.run(1, stream=True)
        await stream.get_final_response()
        assert streaming_flag is True

        streaming_flag = None
        await wf.run(1)
        assert streaming_flag is False


# ---------------------------------------------------------------------------
# Step passthrough outside workflow
# ---------------------------------------------------------------------------


class TestStepPassthrough:
    async def test_step_works_outside_workflow(self):
        result = await add_one(10)
        assert result == 11

    async def test_named_step_outside_workflow(self):
        result = await named_step(5)
        assert result == 15

    def test_step_wrapper_name(self):
        assert add_one.name == "add_one"
        assert named_step.name == "custom_name"

    def test_step_wrapper_is_step_wrapper(self):
        assert isinstance(add_one, StepWrapper)
        assert isinstance(named_step, StepWrapper)


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestStateManagement:
    async def test_get_set_state(self):
        @workflow
        async def stateful_wf(x: int, ctx: RunContext) -> int:
            ctx.set_state("counter", x)
            return ctx.get_state("counter")

        result = await stateful_wf.run(42)
        assert result.get_outputs() == [42]

    async def test_get_state_default(self):
        @workflow
        async def wf(x: int, ctx: RunContext) -> str:
            return ctx.get_state("missing", "default_val")

        result = await wf.run(1)
        assert result.get_outputs() == ["default_val"]


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------


class TestCheckpointing:
    async def test_checkpoint_save_and_restore(self):
        storage = InMemoryCheckpointStorage()

        @step
        async def expensive(x: int) -> int:
            return x * 100

        @workflow(checkpoint_storage=storage)
        async def ckpt_wf(x: int) -> int:
            return await expensive(x)

        result = await ckpt_wf.run(5)
        assert result.get_outputs() == [500]

        # Verify checkpoints were saved: 1 per-step + 1 final
        checkpoints = await storage.list_checkpoints(workflow_name="ckpt_wf")
        assert len(checkpoints) == 2

    async def test_checkpoint_runtime_storage_override(self):
        storage = InMemoryCheckpointStorage()

        @step
        async def compute(x: int) -> int:
            return x + 1

        @workflow
        async def wf(x: int) -> int:
            return await compute(x)

        result = await wf.run(10, checkpoint_storage=storage)
        assert result.get_outputs() == [11]
        # 1 per-step checkpoint + 1 final checkpoint
        checkpoints = await storage.list_checkpoints(workflow_name="wf")
        assert len(checkpoints) == 2

    async def test_checkpoint_restore_replays_cached_tasks(self):
        storage = InMemoryCheckpointStorage()
        call_count = 0

        @step
        async def counting_task(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x + 1

        @workflow(checkpoint_storage=storage)
        async def wf(x: int) -> int:
            return await counting_task(x)

        # First run
        result1 = await wf.run(5)
        assert result1.get_outputs() == [6]
        assert call_count == 1

        # Get checkpoint ID
        checkpoints = await storage.list_checkpoints(workflow_name="wf")
        ckpt_id = checkpoints[0].checkpoint_id

        # Restore — step should replay from cache
        result2 = await wf.run(checkpoint_id=ckpt_id)
        assert result2.get_outputs() == [6]
        assert call_count == 1  # not called again

    async def test_checkpoint_hitl_resume(self):
        storage = InMemoryCheckpointStorage()

        @workflow(checkpoint_storage=storage)
        async def hitl_wf(doc: str, ctx: RunContext) -> str:
            feedback = await ctx.request_info({"draft": doc}, response_type=str, request_id="req1")
            return f"Done: {feedback}"

        # Phase 1: interrupt
        result1 = await hitl_wf.run("draft text")
        assert result1.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

        # Get checkpoint
        checkpoints = await storage.list_checkpoints(workflow_name="hitl_wf")
        ckpt_id = checkpoints[0].checkpoint_id

        # Phase 2: restore and respond
        result2 = await hitl_wf.run(checkpoint_id=ckpt_id, responses={"req1": "Approved!"})
        assert result2.get_outputs() == ["Done: Approved!"]

    async def test_checkpoint_without_storage_raises(self):
        @workflow
        async def wf(x: int) -> int:
            return x

        with pytest.raises(ValueError, match="checkpoint_storage"):
            await wf.run(checkpoint_id="nonexistent")

    async def test_checkpoint_preserves_state(self):
        storage = InMemoryCheckpointStorage()

        @workflow(checkpoint_storage=storage)
        async def stateful_wf(x: int, ctx: RunContext) -> str:
            ctx.set_state("key", "value")
            feedback = await ctx.request_info("need info", response_type=str, request_id="r1")
            val = ctx.get_state("key")
            return f"{val}:{feedback}"

        # Phase 1
        result1 = await stateful_wf.run(1)
        assert result1.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

        # Phase 2: restore and respond
        checkpoints = await storage.list_checkpoints(workflow_name="stateful_wf")
        ckpt_id = checkpoints[0].checkpoint_id

        result2 = await stateful_wf.run(checkpoint_id=ckpt_id, responses={"r1": "hello"})
        assert result2.get_outputs() == ["value:hello"]

    async def test_per_step_checkpoint_enables_crash_recovery(self):
        """Simulates crash recovery: step 1 completes and is checkpointed,
        then the workflow crashes in step 2. Restoring from the per-step
        checkpoint should replay step 1 from cache without re-executing it."""
        storage = InMemoryCheckpointStorage()
        step1_calls = 0
        step2_calls = 0

        @step
        async def slow_step1(x: int) -> int:
            nonlocal step1_calls
            step1_calls += 1
            return x + 10

        @step
        async def crashing_step2(x: int) -> int:
            nonlocal step2_calls
            step2_calls += 1
            if step2_calls == 1:
                raise RuntimeError("simulated crash")
            return x * 2

        @workflow(checkpoint_storage=storage)
        async def crash_wf(x: int) -> int:
            a = await slow_step1(x)
            return await crashing_step2(a)

        # First run: step1 succeeds and checkpoints, step2 crashes
        with pytest.raises(RuntimeError, match="simulated crash"):
            await crash_wf.run(5)

        assert step1_calls == 1
        assert step2_calls == 1

        # A per-step checkpoint was saved after step1 completed
        checkpoints = await storage.list_checkpoints(workflow_name="crash_wf")
        assert len(checkpoints) >= 1
        ckpt_id = checkpoints[0].checkpoint_id

        # Restore from checkpoint: step1 replays from cache, step2 runs fresh
        result = await crash_wf.run(checkpoint_id=ckpt_id)
        assert result.get_outputs() == [30]  # (5+10)*2
        assert step1_calls == 1  # NOT called again — replayed from cache
        assert step2_calls == 2  # called again, succeeds this time

    async def test_per_step_checkpoint_chain(self):
        """Each step creates a new checkpoint chained to the previous one."""
        storage = InMemoryCheckpointStorage()

        @step
        async def s1(x: int) -> int:
            return x + 1

        @step
        async def s2(x: int) -> int:
            return x + 2

        @step
        async def s3(x: int) -> int:
            return x + 3

        @workflow(checkpoint_storage=storage)
        async def multi_step_wf(x: int) -> int:
            a = await s1(x)
            b = await s2(a)
            return await s3(b)

        result = await multi_step_wf.run(0)
        assert result.get_outputs() == [6]  # 0+1+2+3

        # 3 per-step checkpoints + 1 final = 4
        checkpoints = await storage.list_checkpoints(workflow_name="multi_step_wf")
        assert len(checkpoints) == 4

    async def test_no_checkpoint_on_cache_hit(self):
        """During replay, cached steps should NOT create additional checkpoints."""
        storage = InMemoryCheckpointStorage()

        @step
        async def compute(x: int) -> int:
            return x + 1

        @workflow(checkpoint_storage=storage)
        async def wf(x: int) -> int:
            return await compute(x)

        # First run: 1 per-step + 1 final = 2 checkpoints
        await wf.run(5)
        checkpoints = await storage.list_checkpoints(workflow_name="wf")
        assert len(checkpoints) == 2
        ckpt_id = checkpoints[0].checkpoint_id

        # Restore: step replays from cache (no new per-step checkpoint),
        # but final checkpoint still saved = 1 new checkpoint
        await wf.run(checkpoint_id=ckpt_id)
        checkpoints = await storage.list_checkpoints(workflow_name="wf")
        assert len(checkpoints) == 3  # 2 from first run + 1 final from restore


# ---------------------------------------------------------------------------
# Branching / control flow
# ---------------------------------------------------------------------------


class TestControlFlow:
    async def test_if_else_branching(self):
        @dataclass
        class Classification:
            is_spam: bool

        @step
        async def classify(text: str) -> Classification:
            return Classification(is_spam="spam" in text.lower())

        @step
        async def process_normal(text: str) -> str:
            return f"processed: {text}"

        @step
        async def quarantine(text: str) -> str:
            return f"quarantined: {text}"

        @workflow
        async def email_pipeline(email: str) -> str:
            cl = await classify(email)
            if cl.is_spam:
                result = await quarantine(email)
            else:
                result = await process_normal(email)
            return result

        result_spam = await email_pipeline.run("Buy spam now!")
        assert result_spam.get_outputs() == ["quarantined: Buy spam now!"]

        result_normal = await email_pipeline.run("Hello friend")
        assert result_normal.get_outputs() == ["processed: Hello friend"]


# ---------------------------------------------------------------------------
# Nested workflow calls
# ---------------------------------------------------------------------------


class TestNestedWorkflows:
    async def test_nested_workflow_as_task(self):
        @step
        async def step_a(x: int) -> int:
            return x + 1

        @workflow
        async def inner_wf(x: int) -> int:
            return await step_a(x)

        @step
        async def call_inner(x: int) -> int:
            result = await inner_wf.run(x)
            return result.get_outputs()[0]

        @workflow
        async def outer_wf(x: int) -> int:
            return await call_inner(x)

        result = await outer_wf.run(5)
        assert result.get_outputs() == [6]


# ---------------------------------------------------------------------------
# as_agent()
# ---------------------------------------------------------------------------


class TestAsAgent:
    async def test_as_agent_returns_agent(self):
        @workflow
        async def wf(x: int) -> str:
            return f"result: {x}"

        agent = wf.as_agent()
        assert agent.name == "wf"

    async def test_as_agent_custom_name(self):
        @workflow
        async def wf(x: int) -> int:
            return x

        agent = wf.as_agent(name="my_agent")
        assert agent.name == "my_agent"

    async def test_as_agent_run(self):
        @workflow
        async def wf(x: int) -> int:
            return await add_one(x)

        agent = wf.as_agent()
        response = await agent.run(10)
        assert response.text == "11"

    async def test_as_agent_run_streaming(self):
        @workflow
        async def wf(x: int) -> str:
            return f"result: {x}"

        agent = wf.as_agent()
        stream = agent.run(10, stream=True)
        updates: list[AgentResponseUpdate] = []
        async for update in stream:
            updates.append(update)
        assert len(updates) == 1
        assert updates[0].text == "result: 10"

        response = await stream.get_final_response()
        assert len(response.messages) >= 1

    async def test_as_agent_has_id_and_description(self):
        @workflow(description="A test workflow")
        async def wf(x: int) -> int:
            return x

        agent = wf.as_agent(name="my_agent")
        assert agent.id == "FunctionalWorkflowAgent_my_agent"
        assert agent.description == "A test workflow"


# ---------------------------------------------------------------------------
# Concurrent execution guard
# ---------------------------------------------------------------------------


class TestConcurrencyGuard:
    async def test_concurrent_run_raises(self):
        @workflow
        async def slow_wf(x: int) -> int:
            await asyncio.sleep(0.1)
            return x

        # Start first run
        stream = slow_wf.run(1, stream=True)

        # Try to start second run while first is active
        with pytest.raises(RuntimeError, match="already running"):
            slow_wf.run(2, stream=True)

        # Consume the stream to clean up
        await stream.get_final_response()

    async def test_run_after_completion(self):
        @workflow
        async def wf(x: int) -> int:
            return x

        result1 = await wf.run(1)
        assert result1.get_outputs() == [1]

        # Should be able to run again after first completes
        result2 = await wf.run(2)
        assert result2.get_outputs() == [2]


# ---------------------------------------------------------------------------
# Decorator forms
# ---------------------------------------------------------------------------


class TestDecoratorForms:
    def test_step_bare_decorator(self):
        @step
        async def my_step(x: int) -> int:
            return x

        assert isinstance(my_step, StepWrapper)
        assert my_step.name == "my_step"

    def test_step_with_name(self):
        @step(name="renamed")
        async def my_step(x: int) -> int:
            return x

        assert isinstance(my_step, StepWrapper)
        assert my_step.name == "renamed"

    def test_workflow_bare_decorator(self):
        @workflow
        async def my_wf(x: int) -> None:
            pass

        assert isinstance(my_wf, FunctionalWorkflow)
        assert my_wf.name == "my_wf"

    def test_workflow_with_params(self):
        @workflow(name="custom", description="desc")
        async def my_wf(x: int) -> None:
            pass

        assert isinstance(my_wf, FunctionalWorkflow)
        assert my_wf.name == "custom"
        assert my_wf.description == "desc"


# ---------------------------------------------------------------------------
# include_status_events
# ---------------------------------------------------------------------------


class TestIncludeStatusEvents:
    async def test_status_events_excluded_by_default(self):
        @workflow
        async def wf(x: int) -> int:
            return x

        result = await wf.run(1)
        status_in_list = [e for e in result if e.type == "status"]
        assert len(status_in_list) == 0

    async def test_status_events_included_when_requested(self):
        @workflow
        async def wf(x: int) -> int:
            return x

        result = await wf.run(1, include_status_events=True)
        status_in_list = [e for e in result if e.type == "status"]
        assert len(status_in_list) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_workflow_with_no_tasks(self):
        @workflow
        async def no_tasks(x: int) -> int:
            return x * 2

        result = await no_tasks.run(5)
        assert result.get_outputs() == [10]

    async def test_workflow_with_no_output(self):
        @workflow
        async def silent_wf(x: int) -> None:
            pass  # returns None — no output emitted

        result = await silent_wf.run(5)
        assert result.get_outputs() == []

    async def test_return_value_auto_yields_output(self):
        """Returning a non-None value automatically emits it as an output."""

        @workflow
        async def wf(x: int) -> int:
            return x * 3

        result = await wf.run(5)
        assert result.get_outputs() == [15]

    async def test_step_called_multiple_times(self):
        @workflow
        async def wf(x: int) -> int:
            a = await add_one(x)
            b = await add_one(a)
            return await add_one(b)

        result = await wf.run(0)
        assert result.get_outputs() == [3]  # 0+1+1+1

        # Should have 3 invoked and 3 completed events for add_one
        invoked = [e for e in result if e.type == "executor_invoked"]
        completed = [e for e in result if e.type == "executor_completed"]
        assert len(invoked) == 3
        assert len(completed) == 3


# ---------------------------------------------------------------------------
# Recovery after errors
# ---------------------------------------------------------------------------


class TestRecoveryAfterErrors:
    async def test_run_after_failure_is_allowed(self):
        @workflow
        async def wf(x: int) -> int:
            if x == 1:
                raise RuntimeError("boom")
            return x

        with pytest.raises(RuntimeError, match="boom"):
            await wf.run(1)

        # Must be able to run again after the failure
        result = await wf.run(2)
        assert result.get_outputs() == [2]

    async def test_step_sync_function_raises(self):
        with pytest.raises(TypeError, match="async functions"):

            @step  # pyright: ignore[reportArgumentType]
            def not_async(x: int) -> int:  # pyright: ignore[reportUnusedFunction]
                return x


# ---------------------------------------------------------------------------
# WorkflowInterrupted is BaseException
# ---------------------------------------------------------------------------


class TestWorkflowInterruptedIsBaseException:
    async def test_except_exception_does_not_catch_interrupt(self):
        """User code with ``except Exception`` should not catch WorkflowInterrupted."""
        caught = False

        @workflow
        async def wf(x: int, ctx: RunContext) -> str:
            nonlocal caught
            try:
                return await ctx.request_info("need review", response_type=str, request_id="r1")
            except Exception:
                # This should NOT catch WorkflowInterrupted
                caught = True
                return "caught!"

        result = await wf.run("data")
        # Should have a pending request, NOT "caught!"
        assert result.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
        assert result.get_outputs() == []
        assert caught is False


# ---------------------------------------------------------------------------
# Checkpoint validation
# ---------------------------------------------------------------------------


class TestCheckpointValidation:
    async def test_checkpoint_signature_mismatch_raises(self):
        from agent_framework import WorkflowCheckpoint

        storage = InMemoryCheckpointStorage()

        @workflow(name="my_wf", checkpoint_storage=storage)
        async def wf(x: int) -> int:
            return x

        # Manually create a checkpoint with a different signature hash
        bad_checkpoint = WorkflowCheckpoint(
            workflow_name="my_wf",
            graph_signature_hash="totally_different_hash",
            state={"_step_cache": {}, "_original_message": 1},
        )
        ckpt_id = await storage.save(bad_checkpoint)

        # Should fail due to hash mismatch
        with pytest.raises(ValueError, match="not compatible"):
            await wf.run(checkpoint_id=ckpt_id)

    async def test_import_step_cache_malformed_key(self):
        ctx = _RunContext("test")
        with pytest.raises(ValueError, match="Corrupted step cache"):
            ctx._import_step_cache({"invalid_key_no_separator": 42})  # pyright: ignore[reportPrivateUsage]

    async def test_import_step_cache_non_integer_index(self):
        ctx = _RunContext("test")
        with pytest.raises(ValueError, match="Corrupted step cache"):
            ctx._import_step_cache({"step_name::abc": 42})  # pyright: ignore[reportPrivateUsage]
