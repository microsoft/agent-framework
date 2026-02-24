# Copyright (c) Microsoft. All rights reserved.

"""Tests for native workflow AG-UI runner."""

import json
from types import SimpleNamespace
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
from typing_extensions import Never

from agent_framework_ag_ui._workflow_run import (
    _coerce_message,
    _coerce_response_for_request,
    run_workflow_stream,
)


class ProgressEvent(WorkflowEvent):
    """Custom workflow event used to validate CUSTOM mapping."""

    def __init__(self, progress: int) -> None:
        super().__init__("custom_progress", data={"progress": progress})


async def test_workflow_run_maps_custom_and_text_events():
    """Custom workflow events and yielded text are mapped to AG-UI events."""

    @executor(id="start")
    async def start(message: Any, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.add_event(ProgressEvent(10))
        await ctx.yield_output("Hello workflow")

    workflow = WorkflowBuilder(start_executor=start).build()
    input_data = {"messages": [{"role": "user", "content": "go"}]}

    events = [event async for event in run_workflow_stream(input_data, workflow)]

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "CUSTOM" in event_types
    assert "TEXT_MESSAGE_CONTENT" in event_types
    assert "STEP_STARTED" in event_types
    assert "STEP_FINISHED" in event_types
    assert "RUN_FINISHED" in event_types

    custom_events = [event for event in events if event.type == "CUSTOM" and event.name == "custom_progress"]
    assert len(custom_events) == 1
    assert custom_events[0].value == {"progress": 10}


async def test_workflow_run_request_info_emits_interrupt_and_resume_works():
    """request_info should emit interrupt metadata and resume should continue run."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info("Need approval", str)

    workflow = WorkflowBuilder(start_executor=requester).build()

    first_run_events = [
        event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)
    ]

    run_finished_events = [event for event in first_run_events if event.type == "RUN_FINISHED"]
    assert len(run_finished_events) == 1
    interrupt_payload = run_finished_events[0].model_dump().get("interrupt")
    assert isinstance(interrupt_payload, list)
    assert len(interrupt_payload) == 1

    request_id = str(interrupt_payload[0]["id"])
    assert request_id

    resumed_events = [
        event
        async for event in run_workflow_stream(
            {"messages": [], "resume": {"interrupts": [{"id": request_id, "value": "approved"}]}},
            workflow,
        )
    ]

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_STARTED" in resumed_types
    assert "RUN_FINISHED" in resumed_types
    assert "RUN_ERROR" not in resumed_types


async def test_workflow_run_request_info_closes_open_text_message() -> None:
    """Text output should end before request_info interrupt events begin."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.yield_output("Please confirm this action.")
        await ctx.request_info("Need approval", str, request_id="approval-1")

    workflow = WorkflowBuilder(start_executor=requester).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    content_index = next(i for i, event in enumerate(events) if event.type == "TEXT_MESSAGE_CONTENT")
    end_index = next(i for i, event in enumerate(events) if event.type == "TEXT_MESSAGE_END")
    request_start_index = next(
        i
        for i, event in enumerate(events)
        if event.type == "TOOL_CALL_START" and getattr(event, "tool_call_id", None) == "approval-1"
    )

    assert content_index < end_index < request_start_index


async def test_workflow_run_request_info_interrupt_uses_raw_dict_value():
    """Dict request payloads should be surfaced directly in RUN_FINISHED.interrupt.value."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        await ctx.request_info(
            {
                "message": "Choose a flight",
                "options": [{"airline": "KLM"}],
                "recommendation": {"airline": "KLM"},
                "agent": "flights",
            },
            dict,
            request_id="flights-choice",
        )

    workflow = WorkflowBuilder(start_executor=requester).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    run_finished = [event for event in events if event.type == "RUN_FINISHED"][0].model_dump()
    interrupt_payload = run_finished.get("interrupt")
    assert isinstance(interrupt_payload, list)
    assert interrupt_payload[0]["id"] == "flights-choice"
    assert interrupt_payload[0]["value"]["agent"] == "flights"
    assert interrupt_payload[0]["value"]["message"] == "Choose a flight"


async def test_workflow_run_resume_from_forwarded_command_payload() -> None:
    """forwarded_props.command.resume should resume a pending dict request."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.request_info({"options": [{"airline": "KLM"}]}, dict, request_id="flights-choice")

    workflow = WorkflowBuilder(start_executor=requester).build()
    _ = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    resumed_events = [
        event
        async for event in run_workflow_stream(
            {
                "messages": [],
                "forwarded_props": {
                    "command": {"resume": json.dumps({"airline": "KLM", "departure": "AMS", "arrival": "SFO"})}
                },
            },
            workflow,
        )
    ]

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_ERROR" not in resumed_types
    finished = [event for event in resumed_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert "interrupt" not in finished


async def test_workflow_run_structured_user_json_resumes_single_pending_request() -> None:
    """A JSON user reply should resume a single pending dict request without heuristics."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.request_info({"options": [{"name": "Hotel Zoe"}]}, dict, request_id="hotel-choice")

    workflow = WorkflowBuilder(start_executor=requester).build()
    _ = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    resumed_events = [
        event
        async for event in run_workflow_stream(
            {
                "messages": [{"role": "user", "content": json.dumps({"name": "Hotel Zoe"})}],
            },
            workflow,
        )
    ]

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_ERROR" not in resumed_types
    finished = [event for event in resumed_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert "interrupt" not in finished


async def test_workflow_run_resume_content_response_from_json_payload() -> None:
    """JSON resume payloads should coerce into Content responses for approval requests."""

    class ApprovalExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="approval_executor")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext) -> None:
            del message
            function_call = Content.from_function_call(
                call_id="refund-call",
                name="submit_refund",
                arguments={"order_id": "12345", "amount": "$89.99"},
            )
            approval_request = Content.from_function_approval_request(id="approval-1", function_call=function_call)
            await ctx.request_info(approval_request, Content, request_id="approval-1")

        @response_handler
        async def handle_approval(self, original_request: Content, response: Content, ctx: WorkflowContext) -> None:
            del original_request
            status = "approved" if bool(response.approved) else "rejected"
            await ctx.yield_output(f"Refund tool call {status}.")

    workflow = WorkflowBuilder(start_executor=ApprovalExecutor()).build()
    first_events = [
        event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)
    ]
    first_finished = [event for event in first_events if event.type == "RUN_FINISHED"][0].model_dump()
    interrupt_payload = cast(list[dict[str, Any]], first_finished.get("interrupt"))
    interrupt_value = cast(dict[str, Any], interrupt_payload[0]["value"])

    resumed_events = [
        event
        async for event in run_workflow_stream(
            {
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
            workflow,
        )
    ]

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_ERROR" not in resumed_types
    assert "TEXT_MESSAGE_CONTENT" in resumed_types
    resumed_finished = [event for event in resumed_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert "interrupt" not in resumed_finished
    text_deltas = [event.delta for event in resumed_events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert any("approved" in delta for delta in text_deltas)


async def test_workflow_run_resume_message_list_from_json_payload() -> None:
    """Resume payloads should coerce AG-UI message dictionaries into list[Message] responses."""

    class MessageRequestExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="message_request_executor")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext) -> None:
            del message
            await ctx.request_info({"prompt": "Need user follow-up"}, list[Message], request_id="handoff-user-input")

        @response_handler
        async def handle_user_input(
            self, original_request: dict, response: list[Message], ctx: WorkflowContext
        ) -> None:
            del original_request
            user_text = response[0].text if response else ""
            await ctx.yield_output(f"Captured response: {user_text}")

    workflow = WorkflowBuilder(start_executor=MessageRequestExecutor()).build()
    _ = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "start"}]}, workflow)]

    resumed_events = [
        event
        async for event in run_workflow_stream(
            {
                "messages": [],
                "resume": {
                    "interrupts": [
                        {
                            "id": "handoff-user-input",
                            "value": [
                                {
                                    "role": "user",
                                    "contents": [{"type": "text", "text": "Please ship a replacement instead."}],
                                }
                            ],
                        }
                    ]
                },
            },
            workflow,
        )
    ]

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_ERROR" not in resumed_types
    assert "TEXT_MESSAGE_CONTENT" in resumed_types
    resumed_finished = [event for event in resumed_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert "interrupt" not in resumed_finished
    text_deltas = [event.delta for event in resumed_events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert any("replacement" in delta for delta in text_deltas)


async def test_workflow_run_non_chat_output_maps_to_custom_output_event():
    """Non-chat workflow outputs are emitted as CUSTOM workflow_output events."""

    @executor(id="structured")
    async def structured(message: Any, ctx: WorkflowContext[Never, dict[str, int]]) -> None:
        await ctx.yield_output({"count": 3})

    workflow = WorkflowBuilder(start_executor=structured).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    output_custom = [event for event in events if event.type == "CUSTOM" and event.name == "workflow_output"]
    assert len(output_custom) == 1
    assert output_custom[0].value == {"count": 3}


async def test_workflow_run_passthroughs_ag_ui_base_events():
    """Workflow outputs that are AG-UI BaseEvent instances should be emitted directly."""

    @executor(id="stateful")
    async def stateful(message: Any, ctx: WorkflowContext[Never, StateSnapshotEvent]) -> None:
        await ctx.yield_output(StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot={"active_agent": "flights"}))

    workflow = WorkflowBuilder(start_executor=stateful).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    snapshots = [event for event in events if event.type == "STATE_SNAPSHOT"]
    assert len(snapshots) == 1
    assert snapshots[0].snapshot["active_agent"] == "flights"


async def test_workflow_run_plain_text_follow_up_does_not_infer_interrupt_response():
    """User follow-up text should not be coerced into request_info responses for workflows."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.request_info(
            {
                "message": "Choose a flight",
                "options": [{"airline": "KLM"}, {"airline": "United"}],
                "agent": "flights",
            },
            dict,
            request_id="flights-choice",
        )

    workflow = WorkflowBuilder(start_executor=requester).build()
    _ = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    follow_up_events = [
        event
        async for event in run_workflow_stream(
            {
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
                ]
            },
            workflow,
        )
    ]

    follow_up_types = [event.type for event in follow_up_events]
    assert "RUN_ERROR" not in follow_up_types
    assert "TOOL_CALL_START" in follow_up_types

    run_finished = [event for event in follow_up_events if event.type == "RUN_FINISHED"][0].model_dump()
    interrupt_payload = run_finished.get("interrupt")
    assert isinstance(interrupt_payload, list)
    assert interrupt_payload[0]["id"] == "flights-choice"
    assert interrupt_payload[0]["value"]["agent"] == "flights"


