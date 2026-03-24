# Copyright (c) Microsoft. All rights reserved.

"""Comprehensive golden event-stream tests for AgentFrameworkWorkflow.

Covers the full matrix of workflow-specific AG-UI patterns:
- request_info → TOOL_CALL lifecycle and balancing
- Executor step events and activity snapshots
- Text output, dict output, BaseEvent passthrough, AgentResponse output
- Text deduplication across workflow outputs
- Workflow error handling → RUN_ERROR
- Multi-turn interrupt/resume round-trips
- Empty turns with pending requests
- Custom workflow events
- Text message draining on request_info and executor boundaries
"""

import json
from typing import Any, cast

from ag_ui.core import EventType, StateSnapshotEvent
from agent_framework import (
    AgentResponse,
    Content,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    executor,
    handler,
    response_handler,
)
from event_stream import EventStream
from typing_extensions import Never

from agent_framework_ag_ui import AgentFrameworkWorkflow


async def _run(wrapper: AgentFrameworkWorkflow, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in wrapper.run(payload)])


def _payload(
    msg: str = "go",
    *,
    thread_id: str = "thread-wf",
    run_id: str = "run-wf",
    **extra: Any,
) -> dict[str, Any]:
    return {"thread_id": thread_id, "run_id": run_id, "messages": [{"role": "user", "content": msg}], **extra}


# ──────────────────────────────────────────────────────────────────────
# 1. Basic workflow text output
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_text_output_golden_sequence() -> None:
    """Simple text output: RUN_STARTED → STEP_STARTED → TEXT_* → STEP_FINISHED → TEXT_MESSAGE_END → RUN_FINISHED."""

    @executor(id="greeter")
    async def greeter(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("Hello from workflow!")

    workflow = WorkflowBuilder(start_executor=greeter).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_bookends()
    stream.assert_no_run_error()
    stream.assert_text_messages_balanced()
    stream.assert_has_type("TEXT_MESSAGE_START")
    stream.assert_has_type("TEXT_MESSAGE_CONTENT")
    stream.assert_has_type("TEXT_MESSAGE_END")

    # Verify actual content
    deltas = [e.delta for e in stream.get("TEXT_MESSAGE_CONTENT")]
    assert "Hello from workflow!" in deltas


async def test_workflow_text_output_message_id_consistency() -> None:
    """All text events for a single output share the same message_id."""

    @executor(id="echo")
    async def echo(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("echo reply")

    workflow = WorkflowBuilder(start_executor=echo).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_message_ids_consistent()


# ──────────────────────────────────────────────────────────────────────
# 2. Executor step events and activity snapshots
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_executor_lifecycle_events() -> None:
    """Executor invocation produces STEP_STARTED, ACTIVITY_SNAPSHOT, STEP_FINISHED."""

    @executor(id="worker")
    async def worker(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("done")

    workflow = WorkflowBuilder(start_executor=worker).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    # Step events with executor ID
    started = [e for e in stream.get("STEP_STARTED") if getattr(e, "step_name", "") == "worker"]
    finished = [e for e in stream.get("STEP_FINISHED") if getattr(e, "step_name", "") == "worker"]
    assert started, "Expected STEP_STARTED for 'worker'"
    assert finished, "Expected STEP_FINISHED for 'worker'"

    # Activity snapshots
    activities = stream.get("ACTIVITY_SNAPSHOT")
    assert activities, "Expected ACTIVITY_SNAPSHOT events"
    # Check one of them has executor payload
    executor_activities = [a for a in activities if getattr(a, "activity_type", None) == "executor"]
    assert executor_activities, "Expected executor-type activity snapshots"


async def test_workflow_executor_step_ordering() -> None:
    """STEP_STARTED comes before content, STEP_FINISHED comes after."""

    @executor(id="orderer")
    async def orderer(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("ordered output")

    workflow = WorkflowBuilder(start_executor=orderer).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "STEP_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "STEP_FINISHED",
            "RUN_FINISHED",
        ]
    )


# ──────────────────────────────────────────────────────────────────────
# 3. Dict output → CUSTOM workflow_output
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_dict_output_maps_to_custom_event() -> None:
    """Non-chat dict output is emitted as CUSTOM workflow_output event."""

    @executor(id="structured")
    async def structured(message: Any, ctx: WorkflowContext[Never, dict[str, int]]) -> None:
        await ctx.yield_output({"count": 42, "status": 1})

    workflow = WorkflowBuilder(start_executor=structured).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_bookends()
    stream.assert_no_run_error()

    customs = [e for e in stream.get("CUSTOM") if getattr(e, "name", None) == "workflow_output"]
    assert len(customs) == 1
    assert customs[0].value == {"count": 42, "status": 1}

    # Should NOT have TEXT_MESSAGE events for dict output
    assert "TEXT_MESSAGE_CONTENT" not in stream.types()


# ──────────────────────────────────────────────────────────────────────
# 4. BaseEvent passthrough
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_base_event_passthrough() -> None:
    """AG-UI BaseEvent outputs are yielded directly, not wrapped."""

    @executor(id="stateful")
    async def stateful(message: Any, ctx: WorkflowContext[Never, StateSnapshotEvent]) -> None:
        await ctx.yield_output(StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot={"active_agent": "flights"}))

    workflow = WorkflowBuilder(start_executor=stateful).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_bookends()
    snapshots = stream.get("STATE_SNAPSHOT")
    assert len(snapshots) == 1
    assert snapshots[0].snapshot["active_agent"] == "flights"


# ──────────────────────────────────────────────────────────────────────
# 5. AgentResponse output (conversation payload)
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_agent_response_output_extracts_latest_assistant() -> None:
    """AgentResponse output uses only the latest assistant message, not full history."""

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext[Never, AgentResponse]) -> None:
        response = AgentResponse(
            messages=[
                Message(role="user", contents=[Content.from_text("My order is damaged")]),
                Message(role="assistant", contents=[Content.from_text("I'll process your replacement.")]),
            ]
        )
        await ctx.yield_output(response)

    workflow = WorkflowBuilder(start_executor=responder).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_bookends()
    stream.assert_text_messages_balanced()

    deltas = [e.delta for e in stream.get("TEXT_MESSAGE_CONTENT")]
    assert deltas == ["I'll process your replacement."]


