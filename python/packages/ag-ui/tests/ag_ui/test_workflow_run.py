# Copyright (c) Microsoft. All rights reserved.

"""Tests for native workflow AG-UI runner."""

import json
from enum import Enum
from types import SimpleNamespace
from typing import Any, cast

from ag_ui.core import EventType, StateSnapshotEvent
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
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
    _coerce_content,
    _coerce_json_value,
    _coerce_message,
    _coerce_message_content,
    _coerce_response_for_request,
    _coerce_responses_for_pending_requests,
    _custom_event_value,
    _details_code,
    _details_message,
    _extract_responses_from_messages,
    _interrupt_entry_for_request_event,
    _latest_assistant_contents,
    _latest_user_text,
    _message_role_value,
    _pending_request_events,
    _request_payload_from_request_event,
    _single_pending_response_from_value,
    _text_from_contents,
    _workflow_interrupt_event_value,
    _workflow_payload_to_contents,
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


# ── Helper function unit tests ──


class TestPendingRequestEvents:
    """Tests for _pending_request_events helper."""

    async def test_no_runner_context(self):
        """Workflow without _runner_context returns empty dict."""
        workflow = SimpleNamespace()
        result = await _pending_request_events(cast(Any, workflow))
        assert result == {}

    async def test_runner_context_missing_get_pending(self):
        """Runner context without get_pending_request_info_events returns empty."""
        workflow = SimpleNamespace(_runner_context=SimpleNamespace())
        result = await _pending_request_events(cast(Any, workflow))
        assert result == {}

    async def test_get_pending_returns_non_dict(self):
        """get_pending returning non-dict returns empty dict."""

        async def get_pending():
            return ["not", "a", "dict"]

        workflow = SimpleNamespace(_runner_context=SimpleNamespace(get_pending_request_info_events=get_pending))
        result = await _pending_request_events(cast(Any, workflow))
        assert result == {}


class TestInterruptEntryForRequestEvent:
    """Tests for _interrupt_entry_for_request_event helper."""

    def test_request_id_none(self):
        """request_id=None returns None."""
        event = SimpleNamespace(request_id=None)
        assert _interrupt_entry_for_request_event(event) is None

    def test_dict_data_used_directly(self):
        """Dict data is used as interrupt value."""
        event = SimpleNamespace(request_id="r1", data={"key": "val"})
        result = _interrupt_entry_for_request_event(event)
        assert result == {"id": "r1", "value": {"key": "val"}}

    def test_non_dict_data_wrapped(self):
        """Non-dict data is wrapped in {data: ...}."""
        event = SimpleNamespace(request_id="r1", data="text")
        result = _interrupt_entry_for_request_event(event)
        assert result == {"id": "r1", "value": {"data": "text"}}


class TestRequestPayloadFromRequestEvent:
    """Tests for _request_payload_from_request_event helper."""

    def test_falsy_request_id_returns_none(self):
        """Empty string request_id returns None."""
        event = SimpleNamespace(request_id="", request_type=None, response_type=None, data=None)
        assert _request_payload_from_request_event(event) is None


class TestCoerceJsonValue:
    """Tests for _coerce_json_value helper."""

    def test_empty_string(self):
        """Empty string returns original value."""
        assert _coerce_json_value("") == ""

    def test_whitespace_string(self):
        """Whitespace-only string returns original value."""
        assert _coerce_json_value("   ") == "   "

    def test_valid_json_parsed(self):
        """Valid JSON string is parsed."""
        assert _coerce_json_value('{"a": 1}') == {"a": 1}

    def test_invalid_json_returned_as_is(self):
        """Invalid JSON string returned as-is."""
        assert _coerce_json_value("not json") == "not json"

    def test_non_string_returned_as_is(self):
        """Non-string values returned as-is."""
        assert _coerce_json_value(42) == 42
        assert _coerce_json_value(None) is None