async def test_workflow_run_empty_turn_with_pending_request_preserves_interrupts():
    """An empty turn should still return pending workflow interrupts without errors."""

    @executor(id="requester")
    async def requester(message: Any, ctx: WorkflowContext) -> None:
        del message
        await ctx.request_info({"prompt": "choose"}, dict, request_id="pick-one")

    workflow = WorkflowBuilder(start_executor=requester).build()
    _ = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    events = [event async for event in run_workflow_stream({"messages": []}, workflow)]
    types = [event.type for event in events]
    assert types[0] == "RUN_STARTED"
    assert "RUN_FINISHED" in types
    assert "RUN_ERROR" not in types

    finished = [event for event in events if event.type == "RUN_FINISHED"][0].model_dump()
    interrupts = finished.get("interrupt")
    assert isinstance(interrupts, list)
    assert interrupts[0]["id"] == "pick-one"


async def test_workflow_run_agent_response_output_uses_latest_assistant_message_only() -> None:
    """Conversation payload outputs should not flatten full history into one assistant message."""

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext[Never, AgentResponse]) -> None:
        del message
        response = AgentResponse(
            messages=[
                Message(role="user", contents=[Content.from_text("My order arrived damaged")]),
                Message(
                    role="assistant",
                    contents=[Content.from_text("Order Agent: Got it. I submitted the replacement request.")],
                ),
            ]
        )
        await ctx.yield_output(response)

    workflow = WorkflowBuilder(start_executor=responder).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    text_deltas = [event.delta for event in events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert text_deltas == ["Order Agent: Got it. I submitted the replacement request."]


async def test_workflow_run_skips_duplicate_text_from_conversation_snapshot() -> None:
    """Do not emit duplicate assistant text when a snapshot repeats the latest output."""

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext[Never, Any]) -> None:
        del message
        duplicate_text = "Order Agent: Got it. I submitted the replacement request."
        await ctx.yield_output(duplicate_text)
        await ctx.yield_output(
            AgentResponse(
                messages=[
                    Message(role="user", contents=[Content.from_text("standard")]),
                    Message(role="assistant", contents=[Content.from_text(duplicate_text)]),
                ]
            )
        )

    workflow = WorkflowBuilder(start_executor=responder).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    text_deltas = [event.delta for event in events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert text_deltas == ["Order Agent: Got it. I submitted the replacement request."]


async def test_workflow_run_skips_consecutive_duplicate_text_outputs() -> None:
    """Do not emit duplicate assistant text when consecutive outputs are identical."""

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext[Never, Any]) -> None:
        del message
        duplicate_text = "Order Agent: Replacement processed. Case complete."
        await ctx.yield_output(duplicate_text)
        await ctx.yield_output(duplicate_text)

    workflow = WorkflowBuilder(start_executor=responder).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    text_deltas = [event.delta for event in events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert text_deltas == ["Order Agent: Replacement processed. Case complete."]


async def test_workflow_run_skips_final_snapshot_when_streamed_chunks_already_match() -> None:
    """Do not append full snapshot text when prior chunk outputs already formed the same message."""

    @executor(id="responder")
    async def responder(message: Any, ctx: WorkflowContext[Never, Any]) -> None:
        del message
        full_text = (
            "Your replacement request for order 28939393 has been submitted with expedited shipping, "
            "as you requested.\n\nCase complete."
        )
        await ctx.yield_output(
            "Your replacement request for order 28939393 has been submitted with expedited shipping, "
        )
        await ctx.yield_output("as you requested.\n\nCase complete.")
        await ctx.yield_output(
            AgentResponse(
                messages=[
                    Message(role="user", contents=[Content.from_text("My order is 28939393.")]),
                    Message(role="assistant", contents=[Content.from_text(full_text)]),
                ]
            )
        )

    workflow = WorkflowBuilder(start_executor=responder).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    text_deltas = [event.delta for event in events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert text_deltas == [
        "Your replacement request for order 28939393 has been submitted with expedited shipping, ",
        "as you requested.\n\nCase complete.",
    ]


async def test_workflow_run_usage_content_emits_custom_usage_event() -> None:
    """Usage output from workflows should be surfaced as a custom usage event."""

    @executor(id="usage")
    async def usage(message: Any, ctx: WorkflowContext[Never, Content]) -> None:
        del message
        await ctx.yield_output(
            Content.from_usage(
                {
                    "input_token_count": 12,
                    "output_token_count": 6,
                    "total_token_count": 18,
                }
            )
        )

    workflow = WorkflowBuilder(start_executor=usage).build()
    events = [event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)]

    usage_events = [event for event in events if event.type == "CUSTOM" and event.name == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0].value["input_token_count"] == 12
    assert usage_events[0].value["output_token_count"] == 6
    assert usage_events[0].value["total_token_count"] == 18


async def test_workflow_run_accepts_multimodal_input_messages() -> None:
    """Workflow runner should normalize multimodal input into workflow Message content."""

    class CapturingWorkflow:
        def __init__(self) -> None:
            self.captured_message: list[Message] | None = None

        def run(self, **kwargs: Any):
            self.captured_message = cast(list[Message] | None, kwargs.get("message"))

            async def _stream():
                yield SimpleNamespace(type="started")

            return _stream()

    workflow = CapturingWorkflow()
    events = [
        event
        async for event in run_workflow_stream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Please analyze this image"},
                            {
                                "type": "image",
                                "source": {
                                    "type": "url",
                                    "url": "https://example.com/diagram.png",
                                    "mimeType": "image/png",
                                },
                            },
                        ],
                    }
                ]
            },
            cast(Any, workflow),
        )
    ]

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types

    assert workflow.captured_message is not None
    assert len(workflow.captured_message) == 1
    user_message = workflow.captured_message[0]
    assert user_message.role == "user"
    assert len(user_message.contents) == 2
    assert user_message.contents[0].type == "text"
    assert user_message.contents[0].text == "Please analyze this image"
    assert user_message.contents[1].type == "uri"
    assert user_message.contents[1].uri == "https://example.com/diagram.png"