# ──────────────────────────────────────────────────────────────────────
# 6. Custom workflow events
# ──────────────────────────────────────────────────────────────────────


class ProgressEvent(WorkflowEvent):
    """Custom workflow event for testing CUSTOM event mapping."""

    def __init__(self, progress: int) -> None:
        super().__init__("custom_progress", data={"progress": progress})


async def test_workflow_custom_events() -> None:
    """Custom workflow events are mapped to CUSTOM AG-UI events."""

    @executor(id="progress_tracker")
    async def progress_tracker(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.add_event(ProgressEvent(25))
        await ctx.yield_output("In progress...")
        await ctx.add_event(ProgressEvent(100))

    workflow = WorkflowBuilder(start_executor=progress_tracker).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_bookends()
    stream.assert_no_run_error()

    progress_events = [e for e in stream.get("CUSTOM") if getattr(e, "name", None) == "custom_progress"]
    assert len(progress_events) == 2
    assert progress_events[0].value == {"progress": 25}
    assert progress_events[1].value == {"progress": 100}


# ──────────────────────────────────────────────────────────────────────
# 7. request_info → TOOL_CALL lifecycle
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_request_info_tool_call_lifecycle() -> None:
    """request_info emits TOOL_CALL_START/ARGS/END cycle plus CUSTOM request_info."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info("Need approval", str, request_id="req-1")

    workflow = WorkflowBuilder(start_executor=requester).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_bookends()
    stream.assert_no_run_error()

    # Tool call lifecycle
    stream.assert_ordered_types(
        [
            "RUN_STARTED",
            "TOOL_CALL_START",
            "TOOL_CALL_ARGS",
            "TOOL_CALL_END",
            "CUSTOM",  # request_info
            "RUN_FINISHED",
        ]
    )

    # Verify tool call details
    start = stream.first("TOOL_CALL_START")
    assert start.tool_call_id == "req-1"
    assert start.tool_call_name == "request_info"

    # TOOL_CALL_ARGS should contain the request payload
    args = stream.first("TOOL_CALL_ARGS")
    assert args.tool_call_id == "req-1"
    parsed_args = json.loads(args.delta)
    assert parsed_args["request_id"] == "req-1"

    # Tool calls should be balanced
    stream.assert_tool_calls_balanced()


async def test_workflow_request_info_interrupt_in_run_finished() -> None:
    """request_info populates RUN_FINISHED.interrupt with the request metadata."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info(
            {"message": "Choose a flight", "options": [{"airline": "KLM"}], "agent": "flights"},
            dict,
            request_id="flights-choice",
        )

    workflow = WorkflowBuilder(start_executor=requester).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    finished = stream.last("RUN_FINISHED")
    interrupt = finished.model_dump().get("interrupt")
    assert isinstance(interrupt, list)
    assert len(interrupt) == 1
    assert interrupt[0]["id"] == "flights-choice"
    assert interrupt[0]["value"]["agent"] == "flights"