class TestCoerceContent:
    """Tests for _coerce_content helper."""

    def test_already_content(self):
        """Content object returned as-is."""
        content = Content.from_text(text="hello")
        assert _coerce_content(content) is content

    def test_non_dict_returns_none(self):
        """Non-dict value (after JSON parse) returns None."""
        assert _coerce_content([1, 2, 3]) is None
        assert _coerce_content(42) is None

    def test_auto_function_approval_response_type_attempted(self):
        """Dict with approved+id+function_call triggers the auto-type detection path."""
        # The function injects type="function_approval_response" into a copy,
        # but Content.from_dict may fail for complex nested types - returns None.
        value = {
            "approved": True,
            "id": "a1",
            "function_call": {"call_id": "c1", "name": "fn", "arguments": "{}"},
        }
        # Exercises the auto-detection code path even though result is None
        result = _coerce_content(value)
        assert result is None  # from_dict fails for this shape

    def test_valid_text_content_dict(self):
        """Dict with type=text converts successfully."""
        result = _coerce_content({"type": "text", "text": "hello"})
        assert result is not None
        assert result.type == "text"
        assert result.text == "hello"


class TestCoerceMessageContent:
    """Tests for _coerce_message_content helper."""

    def test_string_content(self):
        """String content creates text Content."""
        result = _coerce_message_content("hello")
        assert result is not None
        assert result.type == "text"
        assert result.text == "hello"

    def test_already_content_object(self):
        """Content object returned as-is."""
        content = Content.from_text(text="test")
        assert _coerce_message_content(content) is content

    def test_none_input_returns_none(self):
        """None input returns None."""
        assert _coerce_message_content(None) is None


class TestCoerceMessage:
    """Tests for _coerce_message helper."""

    def test_already_message(self):
        """Message object returned as-is."""
        msg = Message(role="user", contents=[Content.from_text(text="hi")])
        assert _coerce_message(msg) is msg

    def test_non_dict_non_str_returns_none(self):
        """Non-dict/str (e.g. int) returns None."""
        assert _coerce_message(123) is None

    def test_empty_contents(self):
        """Dict with no contents key gets empty text content."""
        msg = _coerce_message({"role": "user"})
        assert msg is not None
        assert len(msg.contents) == 1
        assert msg.contents[0].text == ""

    def test_dict_with_content_key_variant(self):
        """'content' key maps to contents."""
        msg = _coerce_message({"role": "assistant", "content": "Done"})
        assert msg is not None
        assert msg.role == "assistant"
        assert len(msg.contents) == 1


class TestCoerceResponseForRequest:
    """Tests for _coerce_response_for_request helper."""

    def test_response_type_none(self):
        """None response_type returns candidate as-is."""
        event = SimpleNamespace(response_type=None)
        assert _coerce_response_for_request(event, "hello") == "hello"

    def test_response_type_any(self):
        """Any response_type returns candidate as-is."""
        event = SimpleNamespace(response_type=Any)
        assert _coerce_response_for_request(event, {"a": 1}) == {"a": 1}

    def test_list_coercion_bare_list(self):
        """list without type args passes through."""
        event = SimpleNamespace(response_type=list)
        assert _coerce_response_for_request(event, [1, 2]) == [1, 2]

    def test_list_content_coercion(self):
        """list[Content] coerces dicts to Content objects."""
        event = SimpleNamespace(response_type=list[Content])
        result = _coerce_response_for_request(event, [{"type": "text", "text": "hi"}])
        assert result is not None
        assert len(result) == 1
        assert isinstance(result[0], Content)

    def test_list_message_coercion(self):
        """list[Message] coerces dicts to Message objects."""
        event = SimpleNamespace(response_type=list[Message])
        result = _coerce_response_for_request(event, [{"role": "user", "contents": [{"type": "text", "text": "hi"}]}])
        assert result is not None
        assert len(result) == 1
        assert isinstance(result[0], Message)

    def test_list_coercion_fails_returns_none(self):
        """list coercion returns None when items can't be converted."""
        event = SimpleNamespace(response_type=list[Content])
        result = _coerce_response_for_request(event, [None])
        assert result is None

    def test_str_coercion_from_dict(self):
        """str type coerces dict to JSON string."""
        event = SimpleNamespace(response_type=str)
        result = _coerce_response_for_request(event, {"a": 1})
        assert isinstance(result, str)
        assert '"a"' in result

    def test_unknown_type_mismatch(self):
        """Custom class type returns None for non-instance."""

        class Custom:
            pass

        event = SimpleNamespace(response_type=Custom)
        assert _coerce_response_for_request(event, "not_custom") is None

    def test_unknown_type_match(self):
        """Custom class type returns object if isinstance matches."""

        class Custom:
            pass

        obj = Custom()
        event = SimpleNamespace(response_type=Custom)
        assert _coerce_response_for_request(event, obj) is obj


