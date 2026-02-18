# Copyright (c) Microsoft. All rights reserved.

"""Regression tests for HandoffBuilder with Responses API style clients.

These tests cover two handoff invariants:
1. A handoff should clear the service conversation pointer so stale response IDs are not reused.
2. A resumed agent should receive full conversation context, including the original user prompt.
"""

from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, cast

from agent_framework import (
    Agent,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Message,
    ResponseStream,
)
from agent_framework._clients import BaseChatClient
from agent_framework._middleware import ChatMiddlewareLayer
from agent_framework._tools import FunctionInvocationLayer
from agent_framework.orchestrations import HandoffBuilder


class ResponsesApiMockClient(ChatMiddlewareLayer[Any], FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Mock client that simulates AzureOpenAIResponsesClient behavior.

    Key differences from the standard MockChatClient in test_handoff.py:
    - Sets conversation_id on responses (like resp_XXX), which causes
      session.service_session_id to be updated after each agent run.
    - Sets STORES_BY_DEFAULT = True to prevent InMemoryHistoryProvider auto-injection,
      matching the real AzureOpenAIResponsesClient behavior.
    - Tracks all received messages and conversation IDs for assertions.
    """

    # Prevent InMemoryHistoryProvider from being auto-injected.
    # The real AzureOpenAIResponsesClient uses server-side storage (via previous_response_id),
    # so InMemoryHistoryProvider is not needed and would hide context-handling regressions.
    STORES_BY_DEFAULT = True

    def __init__(
        self,
        *,
        name: str = "",
        handoff_to: str | None = None,
    ) -> None:
        ChatMiddlewareLayer.__init__(self)
        FunctionInvocationLayer.__init__(self)
        BaseChatClient.__init__(self)
        self._name = name
        self._handoff_to = handoff_to
        self._call_index = 0
        self._response_counter = 0
        # Track messages received on each call for context assertions.
        self.received_messages_per_call: list[list[Message]] = []
        # Track conversation_id received on each call for stale-id assertions.
        self.received_conversation_ids: list[str | None] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        # Record messages and conversation_id for assertions.
        self.received_messages_per_call.append(list(messages))
        self.received_conversation_ids.append(options.get("conversation_id") if options else None)

        self._response_counter += 1
        resp_id = f"resp_{self._name}_{self._response_counter}"

        if stream:
            return self._build_streaming_response(options=dict(options), resp_id=resp_id)

        async def _get() -> ChatResponse:
            contents = self._build_reply_contents()
            reply = Message(role="assistant", contents=contents)
            # Simulate Responses API: set conversation_id to resp_XXX
            return ChatResponse(
                messages=reply,
                response_id=resp_id,
                conversation_id=resp_id,
            )

        return _get()

    def _build_streaming_response(
        self, *, options: dict[str, Any], resp_id: str
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            contents = self._build_reply_contents()
            yield ChatResponseUpdate(contents=contents, role="assistant", finish_reason="stop")

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            response_format = options.get("response_format")
            output_format_type = response_format if isinstance(response_format, type) else None
            resp = ChatResponse.from_updates(updates, output_format_type=output_format_type)
            # Simulate Responses API: set conversation_id
            resp.conversation_id = resp_id
            return resp

        return ResponseStream(_stream(), finalizer=_finalize)

    def _build_reply_contents(self) -> list[Content]:
        contents: list[Content] = []
        if self._handoff_to and self._call_index == 0:
            # Only handoff on first call
            call_id = f"{self._name}-handoff-{self._call_index}"
            self._call_index += 1
            contents.append(
                Content.from_function_call(
                    call_id=call_id,
                    name=f"handoff_to_{self._handoff_to}",
                    arguments={"handoff_to": self._handoff_to},
                )
            )
        text = f"{self._name} reply (call {self._call_index})"
        self._call_index += 1
        contents.append(Content.from_text(text=text))
        return contents


class ResponsesApiMockAgent(Agent):
    """Mock agent that simulates Responses API behavior for handoff testing."""

    def __init__(self, *, name: str, handoff_to: str | None = None) -> None:
        client = ResponsesApiMockClient(name=name, handoff_to=handoff_to)
        super().__init__(client=client, name=name, id=name)


async def test_handoff_clears_stale_conversation_id_before_resume():
    """A resumed agent should not receive a stale conversation_id after handoff."""
    coordinator = ResponsesApiMockAgent(name="coordinator", handoff_to="specialist")
    specialist = ResponsesApiMockAgent(name="specialist", handoff_to="coordinator")

    workflow = (
        HandoffBuilder(
            participants=[coordinator, specialist],
            termination_condition=lambda conv: len(conv) >= 6,
        )
        .with_start_agent(coordinator)
        .add_handoff(coordinator, [specialist])
        .add_handoff(specialist, [coordinator])
        .build()
    )

    # Use non-streaming so conversation_id from ChatResponse propagates to session
    result = await workflow.run("Research topic X", stream=False)

    # Verify handoffs occurred
    handoff_events = [ev for ev in result if ev.type == "handoff_sent"]
    assert len(handoff_events) >= 1, "At least one handoff should have occurred"

    # Get the coordinator executor and its underlying mock client
    coordinator_executor = workflow.executors["coordinator"]
    cloned_agent = coordinator_executor._agent  # type: ignore[attr-defined]
    mock_client = cast(ResponsesApiMockClient, cloned_agent.client)

    # The coordinator should have been called at least twice
    assert len(mock_client.received_conversation_ids) >= 2, (
        f"Coordinator should have been called at least twice, "
        f"but was called {len(mock_client.received_conversation_ids)} times"
    )

    # The 1st call to the coordinator has no conversation_id (first run, no prior response)
    first_conversation_id = mock_client.received_conversation_ids[0]

    # The 2nd call should NOT receive the conversation_id from the 1st response
    # (resp_coordinator_1), because that response contained the handoff function_call.
    # The session's service_session_id should have been cleared after the handoff,
    # so the 2nd call should receive None as conversation_id.
    second_conversation_id = mock_client.received_conversation_ids[1]
    assert second_conversation_id is None, (
        f"Coordinator's 2nd invocation should not receive a stale conversation_id, "
        f"but got '{second_conversation_id}' (1st call had '{first_conversation_id}'). "
        f"The stale response ID would cause 'No tool output found for function call' "
        f"error with the real Responses API."
    )


async def test_handoff_preserves_full_context_for_resumed_agent():
    """A resumed agent should see full history, including the original user prompt."""
    coordinator = ResponsesApiMockAgent(name="coordinator", handoff_to="specialist")
    specialist = ResponsesApiMockAgent(name="specialist", handoff_to="coordinator")

    workflow = (
        HandoffBuilder(
            participants=[coordinator, specialist],
            termination_condition=lambda conv: len(conv) >= 6,
        )
        .with_start_agent(coordinator)
        .add_handoff(coordinator, [specialist])
        .add_handoff(specialist, [coordinator])
        .build()
    )

    # Use non-streaming so conversation_id propagates to session
    result = await workflow.run("Research topic X", stream=False)

    # Verify handoffs happened
    handoff_events = [ev for ev in result if ev.type == "handoff_sent"]
    assert len(handoff_events) >= 1, "At least one handoff should have occurred"

    # Get the coordinator executor and its underlying mock client
    coordinator_executor = workflow.executors["coordinator"]
    cloned_agent = coordinator_executor._agent  # type: ignore[attr-defined]
    mock_client = cast(ResponsesApiMockClient, cloned_agent.client)

    # The coordinator should have been called at least twice:
    # 1st call: initial run with user message "Research topic X"
    # 2nd call: after specialist hands back
    assert len(mock_client.received_messages_per_call) >= 2, (
        f"Coordinator should have been called at least twice, "
        f"but was called {len(mock_client.received_messages_per_call)} times"
    )

    # Check the 2nd call to the coordinator (after handoff back from specialist)
    second_call_messages = mock_client.received_messages_per_call[1]

    # The second call should include the original user message
    # "Research topic X" in its history. But because only _cache is passed
    # (which only has the specialist's broadcast), the original user message is lost.
    #
    # With the Responses API, once service_session_id is set, InMemoryHistoryProvider
    # is NOT auto-injected (see _prepare_run_context line 991). So the agent only
    # sees _cache (partial history), not _full_conversation (complete history).
    #
    # The fix: use _full_conversation instead of _cache when running the agent
    # after a handoff, so the agent sees the complete conversation history.
    user_messages_in_second_call = [
        msg for msg in second_call_messages if msg.role == "user" and msg.text and "Research topic X" in msg.text
    ]
    assert len(user_messages_in_second_call) > 0, (
        f"Coordinator's 2nd invocation should include the original user message "
        f"'Research topic X' but it's missing. The agent only received {len(second_call_messages)} messages: "
        f"{[f'{m.role}: {m.text}' for m in second_call_messages]}. "
        f"This means conversation context is lost after handoff."
    )