async def test_workflow_request_info_emits_interrupt_card_event() -> None:
    """request_info with dict data emits a WorkflowInterruptEvent custom event."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info(
            {"message": "Pick one", "options": ["A", "B"]},
            dict,
            request_id="pick-1",
        )

    workflow = WorkflowBuilder(start_executor=requester).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    interrupt_cards = [e for e in stream.get("CUSTOM") if getattr(e, "name", None) == "WorkflowInterruptEvent"]
    assert interrupt_cards, "Expected WorkflowInterruptEvent custom event"


# ──────────────────────────────────────────────────────────────────────
# 8. Text message draining on request_info boundary
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_text_drained_before_request_info() -> None:
    """Open text message is closed (TEXT_MESSAGE_END) before request_info tool calls begin."""

    @executor(id="text_then_request")
    async def text_then_request(message: Any, ctx: WorkflowContext) -> None:
        await ctx.yield_output("Please confirm this action.")
        await ctx.request_info("Need approval", str, request_id="approval-1")

    workflow = WorkflowBuilder(start_executor=text_then_request).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_text_messages_balanced()
    stream.assert_tool_calls_balanced()

    # TEXT_MESSAGE_END must appear before TOOL_CALL_START
    types = stream.types()
    text_end_idx = types.index("TEXT_MESSAGE_END")
    tool_start_idx = types.index("TOOL_CALL_START")
    assert text_end_idx < tool_start_idx, (
        f"TEXT_MESSAGE_END (idx={text_end_idx}) must come before TOOL_CALL_START (idx={tool_start_idx})"
    )


# ──────────────────────────────────────────────────────────────────────
# 9. Text deduplication
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_skips_duplicate_text_from_snapshot() -> None:
    """Duplicate text from AgentResponse snapshot is not re-emitted."""

    @executor(id="deduper")
    async def deduper(message: Any, ctx: WorkflowContext[Never, Any]) -> None:
        text = "Order processed successfully."
        await ctx.yield_output(text)
        # Snapshot repeats the same text
        await ctx.yield_output(
            AgentResponse(
                messages=[
                    Message(role="user", contents=[Content.from_text("process order")]),
                    Message(role="assistant", contents=[Content.from_text(text)]),
                ]
            )
        )

    workflow = WorkflowBuilder(start_executor=deduper).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_text_messages_balanced()
    deltas = [e.delta for e in stream.get("TEXT_MESSAGE_CONTENT")]
    # Text should appear only once
    assert deltas == ["Order processed successfully."]


async def test_workflow_skips_consecutive_duplicate_outputs() -> None:
    """Consecutive identical text outputs are deduplicated."""

    @executor(id="repeater")
    async def repeater(message: Any, ctx: WorkflowContext[Never, Any]) -> None:
        text = "Done!"
        await ctx.yield_output(text)
        await ctx.yield_output(text)

    workflow = WorkflowBuilder(start_executor=repeater).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_text_messages_balanced()
    deltas = [e.delta for e in stream.get("TEXT_MESSAGE_CONTENT")]
    assert deltas == ["Done!"]


async def test_workflow_emits_distinct_consecutive_outputs() -> None:
    """Distinct text outputs are all emitted, not incorrectly deduplicated."""

    @executor(id="multisayer")
    async def multisayer(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("First part. ")
        await ctx.yield_output("Second part.")

    workflow = WorkflowBuilder(start_executor=multisayer).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_text_messages_balanced()
    deltas = [e.delta for e in stream.get("TEXT_MESSAGE_CONTENT")]
    assert deltas == ["First part. ", "Second part."]


# ──────────────────────────────────────────────────────────────────────
# 10. Workflow error handling → RUN_ERROR
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_error_emits_run_error_event() -> None:
    """Exceptions during workflow streaming produce RUN_ERROR events."""

    class FailingWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                raise RuntimeError("workflow exploded")
                yield  # pragma: no cover

            return _stream()

    wrapper = AgentFrameworkWorkflow(workflow=cast(Any, FailingWorkflow()))
    stream = await _run(wrapper, _payload())

    # Should still have RUN_STARTED
    stream.assert_has_type("RUN_STARTED")
    # Should have RUN_ERROR
    stream.assert_has_type("RUN_ERROR")
    error = stream.first("RUN_ERROR")
    assert "workflow exploded" in error.message


async def test_workflow_error_preserves_bookend_structure() -> None:
    """Even on error, RUN_STARTED is the first event."""

    class FailingWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                raise ValueError("bad input")
                yield  # pragma: no cover

            return _stream()

    wrapper = AgentFrameworkWorkflow(workflow=cast(Any, FailingWorkflow()))
    stream = await _run(wrapper, _payload())

    types = stream.types()
    assert types[0] == "RUN_STARTED"
    assert "RUN_ERROR" in types


# ──────────────────────────────────────────────────────────────────────
# 11. Multi-turn request_info interrupt/resume
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_interrupt_resume_round_trip() -> None:
    """Turn 1: request_info → interrupt. Turn 2: resume → completion."""

    class RequesterExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="requester")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext) -> None:
            await ctx.request_info("Choose an option", str, request_id="choice-1")

        @response_handler
        async def handle_choice(self, original: str, response: str, ctx: WorkflowContext) -> None:
            await ctx.yield_output(f"You chose: {response}")

    workflow = WorkflowBuilder(start_executor=RequesterExecutor()).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Turn 1
    stream1 = await _run(wrapper, _payload(thread_id="thread-resume", run_id="run-1"))
    stream1.assert_bookends()
    stream1.assert_no_run_error()
    stream1.assert_tool_calls_balanced()

    finished1 = stream1.last("RUN_FINISHED")
    interrupt1 = finished1.model_dump().get("interrupt")
    assert interrupt1, "Expected interrupt"
    assert interrupt1[0]["id"] == "choice-1"

    # Turn 2: resume
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-resume",
            "run_id": "run-2",
            "messages": [],
            "resume": {"interrupts": [{"id": "choice-1", "value": "Option A"}]},
        },
    )
    stream2.assert_has_run_lifecycle()
    stream2.assert_no_run_error()
    stream2.assert_text_messages_balanced()

    # Should have the response text
    deltas = [e.delta for e in stream2.get("TEXT_MESSAGE_CONTENT")]
    assert any("Option A" in d for d in deltas), f"Expected 'Option A' in deltas: {deltas}"

    # No interrupt after resume
    finished2 = stream2.last("RUN_FINISHED")
    interrupt2 = finished2.model_dump().get("interrupt")
    assert not interrupt2


async def test_workflow_forwarded_props_resume() -> None:
    """CopilotKit-style forwarded_props.command.resume should resume a pending request."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info({"options": [{"name": "A"}]}, dict, request_id="pick")

    workflow = WorkflowBuilder(start_executor=requester).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Turn 1
    await _run(wrapper, _payload(thread_id="thread-fwd", run_id="run-1"))

    # Turn 2 via forwarded_props
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-fwd",
            "run_id": "run-2",
            "messages": [],
            "forwarded_props": {"command": {"resume": json.dumps({"name": "A"})}},
        },
    )
    stream2.assert_bookends()
    stream2.assert_no_run_error()

    finished = stream2.last("RUN_FINISHED")
    assert not finished.model_dump().get("interrupt")