class TestSinglePendingResponseFromValue:
    """Tests for _single_pending_response_from_value helper."""

    def test_missing_request_id(self):
        """Event with no request_id returns empty dict."""
        event = SimpleNamespace(response_type=str)
        pending = {"key": event}
        result = _single_pending_response_from_value(pending, "value")
        assert result == {}

    def test_multiple_pending_returns_empty(self):
        """Multiple pending events returns empty dict (ambiguous)."""
        e1 = SimpleNamespace(request_id="r1", response_type=str)
        e2 = SimpleNamespace(request_id="r2", response_type=str)
        result = _single_pending_response_from_value({"r1": e1, "r2": e2}, "val")
        assert result == {}


class TestCoerceResponsesForPendingRequests:
    """Tests for _coerce_responses_for_pending_requests helper."""

    def test_failed_coercion_skipped(self):
        """Incompatible type causes response to be skipped."""
        event = SimpleNamespace(response_type=bool)
        responses = {"r1": "not_a_bool"}
        pending = {"r1": event}
        result = _coerce_responses_for_pending_requests(responses, pending)
        assert "r1" not in result

    def test_unknown_request_id_preserved(self):
        """Responses for unknown request IDs are preserved as-is."""
        responses = {"unknown_id": "value"}
        pending = {}
        result = _coerce_responses_for_pending_requests(responses, pending)
        assert result == {"unknown_id": "value"}

    def test_empty_responses(self):
        """Empty responses dict returns responses unchanged."""
        result = _coerce_responses_for_pending_requests({}, {"r1": SimpleNamespace()})
        assert result == {}


class TestMessageRoleValue:
    """Tests for _message_role_value helper."""

    def test_string_role(self):
        """String role returned directly."""
        msg = Message(role="user", contents=[])
        assert _message_role_value(msg) == "user"

    def test_enum_role(self):
        """Enum-like role gets .value."""

        class Role(Enum):
            USER = "user"

        msg = SimpleNamespace(role=Role.USER)
        assert _message_role_value(cast(Any, msg)) == "user"


class TestLatestUserText:
    """Tests for _latest_user_text helper."""

    def test_only_assistant_messages(self):
        """Only assistant messages returns None."""
        messages = [Message(role="assistant", contents=[Content.from_text(text="hi")])]
        assert _latest_user_text(messages) is None

    def test_user_with_non_text_content(self):
        """User message with only non-text content returns None."""
        messages = [
            Message(role="user", contents=[Content.from_function_call(call_id="c1", name="fn", arguments="{}")])
        ]
        assert _latest_user_text(messages) is None

    def test_user_with_empty_text(self):
        """User message with empty/whitespace text returns None."""
        messages = [Message(role="user", contents=[Content.from_text(text="   ")])]
        assert _latest_user_text(messages) is None


class TestLatestAssistantContents:
    """Tests for _latest_assistant_contents helper."""

    def test_no_assistant_messages(self):
        """Only user messages returns None."""
        messages = [Message(role="user", contents=[Content.from_text(text="hi")])]
        assert _latest_assistant_contents(messages) is None

    def test_assistant_with_empty_contents(self):
        """Assistant message with empty contents returns None."""
        messages = [Message(role="assistant", contents=[])]
        assert _latest_assistant_contents(messages) is None


class TestTextFromContents:
    """Tests for _text_from_contents helper."""

    def test_empty_text_skipped(self):
        """Empty string text content is skipped."""
        contents = [Content.from_text(text="")]
        assert _text_from_contents(contents) is None

    def test_non_text_content_skipped(self):
        """Non-text content types are skipped."""
        contents = [Content.from_function_call(call_id="c1", name="fn", arguments="{}")]
        assert _text_from_contents(contents) is None


