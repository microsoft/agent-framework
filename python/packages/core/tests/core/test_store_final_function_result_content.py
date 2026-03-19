# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable, Sequence
from typing import Any
from unittest.mock import patch

from agent_framework import (
    Agent,
    AgentResponse,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
)
from agent_framework._agents import RawAgent


def _make_client(
    responses: list[ChatResponse] | None = None,
    streaming_responses: list[list[ChatResponseUpdate]] | None = None,
) -> Any:
    """Create a mock chat client that supports function invocation."""

    class _Client(FunctionInvocationLayer):
        def __init__(self) -> None:
            self.call_count = 0
            self.run_responses: list[ChatResponse] = list(responses or [])
            self.streaming_responses: list[list[ChatResponseUpdate]] = list(streaming_responses or [])

        def get_response(
            self,
            messages: Any,
            *,
            stream: bool = False,
            options: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> Any:
            options = options or {}
            if stream:
                return self._stream(options)
            return self._non_stream()

        async def _non_stream(self) -> ChatResponse:
            self.call_count += 1
            if self.run_responses:
                return self.run_responses.pop(0)
            return ChatResponse(messages=Message(role="assistant", text="default"))

        def _stream(self, options: dict[str, Any]) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
            async def _gen() -> AsyncIterable[ChatResponseUpdate]:
                self.call_count += 1
                if self.streaming_responses:
                    for update in self.streaming_responses.pop(0):
                        yield update
                else:
                    yield ChatResponseUpdate(contents=[Content.from_text("default")], role="assistant")

            def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
                response_format = options.get("response_format")
                output_format_type = response_format if isinstance(response_format, type) else None
                return ChatResponse.from_updates(updates, output_format_type=output_format_type)

            return ResponseStream(_gen(), finalizer=_finalize)

    return _Client()


def _get_stored_messages(agent: Agent, session: Any) -> list[Message]:
    """Retrieve messages stored by the InMemoryHistoryProvider."""
    for provider in agent.context_providers:
        if isinstance(provider, InMemoryHistoryProvider):
            state = session.state.get(provider.source_id, {})
            return list(state.get("messages", []))
    return []


# -- Unit tests for the static filter method --


def test_filter_returns_original_when_store_is_true() -> None:
    messages = [
        Message("assistant", [Content.from_function_call("c1", "get_weather")]),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
    ]
    result = RawAgent._filter_final_function_result_content(messages, store_final_function_result_content=True)
    assert result is messages


def test_filter_returns_original_when_empty() -> None:
    result = RawAgent._filter_final_function_result_content([], store_final_function_result_content=False)
    assert result == []


def test_filter_removes_trailing_function_result_messages() -> None:
    messages = [
        Message("assistant", [Content.from_function_call("c1", "get_weather")]),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
    ]
    result = RawAgent._filter_final_function_result_content(messages, store_final_function_result_content=False)
    assert len(result) == 1
    assert result[0].role == "assistant"


def test_filter_removes_multiple_trailing_function_result_messages() -> None:
    messages = [
        Message(
            "assistant",
            [
                Content.from_function_call("c1", "get_weather"),
                Content.from_function_call("c2", "get_news"),
            ],
        ),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
        Message("tool", [Content.from_function_result("c2", result="Headlines")]),
    ]
    result = RawAgent._filter_final_function_result_content(messages, store_final_function_result_content=False)
    assert len(result) == 1
    assert result[0].role == "assistant"


def test_filter_keeps_mixed_content_message() -> None:
    messages = [
        Message("tool", [Content.from_text("Some note"), Content.from_function_result("c1", result="Sunny")]),
    ]
    result = RawAgent._filter_final_function_result_content(messages, store_final_function_result_content=False)
    assert len(result) == 1
    assert len(result[0].contents) == 2


def test_filter_no_filtering_when_last_is_not_function_result() -> None:
    messages = [
        Message("assistant", [Content.from_text("The weather is sunny.")]),
    ]
    result = RawAgent._filter_final_function_result_content(messages, store_final_function_result_content=False)
    assert len(result) == 1
    assert result[0].contents[0].type == "text"


def test_filter_stops_at_non_tool_message() -> None:
    messages = [
        Message("assistant", [Content.from_text("Here's the result:")]),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
    ]
    result = RawAgent._filter_final_function_result_content(messages, store_final_function_result_content=False)
    assert len(result) == 1
    assert result[0].role == "assistant"
    assert result[0].contents[0].text == "Here's the result:"


# -- Integration tests with the Agent class --


async def test_run_filters_final_function_result_when_default() -> None:
    """Default behavior (store_final_function_result_content not set) should filter."""
    response_messages = [
        Message("assistant", [Content.from_function_call("c1", "get_weather")]),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
    ]
    client = _make_client(responses=[ChatResponse(messages=response_messages)])

    with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", 2):
        agent = Agent(client=client, name="test-agent")
        session = agent.create_session()
        await agent.run(
            [Message("user", [Content.from_text("What's the weather?")])],
            session=session,
        )

    stored = _get_stored_messages(agent, session)
    assert len(stored) == 2  # user + assistant (tool message filtered)
    assert stored[0].role == "user"
    assert stored[1].role == "assistant"
    assert stored[1].contents[0].type == "function_call"


async def test_run_filters_final_function_result_when_false() -> None:
    """Explicit False should filter trailing function result content."""
    response_messages = [
        Message("assistant", [Content.from_function_call("c1", "get_weather")]),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
    ]
    client = _make_client(responses=[ChatResponse(messages=response_messages)])

    with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", 2):
        agent = Agent(client=client, name="test-agent")
        session = agent.create_session()
        await agent.run(
            [Message("user", [Content.from_text("What's the weather?")])],
            session=session,
            options={"store_final_function_result_content": False},
        )

    stored = _get_stored_messages(agent, session)
    assert len(stored) == 2  # user + assistant (tool message filtered)
    assert stored[1].role == "assistant"
    assert stored[1].contents[0].type == "function_call"


async def test_run_keeps_final_function_result_when_true() -> None:
    """When True, trailing function result content should be kept in history."""
    response_messages = [
        Message("assistant", [Content.from_function_call("c1", "get_weather")]),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
    ]
    client = _make_client(responses=[ChatResponse(messages=response_messages)])

    with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", 2):
        agent = Agent(client=client, name="test-agent")
        session = agent.create_session()
        await agent.run(
            [Message("user", [Content.from_text("What's the weather?")])],
            session=session,
            options={"store_final_function_result_content": True},
        )

    stored = _get_stored_messages(agent, session)
    assert len(stored) == 3  # user + assistant + tool
    assert stored[2].role == "tool"
    assert stored[2].contents[0].type == "function_result"


async def test_run_no_filtering_when_last_is_text() -> None:
    """No filtering when the last message is not a function result."""
    response_messages = [
        Message("assistant", [Content.from_text("The weather is sunny.")]),
    ]
    client = _make_client(responses=[ChatResponse(messages=response_messages)])

    with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", 2):
        agent = Agent(client=client, name="test-agent")
        session = agent.create_session()
        await agent.run(
            [Message("user", [Content.from_text("What's the weather?")])],
            session=session,
        )

    stored = _get_stored_messages(agent, session)
    assert len(stored) == 2  # user + assistant text
    assert stored[1].text == "The weather is sunny."


async def test_run_returns_unfiltered_response_to_caller() -> None:
    """AgentResponse returned to the caller should contain the full unfiltered response."""
    response_messages = [
        Message("assistant", [Content.from_function_call("c1", "get_weather")]),
        Message("tool", [Content.from_function_result("c1", result="Sunny")]),
    ]
    client = _make_client(responses=[ChatResponse(messages=response_messages)])

    with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", 2):
        agent = Agent(client=client, name="test-agent")
        session = agent.create_session()
        result: AgentResponse = await agent.run(
            [Message("user", [Content.from_text("What's the weather?")])],
            session=session,
            options={"store_final_function_result_content": False},
        )

    # The returned response should have both messages (unfiltered)
    assert len(result.messages) == 2
    assert result.messages[-1].contents[0].type == "function_result"


async def test_run_streaming_filters_final_function_result_when_default() -> None:
    """Streaming path should also filter trailing function result content by default."""
    streaming_updates = [
        ChatResponseUpdate(
            contents=[Content.from_function_call("c1", "get_weather")],
            role="assistant",
        ),
        ChatResponseUpdate(
            contents=[Content.from_function_result("c1", result="Sunny")],
            role="tool",
        ),
    ]
    client = _make_client(streaming_responses=[streaming_updates])

    with patch("agent_framework._tools.DEFAULT_MAX_ITERATIONS", 2):
        agent = Agent(client=client, name="test-agent")
        session = agent.create_session()
        stream = agent.run(
            [Message("user", [Content.from_text("What's the weather?")])],
            session=session,
            stream=True,
        )
        async for _ in stream:
            pass
        await stream.get_final_response()

    stored = _get_stored_messages(agent, session)
    assert len(stored) == 2  # user + assistant (tool filtered)
    assert stored[0].role == "user"
    assert stored[1].role == "assistant"
    assert stored[1].contents[0].type == "function_call"