# ──────────────────────────────────────────────────────────────────────
# 12. Empty turns with pending requests
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_empty_turn_preserves_interrupts() -> None:
    """An empty turn with a pending request still returns the interrupt without errors."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info({"prompt": "choose"}, dict, request_id="pick-one")

    workflow = WorkflowBuilder(start_executor=requester).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Turn 1: trigger the request
    await _run(wrapper, _payload(thread_id="thread-empty", run_id="run-1"))

    # Turn 2: empty messages, no resume
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-empty",
            "run_id": "run-2",
            "messages": [],
        },
    )
    stream2.assert_bookends()
    stream2.assert_no_run_error()
    stream2.assert_tool_calls_balanced()

    # Should re-emit the pending interrupt
    finished = stream2.last("RUN_FINISHED")
    interrupts = finished.model_dump().get("interrupt")
    assert isinstance(interrupts, list)
    assert interrupts[0]["id"] == "pick-one"

    # Should have TOOL_CALL events for the pending request
    stream2.assert_has_type("TOOL_CALL_START")


async def test_workflow_empty_turn_no_pending_requests() -> None:
    """Empty turn with no pending requests produces clean bookends."""

    @executor(id="noop")
    async def noop(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output("done")

    workflow = WorkflowBuilder(start_executor=noop).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Run once to completion
    await _run(wrapper, _payload(thread_id="thread-empty-clean", run_id="run-1"))

    # Empty turn
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-empty-clean",
            "run_id": "run-2",
            "messages": [],
        },
    )
    stream2.assert_bookends()
    stream2.assert_no_run_error()


# ──────────────────────────────────────────────────────────────────────
# 13. Usage content as CUSTOM event
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_usage_output_maps_to_custom_event() -> None:
    """Usage Content outputs are surfaced as custom usage events."""

    @executor(id="usage_reporter")
    async def usage_reporter(message: Any, ctx: WorkflowContext[Never, Content]) -> None:
        await ctx.yield_output(
            Content.from_usage({"input_token_count": 100, "output_token_count": 50, "total_token_count": 150})
        )

    workflow = WorkflowBuilder(start_executor=usage_reporter).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)
    stream = await _run(wrapper, _payload())

    stream.assert_bookends()
    stream.assert_no_run_error()

    usage_events = [e for e in stream.get("CUSTOM") if getattr(e, "name", None) == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].value["input_token_count"] == 100
    assert usage_events[0].value["total_token_count"] == 150


# ──────────────────────────────────────────────────────────────────────
# 14. Approval flow (Content-based request_info)
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_approval_flow_round_trip() -> None:
    """function_approval_request via request_info, then resume with approval response."""

    class ApprovalExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="approval_exec")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext) -> None:
            function_call = Content.from_function_call(
                call_id="refund-call",
                name="submit_refund",
                arguments={"order_id": "12345", "amount": "$89.99"},
            )
            approval_request = Content.from_function_approval_request(id="approval-1", function_call=function_call)
            await ctx.request_info(approval_request, Content, request_id="approval-1")

        @response_handler
        async def handle_approval(self, original_request: Content, response: Content, ctx: WorkflowContext) -> None:
            status = "approved" if bool(response.approved) else "rejected"
            await ctx.yield_output(f"Refund {status}.")

    workflow = WorkflowBuilder(start_executor=ApprovalExecutor()).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Turn 1: request approval
    stream1 = await _run(wrapper, _payload(thread_id="thread-approval", run_id="run-1"))
    stream1.assert_bookends()
    stream1.assert_no_run_error()

    finished1 = stream1.last("RUN_FINISHED")
    interrupt1 = finished1.model_dump().get("interrupt")
    assert interrupt1, "Expected approval interrupt"
    interrupt_value = interrupt1[0]["value"]

    # Turn 2: approve
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-approval",
            "run_id": "run-2",
            "messages": [],
            "resume": {
                "interrupts": [
                    {
                        "id": "approval-1",
                        "value": {
                            "type": "function_approval_response",
                            "approved": True,
                            "id": interrupt_value.get("id", "approval-1"),
                            "function_call": interrupt_value.get("function_call"),
                        },
                    }
                ]
            },
        },
    )
    stream2.assert_has_run_lifecycle()
    stream2.assert_no_run_error()
    stream2.assert_text_messages_balanced()

    deltas = [e.delta for e in stream2.get("TEXT_MESSAGE_CONTENT")]
    assert any("approved" in d for d in deltas)

    # No more interrupt
    finished2 = stream2.last("RUN_FINISHED")
    assert not finished2.model_dump().get("interrupt")


# ──────────────────────────────────────────────────────────────────────
# 15. Message list request/response coercion
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_message_list_resume() -> None:
    """Resume with list[Message] payload coerces correctly into workflow response."""

    class MessageRequestExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="msg_request")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext) -> None:
            await ctx.request_info({"prompt": "Need follow-up"}, list[Message], request_id="handoff")

        @response_handler
        async def handle_input(self, original: dict, response: list[Message], ctx: WorkflowContext) -> None:
            user_text = response[0].text if response else ""
            await ctx.yield_output(f"Got: {user_text}")

    workflow = WorkflowBuilder(start_executor=MessageRequestExecutor()).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Turn 1
    await _run(wrapper, _payload(thread_id="thread-msg", run_id="run-1"))

    # Turn 2: resume with message list
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-msg",
            "run_id": "run-2",
            "messages": [],
            "resume": {
                "interrupts": [
                    {
                        "id": "handoff",
                        "value": [
                            {"role": "user", "contents": [{"type": "text", "text": "Ship a replacement"}]},
                        ],
                    }
                ]
            },
        },
    )
    stream2.assert_has_run_lifecycle()
    stream2.assert_no_run_error()
    stream2.assert_text_messages_balanced()

    deltas = [e.delta for e in stream2.get("TEXT_MESSAGE_CONTENT")]
    assert any("replacement" in d for d in deltas)


# ──────────────────────────────────────────────────────────────────────
# 16. Plain text follow-up does NOT infer interrupt response
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_plain_text_does_not_resume_pending_dict_request() -> None:
    """Plain text user follow-up should NOT be coerced into a dict response."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info(
            {"message": "Choose a flight", "options": [{"airline": "KLM"}], "agent": "flights"},
            dict,
            request_id="flights-choice",
        )

    workflow = WorkflowBuilder(start_executor=requester).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Turn 1
    await _run(wrapper, _payload(thread_id="thread-nocoerce", run_id="run-1"))

    # Turn 2: plain text follow-up with request_info tool call in history
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-nocoerce",
            "run_id": "run-2",
            "messages": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "flights-choice",
                            "type": "function",
                            "function": {"name": "request_info", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "user", "content": "I prefer KLM please"},
            ],
        },
    )
    stream2.assert_bookends()
    stream2.assert_no_run_error()

    # Should still have the interrupt (text was not accepted as dict response)
    finished = stream2.last("RUN_FINISHED")
    interrupts = finished.model_dump().get("interrupt")
    assert isinstance(interrupts, list)
    assert interrupts[0]["id"] == "flights-choice"