class TestWorkflowInterruptEventValue:
    """Tests for _workflow_interrupt_event_value helper."""

    def test_none_data(self):
        """None data returns None."""
        assert _workflow_interrupt_event_value({"data": None}) is None

    def test_string_data(self):
        """String data returned directly."""
        assert _workflow_interrupt_event_value({"data": "text"}) == "text"

    def test_dict_data_serialized(self):
        """Dict data is JSON-serialized."""
        result = _workflow_interrupt_event_value({"data": {"key": "val"}})
        assert json.loads(result) == {"key": "val"}


class TestWorkflowPayloadToContents:
    """Tests for _workflow_payload_to_contents helper."""

    def test_none_payload(self):
        """None payload returns None."""
        assert _workflow_payload_to_contents(None) is None

    def test_non_assistant_message(self):
        """User Message returns None."""
        msg = Message(role="user", contents=[Content.from_text(text="hi")])
        assert _workflow_payload_to_contents(msg) is None

    def test_agent_response_update_non_assistant(self):
        """AgentResponseUpdate with user role returns None."""
        update = AgentResponseUpdate(contents=[Content.from_text(text="hi")], role="user")
        assert _workflow_payload_to_contents(update) is None

    def test_agent_response_update_none_role(self):
        """AgentResponseUpdate with None role returns None."""
        update = AgentResponseUpdate(contents=[Content.from_text(text="hi")], role=None)
        assert _workflow_payload_to_contents(update) is None

    def test_list_with_none_item(self):
        """List containing None causes None return."""
        result = _workflow_payload_to_contents([Content.from_text(text="hi"), None])
        assert result is None

    def test_empty_list(self):
        """Empty list returns None."""
        assert _workflow_payload_to_contents([]) is None

    def test_string_payload(self):
        """String payload creates text content."""
        result = _workflow_payload_to_contents("hello")
        assert result is not None
        assert len(result) == 1
        assert result[0].type == "text"

    def test_content_payload(self):
        """Single Content returned as list."""
        content = Content.from_text(text="test")
        result = _workflow_payload_to_contents(content)
        assert result == [content]

    def test_unknown_type_returns_none(self):
        """Unknown types return None."""
        assert _workflow_payload_to_contents(42) is None


class TestCustomEventValue:
    """Tests for _custom_event_value helper."""

    def test_event_with_data(self):
        """Event with .data attribute returns data."""
        event = SimpleNamespace(type="custom", data={"progress": 50})
        assert _custom_event_value(event) == {"progress": 50}

    def test_event_without_data(self):
        """Event without .data returns filtered custom fields."""
        event = SimpleNamespace(type="custom", data=None, custom_field="value")
        result = _custom_event_value(event)
        assert result == {"custom_field": "value"}

    def test_event_with_no_custom_fields(self):
        """Event with only base fields returns None."""
        event = SimpleNamespace(type="custom", data=None)
        result = _custom_event_value(event)
        assert result is None


class TestDetailsMessage:
    """Tests for _details_message helper."""

    def test_none_details(self):
        """None details returns default message."""
        assert _details_message(None) == "Workflow execution failed."

    def test_details_with_message(self):
        """Details with .message attribute uses it."""
        details = SimpleNamespace(message="Custom error")
        assert _details_message(details) == "Custom error"

    def test_details_with_empty_message(self):
        """Details with empty .message falls back to str()."""
        details = SimpleNamespace(message="")
        result = _details_message(details)
        assert "message=" in result or result == str(details)

    def test_details_without_message(self):
        """Details without .message uses str()."""
        assert _details_message("plain string") == "plain string"


class TestDetailsCode:
    """Tests for _details_code helper."""

    def test_none_details(self):
        """None details returns None."""
        assert _details_code(None) is None

    def test_details_with_error_type(self):
        """Details with .error_type returns it."""
        details = SimpleNamespace(error_type="ValueError")
        assert _details_code(details) == "ValueError"

    def test_details_with_empty_error_type(self):
        """Details with empty .error_type returns None."""
        details = SimpleNamespace(error_type="")
        assert _details_code(details) is None

    def test_details_without_error_type(self):
        """Details without .error_type returns None."""
        details = SimpleNamespace(message="err")
        assert _details_code(details) is None


