# Copyright (c) Microsoft. All rights reserved.

import re
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import (
    Agent,
    BaseContextProvider,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
    WorkflowEvent,
    resolve_agent_id,
    tool,
)
from agent_framework._clients import BaseChatClient
from agent_framework._middleware import ChatMiddlewareLayer, FunctionInvocationContext, MiddlewareTermination
from agent_framework._tools import FunctionInvocationLayer, FunctionTool
from agent_framework.orchestrations import HandoffAgentUserRequest, HandoffBuilder

from agent_framework_orchestrations._handoff import (
    HANDOFF_FUNCTION_RESULT_KEY,
    HandoffAgentExecutor,
    HandoffConfiguration,
    _AutoHandoffMiddleware,  # pyright: ignore[reportPrivateUsage]
    get_handoff_tool_name,
)
from agent_framework_orchestrations._orchestrator_helpers import clean_conversation_for_handoff


class MockChatClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Mock chat client for testing handoff workflows."""

    def __init__(
        self,
        *,
        name: str = "",
        handoff_to: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the mock chat client.

        Args:
            name: The name of the agent using this chat client.
            handoff_to: The name of the agent to hand off to, or None for no handoff.
                This is hardcoded for testing purposes so that the agent always attempts to hand off.
        """
        ChatMiddlewareLayer.__init__(self)
        FunctionInvocationLayer.__init__(self)
        BaseChatClient.__init__(self)
        self._name = name
        self._handoff_to = handoff_to
        self._call_index = 0

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:
            return self._build_streaming_response(options=dict(options))

        async def _get() -> ChatResponse:
            contents = _build_reply_contents(self._name, self._handoff_to, self._next_call_id())
            reply = Message(
                role="assistant",
                contents=contents,
            )
            return ChatResponse(messages=reply, response_id="mock_response")

        return _get()

    def _build_streaming_response(self, *, options: dict[str, Any]) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            contents = _build_reply_contents(self._name, self._handoff_to, self._next_call_id())
            yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            response_format = options.get("response_format")
            output_format_type = response_format if isinstance(response_format, type) else None
            return ChatResponse.from_updates(updates, output_format_type=output_format_type)

        return ResponseStream(_stream(), finalizer=_finalize)

    def _next_call_id(self) -> str | None:
        if not self._handoff_to:
            return None
        call_id = f"{self._name}-handoff-{self._call_index}"
        self._call_index += 1
        return call_id


def _build_reply_contents(
    agent_name: str,
    handoff_to: str | None,
    call_id: str | None,
) -> list[Content]:
    contents: list[Content] = []
    if handoff_to and call_id:
        contents.append(
            Content.from_function_call(
                call_id=call_id, name=f"handoff_to_{handoff_to}", arguments={"handoff_to": handoff_to}
            )
        )
    text = f"{agent_name} reply"
    contents.append(Content.from_text(text=text))
    return contents


class MockHandoffAgent(Agent):
    """Mock agent that can hand off to another agent."""

    def __init__(
        self,
        *,
        name: str,
        handoff_to: str | None = None,
    ) -> None:
        """Initialize the mock handoff agent.

        Args:
            name: The name of the agent.
            handoff_to: The name of the agent to hand off to, or None for no handoff.
                This is hardcoded for testing purposes so that the agent always attempts to hand off.
        """
        super().__init__(client=MockChatClient(name=name, handoff_to=handoff_to), name=name, id=name)


class ContextAwareRefundClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Mock client that expects prior user context to remain available on resume."""

    def __init__(self) -> None:
        ChatMiddlewareLayer.__init__(self)
        FunctionInvocationLayer.__init__(self)
        BaseChatClient.__init__(self)
        self._call_index = 0

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        del kwargs
        del options

        contents = self._next_contents(messages)
        if stream:
            return self._build_streaming_response(contents)

        async def _get() -> ChatResponse:
            return ChatResponse(messages=[Message(role="assistant", contents=contents)], response_id="context-aware")

        return _get()

    def _build_streaming_response(self, contents: list[Content]) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            return ChatResponse.from_updates(updates)

        return ResponseStream(_stream(), finalizer=_finalize)

    def _next_contents(self, messages: Sequence[Message]) -> list[Content]:
        user_text = " ".join(message.text or "" for message in messages if message.role == "user")
        order_match = re.search(r"\b(\d{4,12})\b", user_text)
        order_id = order_match.group(1) if order_match else None
        asks_refund = any(token in user_text.lower() for token in ("broken", "damaged", "refund", "cracked"))

        if self._call_index == 0:
            reply = "Refund Agent: Please share your order number."
        elif self._call_index == 1:
            if order_id:
                reply = f"Refund Agent: Thanks, I found order {order_id}. Why do you need the refund?"
            else:
                reply = "Refund Agent: I still need your order number."
        else:
            if order_id and asks_refund:
                reply = f"Refund Agent: Got it for order {order_id}. I can proceed with your refund."
            else:
                reply = "Refund Agent: I still need your order number."

        self._call_index += 1
        return [Content.from_text(text=reply)]


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    return [event async for event in stream]


async def test_handoff():
    """Test that agents can hand off to each other."""

    # `triage` hands off to `specialist`, who then hands off to `escalation`.
    # `escalation` has no handoff, so the workflow should request user input to continue.
    triage = MockHandoffAgent(name="triage", handoff_to="specialist")
    specialist = MockHandoffAgent(name="specialist", handoff_to="escalation")
    escalation = MockHandoffAgent(name="escalation")

    # Without explicitly defining handoffs, the builder will create connections
    # between all agents.
    workflow = (
        HandoffBuilder(
            participants=[triage, specialist, escalation],
            termination_condition=lambda conv: sum(1 for m in conv if m.role == "user") >= 2,
        )
        .with_start_agent(triage)
        .build()
    )

    # Start conversation - triage hands off to specialist then escalation
    # escalation won't trigger a handoff, so the response from it will become
    # a request for user input because autonomous mode is not enabled by default.
    events = await _drain(workflow.run("Need technical support", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]

    assert requests
    assert len(requests) == 1

    request = requests[0]
    assert isinstance(request.data, HandoffAgentUserRequest)
    assert request.source_executor_id == escalation.name


def _latest_request_info_event(events: list[WorkflowEvent]) -> WorkflowEvent[Any]:
    request_events = [event for event in events if event.type == "request_info"]
    assert request_events
    request_event = request_events[-1]
    assert isinstance(request_event.data, HandoffAgentUserRequest)
    return request_event


def _request_text(event: WorkflowEvent[Any]) -> str:
    request_payload = cast(HandoffAgentUserRequest, event.data)
    messages = request_payload.agent_response.messages
    assert messages
    return messages[-1].text or ""


async def test_resume_keeps_prior_user_context_for_same_agent() -> None:
    """Ensure same-agent request_info resumes retain prior turn context."""
    refund_agent = Agent(
        id="refund_agent",
        name="refund_agent",
        client=ContextAwareRefundClient(),
    )
    workflow = (
        HandoffBuilder(participants=[refund_agent], termination_condition=lambda _: False)
        .with_start_agent(refund_agent)
        .build()
    )

    first_events = await _drain(workflow.run("My order arrived damaged.", stream=True))
    first_request = _latest_request_info_event(first_events)
    assert "order number" in _request_text(first_request).lower()

    second_events = await _drain(
        workflow.run(
            stream=True,
            responses={first_request.request_id: [Message(role="user", text="Order 2939393")]},
        )
    )
    second_request = _latest_request_info_event(second_events)
    second_text = _request_text(second_request).lower()
    assert "order 2939393" in second_text
    assert "order number" not in second_text

    third_events = await _drain(
        workflow.run(
            stream=True,
            responses={second_request.request_id: [Message(role="user", text="It arrived broken and unusable.")]},
        )
    )
    third_request = _latest_request_info_event(third_events)
    third_text = _request_text(third_request).lower()
    assert "order 2939393" in third_text
    assert "order number" not in third_text


async def test_tool_approval_responses_are_not_replayed_from_history() -> None:
    """Ensure persisted history does not re-execute previously approved tool calls."""
    execution_count = 0

    @tool(name="submit_refund_counted", approval_mode="always_require")
    def submit_refund_counted() -> str:
        nonlocal execution_count
        execution_count += 1
        return "ok"

    class ApprovalReplayClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)
            self._call_index = 0

        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            del messages
            del options
            del kwargs

            if self._call_index == 0:
                contents = [
                    Content.from_function_call(
                        call_id="refund-call-1",
                        name="submit_refund_counted",
                        arguments={},
                    )
                ]
            elif self._call_index == 1:
                contents = [Content.from_text(text="Refund approved and recorded.")]
            else:
                contents = [Content.from_text(text="No additional tool work needed.")]
            self._call_index += 1

            if stream:

                async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                    yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

                return ResponseStream(_stream(), finalizer=lambda updates: ChatResponse.from_updates(updates))

            async def _get() -> ChatResponse:
                return ChatResponse(
                    messages=[Message(role="assistant", contents=contents)],
                    response_id="approval-replay",
                )

            return _get()

    agent = Agent(
        id="refund_agent",
        name="refund_agent",
        client=ApprovalReplayClient(),
        tools=[submit_refund_counted],
    )
    workflow = (
        HandoffBuilder(participants=[agent], termination_condition=lambda _: False).with_start_agent(agent).build()
    )

    first_events = await _drain(workflow.run("start", stream=True))
    first_requests = [event for event in first_events if event.type == "request_info"]
    assert first_requests
    first_request = first_requests[-1]
    assert isinstance(first_request.data, Content)
    approval_response = first_request.data.to_function_approval_response(approved=True)

    second_events = await _drain(workflow.run(stream=True, responses={first_request.request_id: approval_response}))
    second_request = _latest_request_info_event(second_events)

    await _drain(
        workflow.run(
            stream=True,
            responses={second_request.request_id: [Message(role="user", text="Thanks, what's next?")]},
        )
    )

    assert execution_count == 1


async def test_handoff_resume_preserves_approval_function_call_for_stateless_runs() -> None:
    """Approval resume turns must replay matching function calls when store=False."""

    @tool(name="submit_refund", approval_mode="always_require")
    def submit_refund() -> str:
        return "ok"

    class StrictStatelessApprovalClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)
            self._call_index = 0
            self.resume_validated = False

        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            del options
            del kwargs

            if self._call_index == 0:
                contents = [
                    Content.from_function_call(
                        call_id="refund-call-1",
                        name="submit_refund",
                        arguments={},
                    )
                ]
            else:
                function_call_ids = {
                    content.call_id
                    for message in messages
                    for content in message.contents
                    if content.type == "function_call" and content.call_id
                }
                function_result_ids = {
                    content.call_id
                    for message in messages
                    for content in message.contents
                    if content.type == "function_result" and content.call_id
                }
                missing_call_ids = sorted(function_result_ids - function_call_ids)
                if missing_call_ids:
                    raise AssertionError(
                        f"No tool call found for function call output with call_id {missing_call_ids[0]}."
                    )
                self.resume_validated = True
                contents = [Content.from_text(text="Refund submitted.")]

            self._call_index += 1

            if stream:

                async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                    yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

                return ResponseStream(_stream(), finalizer=lambda updates: ChatResponse.from_updates(updates))

            async def _get() -> ChatResponse:
                return ChatResponse(
                    messages=[Message(role="assistant", contents=contents)],
                    response_id="strict-stateless",
                )

            return _get()

    client = StrictStatelessApprovalClient()
    agent = Agent(
        id="refund_agent",
        name="refund_agent",
        client=client,
        tools=[submit_refund],
    )
    workflow = (
        HandoffBuilder(participants=[agent], termination_condition=lambda _: False).with_start_agent(agent).build()
    )

    first_events = await _drain(workflow.run("start", stream=True))
    approval_requests = [
        event for event in first_events if event.type == "request_info" and isinstance(event.data, Content)
    ]
    assert approval_requests
    first_request = approval_requests[0]

    approval_response = first_request.data.to_function_approval_response(True)
    await _drain(workflow.run(stream=True, responses={first_request.request_id: approval_response}))

    assert client.resume_validated is True


async def test_handoff_replay_serializes_handoff_function_results() -> None:
    """Returning to the same agent must not replay dict tool outputs."""

    class ReplaySafeHandoffClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
        def __init__(self, name: str, handoff_sequence: list[str | None]) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)
            self._name = name
            self._handoff_sequence = handoff_sequence
            self._call_index = 0

        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            del options
            del kwargs

            for message in messages:
                for content in message.contents:
                    if content.type == "function_result" and isinstance(content.result, dict):
                        raise AssertionError("Expected replayed function_result payloads to be JSON strings.")

            handoff_to = (
                self._handoff_sequence[self._call_index] if self._call_index < len(self._handoff_sequence) else None
            )
            call_id = f"{self._name}-handoff-{self._call_index}" if handoff_to else None
            contents = _build_reply_contents(self._name, handoff_to, call_id)
            self._call_index += 1

            if stream:

                async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                    yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

                return ResponseStream(_stream(), finalizer=lambda updates: ChatResponse.from_updates(updates))

            async def _get() -> ChatResponse:
                return ChatResponse(messages=[Message(role="assistant", contents=contents)], response_id="replay-safe")

            return _get()

    triage = Agent(
        id="triage",
        name="triage",
        client=ReplaySafeHandoffClient(name="triage", handoff_sequence=["specialist", None]),
    )
    specialist = Agent(
        id="specialist",
        name="specialist",
        client=ReplaySafeHandoffClient(name="specialist", handoff_sequence=["triage"]),
    )

    workflow = (
        HandoffBuilder(participants=[triage, specialist], termination_condition=lambda _: False)
        .with_start_agent(triage)
        .build()
    )

    events = await _drain(workflow.run("start", stream=True))
    requests = [event for event in events if event.type == "request_info"]
    assert requests
    assert requests[-1].source_executor_id == triage.name


async def test_handoff_resume_preserves_approved_tool_output_for_stateless_runs() -> None:
    """Approved calls must keep function_call/function_result pairs for later replays."""
    submit_call_id = "call_submit_refund_approved"

    @tool(name="submit_refund", approval_mode="always_require")
    def submit_refund() -> str:
        return "submitted"

    class RefundReplayClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)
            self._call_index = 0
            self.resume_validated = False

        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            del options
            del kwargs

            if self._call_index == 0:
                contents = [Content.from_function_call(call_id=submit_call_id, name="submit_refund", arguments={})]
            elif self._call_index == 1:
                contents = _build_reply_contents("refund_agent", "order_agent", "refund-order-handoff-1")
            else:
                function_call_ids = {
                    content.call_id
                    for message in messages
                    for content in message.contents
                    if content.type == "function_call" and content.call_id
                }
                function_result_ids = {
                    content.call_id
                    for message in messages
                    for content in message.contents
                    if content.type == "function_result" and content.call_id
                }
                if submit_call_id in function_call_ids and submit_call_id not in function_result_ids:
                    raise AssertionError(f"No tool output found for function call {submit_call_id}.")
                self.resume_validated = True
                contents = [Content.from_text(text="Refund agent resumed.")]

            self._call_index += 1

            if stream:

                async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                    yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

                return ResponseStream(_stream(), finalizer=lambda updates: ChatResponse.from_updates(updates))

            async def _get() -> ChatResponse:
                return ChatResponse(
                    messages=[Message(role="assistant", contents=contents)],
                    response_id="refund-replay",
                )

            return _get()

    class OrderReplayClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)
            self._call_index = 0

        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            del messages
            del options
            del kwargs

            if self._call_index == 0:
                contents = [Content.from_text(text="Would you like a replacement or a refund?")]
            else:
                contents = _build_reply_contents("order_agent", "refund_agent", "order-refund-handoff-1")
            self._call_index += 1

            if stream:

                async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                    yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

                return ResponseStream(_stream(), finalizer=lambda updates: ChatResponse.from_updates(updates))

            async def _get() -> ChatResponse:
                return ChatResponse(messages=[Message(role="assistant", contents=contents)], response_id="order-replay")

            return _get()

    refund_client = RefundReplayClient()
    refund_agent = Agent(
        id="refund_agent",
        name="refund_agent",
        client=refund_client,
        tools=[submit_refund],
    )
    order_agent = Agent(
        id="order_agent",
        name="order_agent",
        client=OrderReplayClient(),
    )
    workflow = (
        HandoffBuilder(participants=[refund_agent, order_agent], termination_condition=lambda _: False)
        .with_start_agent(refund_agent)
        .build()
    )

    first_events = await _drain(workflow.run("start", stream=True))
    approval_requests = [
        event for event in first_events if event.type == "request_info" and isinstance(event.data, Content)
    ]
    assert approval_requests
    approval_request = approval_requests[-1]
    approval_response = approval_request.data.to_function_approval_response(True)

    second_events = await _drain(workflow.run(stream=True, responses={approval_request.request_id: approval_response}))
    order_request = _latest_request_info_event(second_events)
    assert order_request.source_executor_id == order_agent.name

    await _drain(
        workflow.run(
            stream=True,
            responses={order_request.request_id: [Message(role="user", text="Please continue with refund.")]},
        )
    )

    assert refund_client.resume_validated is True


def test_handoff_clone_disables_provider_side_storage() -> None:
    """Handoff executors should force store=False to avoid stale provider call state."""
    triage = MockHandoffAgent(name="triage")
    workflow = HandoffBuilder(participants=[triage]).with_start_agent(triage).build()

    executor = workflow.executors[resolve_agent_id(triage)]
    assert isinstance(executor, HandoffAgentExecutor)
    assert executor._agent.default_options.get("store") is False


async def test_handoff_clears_stale_service_session_id_before_run() -> None:
    """Stale service session IDs must be dropped before each handoff agent turn."""
    triage = MockHandoffAgent(name="triage", handoff_to="specialist")
    specialist = MockHandoffAgent(name="specialist")
    workflow = HandoffBuilder(participants=[triage, specialist]).with_start_agent(triage).build()

    triage_executor = workflow.executors[resolve_agent_id(triage)]
    assert isinstance(triage_executor, HandoffAgentExecutor)
    triage_executor._session.service_session_id = "resp_stale_value"

    await _drain(workflow.run("My order is damaged", stream=True))

    assert triage_executor._session.service_session_id is None


def test_clean_conversation_for_handoff_keeps_text_only_history() -> None:
    """Tool-control messages must be excluded from persisted handoff history."""
    function_call = Content.from_function_call(
        call_id="handoff-call-1",
        name="handoff_to_refund_agent",
        arguments={"context": "route to refund"},
    )
    approval_response = Content.from_function_approval_response(
        approved=True,
        id="approval-1",
        function_call=function_call,
    )

    conversation = [
        Message(role="user", text="My order arrived damaged."),
        Message(
            role="assistant",
            contents=[
                function_call,
                Content.from_text(text="Triage Agent: Routing you to Refund."),
            ],
        ),
        Message(role="tool", contents=[Content.from_function_result(call_id="handoff-call-1", result="ok")]),
        Message(role="user", contents=[approval_response]),
        Message(
            role="assistant",
            contents=[Content.from_function_call(call_id="handoff-call-2", name="handoff_to_order_agent")],
        ),
    ]

    cleaned = clean_conversation_for_handoff(conversation)
    assert [message.role for message in cleaned] == ["user", "assistant"]
    assert [message.text for message in cleaned] == [
        "My order arrived damaged.",
        "Triage Agent: Routing you to Refund.",
    ]


def test_persist_missing_approved_function_results_handles_runtime_and_fallback_outputs() -> None:
    """Persisted history should retain approved call outputs across runtime shapes."""
    agent = MockHandoffAgent(name="triage")
    executor = HandoffAgentExecutor(agent, handoffs=[])

    call_with_runtime_result = "call-runtime-result"
    call_with_approval_only = "call-approval-only"

    executor._full_conversation = [
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id=call_with_runtime_result, name="submit_refund", arguments={}),
                Content.from_function_call(call_id=call_with_approval_only, name="submit_refund", arguments={}),
            ],
        )
    ]

    approval_response = Content.from_function_approval_response(
        approved=True,
        id=call_with_approval_only,
        function_call=Content.from_function_call(call_id=call_with_approval_only, name="submit_refund", arguments={}),
    )
    runtime_messages = [
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id=call_with_runtime_result, result='{"submitted":true}')],
        ),
        Message(role="user", contents=[approval_response]),
    ]

    executor._persist_missing_approved_function_results(runtime_tool_messages=runtime_messages, response_messages=[])

    persisted_tool_messages = [message for message in executor._full_conversation if message.role == "tool"]
    assert persisted_tool_messages
    persisted_results = [
        content
        for message in persisted_tool_messages
        for content in message.contents
        if content.type == "function_result" and content.call_id
    ]
    result_by_call_id = {content.call_id: content.result for content in persisted_results}
    assert result_by_call_id[call_with_runtime_result] == '{"submitted":true}'
    assert result_by_call_id[call_with_approval_only] == '{"status":"approved"}'


async def test_autonomous_mode_yields_output_without_user_request():
    """Ensure autonomous interaction mode yields output without requesting user input."""
    triage = MockHandoffAgent(name="triage", handoff_to="specialist")
    specialist = MockHandoffAgent(name="specialist")

    workflow = (
        HandoffBuilder(
            participants=[triage, specialist],
            # This termination condition ensures the workflow runs through both agents.
            # First message is the user message to triage, second is triage's response, which
            # is a handoff to specialist, third is specialist's response that should not request
            # user input due to autonomous mode. Fourth message will come from the specialist
            # again and will trigger termination.
            termination_condition=lambda conv: len(conv) >= 4,
        )
        .with_start_agent(triage)
        # Since specialist has no handoff, the specialist will be generating normal responses.
        # With autonomous mode, this should continue until the termination condition is met.
        .with_autonomous_mode(
            agents=[specialist],
            turn_limits={resolve_agent_id(specialist): 1},
        )
        .build()
    )

    events = await _drain(workflow.run("Package arrived broken", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]
    assert not requests, "Autonomous mode should not request additional user input"

    outputs = [ev for ev in events if ev.type == "output"]
    assert outputs, "Autonomous mode should yield a workflow output"

    final_conversation = outputs[-1].data
    assert isinstance(final_conversation, list)
    conversation_list = cast(list[Message], final_conversation)
    assert any(msg.role == "assistant" and (msg.text or "").startswith("specialist reply") for msg in conversation_list)


async def test_autonomous_mode_resumes_user_input_on_turn_limit():
    """Autonomous mode should resume user input request when turn limit is reached."""
    triage = MockHandoffAgent(name="triage", handoff_to="worker")
    worker = MockHandoffAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[triage, worker], termination_condition=lambda conv: False)
        .with_start_agent(triage)
        .with_autonomous_mode(agents=[worker], turn_limits={resolve_agent_id(worker): 2})
        .build()
    )

    events = await _drain(workflow.run("Start", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]
    assert requests and len(requests) == 1, "Turn limit should force a user input request"
    assert requests[0].source_executor_id == worker.name


def test_build_fails_without_start_agent():
    """Verify that build() raises ValueError when with_start_agent() was not called."""
    triage = MockHandoffAgent(name="triage")
    specialist = MockHandoffAgent(name="specialist")

    with pytest.raises(ValueError, match=r"Must call with_start_agent\(...\) before building the workflow."):
        HandoffBuilder(participants=[triage, specialist]).build()


def test_build_fails_without_participants():
    """Verify that build() raises ValueError when no participants are provided."""
    with pytest.raises(ValueError):
        HandoffBuilder(participants=[]).build()


async def test_handoff_async_termination_condition() -> None:
    """Test that async termination conditions work correctly."""
    termination_call_count = 0

    async def async_termination(conv: list[Message]) -> bool:
        nonlocal termination_call_count
        termination_call_count += 1
        user_count = sum(1 for msg in conv if msg.role == "user")
        return user_count >= 2

    coordinator = MockHandoffAgent(name="coordinator", handoff_to="worker")
    worker = MockHandoffAgent(name="worker")

    workflow = (
        HandoffBuilder(participants=[coordinator, worker], termination_condition=async_termination)
        .with_start_agent(coordinator)
        .build()
    )

    events = await _drain(workflow.run("First user message", stream=True))
    requests = [ev for ev in events if ev.type == "request_info"]
    assert requests

    events = await _drain(
        workflow.run(
            stream=True, responses={requests[-1].request_id: [Message(role="user", text="Second user message")]}
        )
    )
    outputs = [ev for ev in events if ev.type == "output"]
    assert len(outputs) == 1

    final_conversation = outputs[0].data
    assert isinstance(final_conversation, list)
    final_conv_list = cast(list[Message], final_conversation)
    user_messages = [msg for msg in final_conv_list if msg.role == "user"]
    assert len(user_messages) == 2
    assert termination_call_count > 0


async def test_handoff_terminates_without_request_info_when_latest_response_meets_condition() -> None:
    """Termination triggered by the latest assistant response should not emit request_info."""

    class FinalizingClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
        def __init__(self) -> None:
            ChatMiddlewareLayer.__init__(self)
            FunctionInvocationLayer.__init__(self)
            BaseChatClient.__init__(self)

        def _inner_get_response(
            self,
            *,
            messages: Sequence[Message],
            stream: bool,
            options: Mapping[str, Any],
            **kwargs: Any,
        ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
            del messages, options, kwargs
            contents = [Content.from_text(text="Replacement request submitted. Case complete.")]

            if stream:

                async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                    yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

                return ResponseStream(_stream(), finalizer=lambda updates: ChatResponse.from_updates(updates))

            async def _get() -> ChatResponse:
                return ChatResponse(messages=[Message(role="assistant", contents=contents)], response_id="finalizing")

            return _get()

    agent = Agent(id="order_agent", name="order_agent", client=FinalizingClient())
    workflow = (
        HandoffBuilder(
            participants=[agent],
            termination_condition=lambda conv: any(
                message.role == "assistant" and "case complete." in (message.text or "").lower() for message in conv
            ),
        )
        .with_start_agent(agent)
        .build()
    )

    events = await _drain(workflow.run("ship replacement", stream=True))

    requests = [event for event in events if event.type == "request_info"]
    assert not requests

    outputs = [event for event in events if event.type == "output"]
    assert outputs
    conversation_outputs = [event for event in outputs if isinstance(event.data, list)]
    assert len(conversation_outputs) == 1


async def test_tool_choice_preserved_from_agent_config():
    """Verify that agent-level tool_choice configuration is preserved and not overridden."""
    # Create a mock chat client that records the tool_choice used
    recorded_tool_choices: list[Any] = []

    async def mock_get_response(messages: Any, options: dict[str, Any] | None = None, **kwargs: Any) -> ChatResponse:
        if options:
            recorded_tool_choices.append(options.get("tool_choice"))
        return ChatResponse(
            messages=[Message(role="assistant", text="Response")],
            response_id="test_response",
        )

    mock_client = MagicMock()
    mock_client.get_response = AsyncMock(side_effect=mock_get_response)

    # Create agent with specific tool_choice configuration via default_options
    agent = Agent(
        client=mock_client,
        name="test_agent",
        default_options={"tool_choice": {"mode": "required"}},  # type: ignore
    )

    # Run the agent
    await agent.run("Test message")

    # Verify tool_choice was preserved
    assert len(recorded_tool_choices) > 0, "No tool_choice recorded"
    last_tool_choice = recorded_tool_choices[-1]
    assert last_tool_choice is not None, "tool_choice should not be None"
    assert last_tool_choice == {"mode": "required"}, f"Expected 'required', got {last_tool_choice}"


async def test_context_provider_preserved_during_handoff():
    """Verify that context_providers are preserved when cloning agents in handoff workflows."""
    # Track whether context provider methods were called
    provider_calls: list[str] = []

    class TestContextProvider(BaseContextProvider):
        """A test context provider that tracks its invocations."""

        def __init__(self) -> None:
            super().__init__("test")

        async def before_run(self, **kwargs: Any) -> None:
            provider_calls.append("before_run")

    # Create context provider
    context_provider = TestContextProvider()

    # Create a mock chat client
    mock_client = MockChatClient(name="test_agent")

    # Create agent with context provider using proper constructor
    agent = Agent(
        client=mock_client,
        name="test_agent",
        id="test_agent",
        context_providers=[context_provider],
    )

    # Verify the original agent has the context provider
    assert context_provider in agent.context_providers, "Original agent should have context provider"

    # Build handoff workflow - this should clone the agent and preserve context_providers
    workflow = HandoffBuilder(participants=[agent]).with_start_agent(agent).build()

    # Run workflow with a simple message to trigger context provider
    await _drain(workflow.run("Test message", stream=True))

    # Verify context provider was invoked during the workflow execution
    assert len(provider_calls) > 0, (
        "Context provider should be called during workflow execution, "
        "indicating it was properly preserved during agent cloning"
    )


def test_handoff_builder_accepts_all_instances_in_add_handoff():
    """Test that add_handoff accepts all instances when using participants."""
    triage = MockHandoffAgent(name="triage", handoff_to="specialist_a")
    specialist_a = MockHandoffAgent(name="specialist_a")
    specialist_b = MockHandoffAgent(name="specialist_b")

    # This should work - all instances with participants
    builder = (
        HandoffBuilder(participants=[triage, specialist_a, specialist_b])
        .with_start_agent(triage)
        .add_handoff(triage, [specialist_a, specialist_b])
    )

    workflow = builder.build()
    assert "triage" in workflow.executors
    assert "specialist_a" in workflow.executors
    assert "specialist_b" in workflow.executors


async def test_auto_handoff_middleware_intercepts_handoff_tool_call() -> None:
    """Middleware should short-circuit matching handoff tool calls with a synthetic result."""
    target_id = "specialist"
    middleware = _AutoHandoffMiddleware([HandoffConfiguration(target=target_id)])

    @tool(name=get_handoff_tool_name(target_id), approval_mode="never_require")
    def handoff_tool() -> str:
        return "unreachable"

    context = FunctionInvocationContext(function=handoff_tool, arguments={})
    call_next = AsyncMock()

    with pytest.raises(MiddlewareTermination) as exc_info:
        await middleware.process(context, call_next)

    call_next.assert_not_awaited()
    expected_result = FunctionTool.parse_result({HANDOFF_FUNCTION_RESULT_KEY: target_id})
    assert context.result == expected_result
    assert exc_info.value.result == expected_result


async def test_auto_handoff_middleware_calls_next_for_non_handoff_tool() -> None:
    """Middleware should pass through when the function name is not a configured handoff tool."""
    middleware = _AutoHandoffMiddleware([HandoffConfiguration(target="specialist")])

    @tool(name="regular_tool", approval_mode="never_require")
    def regular_tool() -> str:
        return "ok"

    context = FunctionInvocationContext(function=regular_tool, arguments={})
    call_next = AsyncMock()

    await middleware.process(context, call_next)

    call_next.assert_awaited_once()
    assert context.result is None