# ──────────────────────────────────────────────────────────────────────
# 17. Workflow factory (thread-scoped workflows)
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_factory_thread_scoping() -> None:
    """workflow_factory creates separate workflow instances per thread_id."""

    def make_workflow(thread_id: str):
        @executor(id="echo")
        async def echo(message: Any, ctx: WorkflowContext[Never, str]) -> None:
            await ctx.yield_output(f"Thread: {thread_id}")

        return WorkflowBuilder(start_executor=echo).build()

    wrapper = AgentFrameworkWorkflow(workflow_factory=make_workflow)

    stream_a = await _run(wrapper, _payload(thread_id="thread-a", run_id="run-a"))
    stream_b = await _run(wrapper, _payload(thread_id="thread-b", run_id="run-b"))

    stream_a.assert_bookends()
    stream_b.assert_bookends()

    deltas_a = [e.delta for e in stream_a.get("TEXT_MESSAGE_CONTENT")]
    deltas_b = [e.delta for e in stream_b.get("TEXT_MESSAGE_CONTENT")]
    assert any("thread-a" in d for d in deltas_a)
    assert any("thread-b" in d for d in deltas_b)


# ──────────────────────────────────────────────────────────────────────
# 18. Multiple request_info calls in sequence
# ──────────────────────────────────────────────────────────────────────