class TestExtractResponsesFromMessages:
    """Tests for _extract_responses_from_messages helper."""

    def test_function_result_extracted(self):
        """function_result content is extracted keyed by call_id."""
        result = Content.from_function_result(call_id="call-1", result="ok")
        messages = [Message(role="tool", contents=[result])]
        responses = _extract_responses_from_messages(messages)
        assert responses == {"call-1": "ok"}

    def test_function_result_without_call_id_skipped(self):
        """function_result with no call_id is ignored."""
        result = Content.from_function_result(call_id="", result="ok")
        messages = [Message(role="tool", contents=[result])]
        responses = _extract_responses_from_messages(messages)
        assert responses == {}

    def test_function_approval_response_extracted(self):
        """function_approval_response content is extracted keyed by id."""
        func_call = Content.from_function_call(
            call_id="call-1",
            name="do_action",
            arguments={"x": 1},
        )
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval-1",
            function_call=func_call,
        )
        messages = [Message(role="user", contents=[approval])]
        responses = _extract_responses_from_messages(messages)
        assert "approval-1" in responses
        assert responses["approval-1"]["approved"] is True
        assert responses["approval-1"]["id"] == "approval-1"
        assert "function_call" in responses["approval-1"]

    def test_denied_approval_response_extracted(self):
        """Denied function_approval_response is extracted with approved=False."""
        func_call = Content.from_function_call(
            call_id="call-2",
            name="delete_item",
            arguments={},
        )
        approval = Content.from_function_approval_response(
            approved=False,
            id="approval-2",
            function_call=func_call,
        )
        messages = [Message(role="user", contents=[approval])]
        responses = _extract_responses_from_messages(messages)
        assert "approval-2" in responses
        assert responses["approval-2"]["approved"] is False

    def test_mixed_result_and_approval(self):
        """Both function_result and function_approval_response are extracted."""
        result = Content.from_function_result(call_id="call-1", result="done")
        func_call = Content.from_function_call(
            call_id="call-2",
            name="submit",
            arguments={},
        )
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval-1",
            function_call=func_call,
        )
        messages = [
            Message(role="tool", contents=[result]),
            Message(role="user", contents=[approval]),
        ]
        responses = _extract_responses_from_messages(messages)
        assert "call-1" in responses
        assert responses["call-1"] == "done"
        assert "approval-1" in responses
        assert responses["approval-1"]["approved"] is True

    def test_mixed_result_and_approval_same_message(self):
        """Both function_result and function_approval_response in the same message are extracted."""
        result = Content.from_function_result(call_id="call-1", result="done")
        func_call = Content.from_function_call(
            call_id="call-2",
            name="submit",
            arguments={},
        )
        approval = Content.from_function_approval_response(
            approved=True,
            id="approval-1",
            function_call=func_call,
        )
        messages = [Message(role="tool", contents=[result, approval])]
        responses = _extract_responses_from_messages(messages)
        assert "call-1" in responses
        assert responses["call-1"] == "done"
        assert "approval-1" in responses
        assert responses["approval-1"]["approved"] is True

    def test_text_content_skipped(self):
        """Non-result, non-approval content is ignored."""
        text = Content.from_text(text="hello")
        messages = [Message(role="user", contents=[text])]
        responses = _extract_responses_from_messages(messages)
        assert responses == {}

    def test_empty_messages(self):
        """Empty message list returns empty responses."""
        assert _extract_responses_from_messages([]) == {}


# ── Stream integration tests ──