def test_coerce_message_accepts_string_payload() -> None:
    """String values should coerce into a user Message with one text content."""
    message = _coerce_message("Please continue")
    assert message is not None
    assert message.role == "user"
    assert len(message.contents) == 1
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "Please continue"


def test_coerce_message_accepts_content_key_variant() -> None:
    """The 'content' key variant should map into Message.contents."""
    message = _coerce_message({"role": "assistant", "content": {"type": "text", "content": "Done"}})
    assert message is not None
    assert message.role == "assistant"
    assert len(message.contents) == 1
    assert message.contents[0].type == "text"
    assert message.contents[0].text == "Done"


def test_coerce_response_for_request_bool_int_float_and_mismatch() -> None:
    """Scalar coercion should enforce bool/int/float rules and return None on mismatches."""
    bool_request = SimpleNamespace(response_type=bool)
    assert _coerce_response_for_request(bool_request, True) is True
    assert _coerce_response_for_request(bool_request, "true") is True
    assert _coerce_response_for_request(bool_request, 1) is None

    int_request = SimpleNamespace(response_type=int)
    assert _coerce_response_for_request(int_request, 7) == 7
    assert _coerce_response_for_request(int_request, "7") == 7
    assert _coerce_response_for_request(int_request, True) is None

    float_request = SimpleNamespace(response_type=float)
    assert _coerce_response_for_request(float_request, 2) == 2
    assert _coerce_response_for_request(float_request, "2.5") == 2.5
    assert _coerce_response_for_request(float_request, True) is None

    dict_request = SimpleNamespace(response_type=dict)
    assert _coerce_response_for_request(dict_request, "[1,2,3]") is None


async def test_workflow_run_emits_run_error_when_stream_raises() -> None:
    """Unexpected stream exceptions should be converted into RUN_ERROR events."""

    class FailingWorkflow:
        def run(self, **kwargs: Any):
            del kwargs

            async def _stream():
                raise RuntimeError("workflow stream exploded")
                yield  # pragma: no cover

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]},
            cast(Any, FailingWorkflow()),
        )
    ]

    event_types = [event.type for event in events]
    assert event_types[0] == "RUN_STARTED"
    assert "RUN_ERROR" in event_types
    run_error = next(event for event in events if event.type == "RUN_ERROR")
    assert "workflow stream exploded" in run_error.message