async def test_workflow_sequential_request_info_interrupts() -> None:
    """Two chained executors each requesting info: first triggers interrupt, resume, then second triggers interrupt.

    This mirrors the subgraphs_agent pattern where separate executors handle sequential interactions.
    """

    class NameRequester(Executor):
        def __init__(self) -> None:
            super().__init__(id="name_requester")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext[str]) -> None:
            await ctx.request_info("What's your name?", str, request_id="name-req")

        @response_handler
        async def handle_name(self, original: str, response: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message(response)

    class DestRequester(Executor):
        def __init__(self) -> None:
            super().__init__(id="dest_requester")

        @handler
        async def start(self, message: str, ctx: WorkflowContext[str]) -> None:
            self._name = message
            await ctx.request_info("Where to?", str, request_id="dest-req")

        @response_handler
        async def handle_dest(self, original: str, response: str, ctx: WorkflowContext[str]) -> None:
            await ctx.yield_output(f"Booking for {self._name} to {response}")

    name_requester = NameRequester()
    dest_requester = DestRequester()
    workflow = WorkflowBuilder(start_executor=name_requester).add_chain([name_requester, dest_requester]).build()
    wrapper = AgentFrameworkWorkflow(workflow=workflow)

    # Turn 1
    stream1 = await _run(wrapper, _payload(thread_id="thread-seq", run_id="run-1"))
    stream1.assert_bookends()
    stream1.assert_tool_calls_balanced()
    interrupt1 = stream1.last("RUN_FINISHED").model_dump().get("interrupt")
    assert interrupt1[0]["id"] == "name-req"

    # Turn 2: answer name → triggers second executor's request_info
    stream2 = await _run(
        wrapper,
        {
            "thread_id": "thread-seq",
            "run_id": "run-2",
            "messages": [],
            "resume": {"interrupts": [{"id": "name-req", "value": "Alice"}]},
        },
    )
    stream2.assert_has_run_lifecycle()
    stream2.assert_tool_calls_balanced()
    interrupt2 = stream2.last("RUN_FINISHED").model_dump().get("interrupt")
    assert interrupt2[0]["id"] == "dest-req"

    # Turn 3: answer destination → completion
    stream3 = await _run(
        wrapper,
        {
            "thread_id": "thread-seq",
            "run_id": "run-3",
            "messages": [],
            "resume": {"interrupts": [{"id": "dest-req", "value": "Paris"}]},
        },
    )
    stream3.assert_has_run_lifecycle()
    stream3.assert_no_run_error()
    stream3.assert_text_messages_balanced()

    deltas = [e.delta for e in stream3.get("TEXT_MESSAGE_CONTENT")]
    assert any("Alice" in d and "Paris" in d for d in deltas)
    assert not stream3.last("RUN_FINISHED").model_dump().get("interrupt")