async def test_workflow_run_approval_via_messages_approved() -> None:
    """Approval response sent via messages (function_approvals) should satisfy the pending request."""

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
            await ctx.yield_output(f"Refund {status}.")

    workflow = WorkflowBuilder(start_executor=ApprovalExecutor()).build()
    first_events = [
        event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)
    ]
    first_finished = [event for event in first_events if event.type == "RUN_FINISHED"][0].model_dump()
    interrupt_payload = cast(list[dict[str, Any]], first_finished.get("interrupt"))
    assert isinstance(interrupt_payload, list) and len(interrupt_payload) == 1

    # Second turn: send approval via function_approvals on a message (not resume.interrupts)
    resumed_events = [
        event
        async for event in run_workflow_stream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "",
                        "function_approvals": [
                            {
                                "approved": True,
                                "id": "approval-1",
                                "call_id": "refund-call",
                                "name": "submit_refund",
                                "arguments": {"order_id": "12345", "amount": "$89.99"},
                            }
                        ],
                    }
                ],
            },
            workflow,
        )
    ]

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_STARTED" in resumed_types
    assert "RUN_FINISHED" in resumed_types
    assert "RUN_ERROR" not in resumed_types
    assert "TEXT_MESSAGE_CONTENT" in resumed_types
    text_deltas = [event.delta for event in resumed_events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert any("approved" in delta for delta in text_deltas)
    resumed_finished = [event for event in resumed_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert not resumed_finished.get("interrupt")


async def test_workflow_run_approval_via_messages_denied() -> None:
    """Denied approval response sent via messages (function_approvals) should satisfy the pending request."""

    class ApprovalExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id="approval_executor")

        @handler
        async def start(self, message: Any, ctx: WorkflowContext) -> None:
            del message
            function_call = Content.from_function_call(
                call_id="delete-call",
                name="delete_record",
                arguments={"record_id": "abc"},
            )
            approval_request = Content.from_function_approval_request(id="deny-1", function_call=function_call)
            await ctx.request_info(approval_request, Content, request_id="deny-1")

        @response_handler
        async def handle_approval(self, original_request: Content, response: Content, ctx: WorkflowContext) -> None:
            del original_request
            status = "approved" if bool(response.approved) else "rejected"
            await ctx.yield_output(f"Delete {status}.")

    workflow = WorkflowBuilder(start_executor=ApprovalExecutor()).build()
    first_events = [
        event async for event in run_workflow_stream({"messages": [{"role": "user", "content": "go"}]}, workflow)
    ]
    first_finished = [event for event in first_events if event.type == "RUN_FINISHED"][0].model_dump()
    interrupt_payload = cast(list[dict[str, Any]], first_finished.get("interrupt"))
    assert isinstance(interrupt_payload, list) and len(interrupt_payload) == 1

    # Second turn: send denial via function_approvals on a message (not resume.interrupts)
    resumed_events = [
        event
        async for event in run_workflow_stream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "",
                        "function_approvals": [
                            {
                                "approved": False,
                                "id": "deny-1",
                                "call_id": "delete-call",
                                "name": "delete_record",
                                "arguments": {"record_id": "abc"},
                            }
                        ],
                    }
                ],
            },
            workflow,
        )
    ]

    resumed_types = [event.type for event in resumed_events]
    assert "RUN_STARTED" in resumed_types
    assert "RUN_FINISHED" in resumed_types
    assert "RUN_ERROR" not in resumed_types
    assert "TEXT_MESSAGE_CONTENT" in resumed_types
    text_deltas = [event.delta for event in resumed_events if event.type == "TEXT_MESSAGE_CONTENT"]
    assert any("rejected" in delta for delta in text_deltas)
    resumed_finished = [event for event in resumed_events if event.type == "RUN_FINISHED"][0].model_dump()
    assert not resumed_finished.get("interrupt")


async def test_workflow_run_available_interrupts_logged():
    """available_interrupts in input data should be logged without errors."""

    @executor(id="noop")
    async def noop(message: Any, ctx: WorkflowContext) -> None:
        pass

    workflow = WorkflowBuilder(start_executor=noop).build()
    input_data = {
        "messages": [{"role": "user", "content": "go"}],
        "available_interrupts": [{"id": "req_1", "type": "request_info"}],
    }

    events = [event async for event in run_workflow_stream(input_data, workflow)]
    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types
    assert "RUN_ERROR" not in event_types


async def test_workflow_run_failed_event():
    """Workflow 'failed' event should produce RUN_ERROR."""

    class FailingWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(
                    type="failed", details=SimpleNamespace(message="it broke", error_type="TestError")
                )

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, FailingWorkflow())
        )
    ]

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_ERROR" in event_types
    error_event = next(e for e in events if e.type == "RUN_ERROR")
    assert error_event.message == "it broke"
    assert error_event.code == "TestError"


async def test_workflow_run_status_enum_state():
    """Status events with enum-like state should be handled."""

    class WorkflowState(Enum):
        IDLE = "idle"

    class StatusWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(type="status", state=WorkflowState.IDLE)

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, StatusWorkflow())
        )
    ]

    event_types = [event.type for event in events]
    assert "RUN_STARTED" in event_types
    assert "RUN_FINISHED" in event_types


async def test_workflow_run_executor_invoked_drains_text():
    """executor_invoked should drain any open text message."""

    class ExecutorWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(type="output", data="Hello world")
                yield SimpleNamespace(type="executor_invoked", executor_id="agent_1", data=None)
                yield SimpleNamespace(type="executor_completed", executor_id="agent_1", data=None)

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, ExecutorWorkflow())
        )
    ]

    # Text should end before executor step starts
    text_end_idx = next(i for i, e in enumerate(events) if e.type == "TEXT_MESSAGE_END")
    step_start_idx = next(i for i, e in enumerate(events) if e.type == "STEP_STARTED")
    assert text_end_idx < step_start_idx


async def test_workflow_run_executor_failed_event():
    """executor_failed event should emit activity snapshot with failed status."""

    class ExecutorFailWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(
                    type="executor_failed",
                    executor_id="agent_1",
                    details=SimpleNamespace(message="agent crashed"),
                )

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, ExecutorFailWorkflow())
        )
    ]

    activity = [e for e in events if e.type == "ACTIVITY_SNAPSHOT"]
    assert len(activity) == 1
    assert activity[0].content["status"] == "failed"
    assert activity[0].content["details"]["message"] == "agent crashed"


async def test_workflow_run_list_base_event_output():
    """Workflow yielding list of BaseEvent objects should emit each."""

    class ListEventWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(
                    type="output",
                    data=[
                        StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot={"a": 1}),
                        StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot={"b": 2}),
                    ],
                )

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, ListEventWorkflow())
        )
    ]

    snapshots = [e for e in events if e.type == "STATE_SNAPSHOT"]
    assert len(snapshots) == 2
    assert snapshots[0].snapshot == {"a": 1}
    assert snapshots[1].snapshot == {"b": 2}


async def test_workflow_run_late_run_started():
    """If no events emitted, RUN_STARTED still emitted at end."""

    class EmptyWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                return
                yield  # pragma: no cover

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, EmptyWorkflow())
        )
    ]

    assert events[0].type == "RUN_STARTED"
    assert events[-1].type == "RUN_FINISHED"


async def test_workflow_run_last_assistant_text_update():
    """Text outputs update last_assistant_text for dedup tracking."""

    class DualTextWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(type="output", data="First text")
                yield SimpleNamespace(type="output", data="Second text")

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, DualTextWorkflow())
        )
    ]

    text_deltas = [e.delta for e in events if e.type == "TEXT_MESSAGE_CONTENT"]
    assert "First text" in text_deltas
    assert "Second text" in text_deltas


async def test_workflow_run_superstep_events():
    """superstep_started/completed emit Step events with iteration."""

    class SuperstepWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(type="superstep_started", iteration=1)
                yield SimpleNamespace(type="superstep_completed", iteration=1)

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, SuperstepWorkflow())
        )
    ]

    step_started = [e for e in events if e.type == "STEP_STARTED"]
    step_finished = [e for e in events if e.type == "STEP_FINISHED"]
    assert len(step_started) == 1
    assert step_started[0].step_name == "superstep:1"
    assert len(step_finished) == 1
    assert step_finished[0].step_name == "superstep:1"


async def test_workflow_run_non_terminal_status_emits_custom():
    """Non-terminal status events emit custom events."""

    class StatusWorkflow:
        def run(self, **kwargs: Any):
            async def _stream():
                yield SimpleNamespace(type="started")
                yield SimpleNamespace(type="status", state="running")

            return _stream()

    events = [
        event
        async for event in run_workflow_stream(
            {"messages": [{"role": "user", "content": "go"}]}, cast(Any, StatusWorkflow())
        )
    ]

    custom = [e for e in events if e.type == "CUSTOM" and e.name == "status"]
    assert len(custom) == 1
    assert custom[0].value == {"state": "running"}
