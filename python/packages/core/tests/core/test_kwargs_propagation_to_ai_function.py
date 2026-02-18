# Copyright (c) Microsoft. All rights reserved.

"""Tests for kwargs propagation from get_response() to @tool functions."""

from collections.abc import AsyncIterable, Awaitable, MutableSequence, Sequence
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    tool,
)
from agent_framework.observability import ChatTelemetryLayer


class _MockBaseChatClient(BaseChatClient[Any]):
    """Mock chat client for testing function invocation."""

    def __init__(self) -> None:
        super().__init__()
        self.run_responses: list[ChatResponse] = []
        self.streaming_responses: list[list[ChatResponseUpdate]] = []
        self.call_count: int = 0

    def _inner_get_response(
        self,
        *,
        messages: MutableSequence[Message],
        stream: bool,
        options: dict[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:
            return self._get_streaming_response(messages=messages, options=options, **kwargs)

        async def _get() -> ChatResponse:
            return await self._get_non_streaming_response(messages=messages, options=options, **kwargs)

        return _get()

    async def _get_non_streaming_response(
        self,
        *,
        messages: MutableSequence[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        self.call_count += 1
        if self.run_responses:
            return self.run_responses.pop(0)
        return ChatResponse(messages=Message(role="assistant", text="default response"))

    def _get_streaming_response(
        self,
        *,
        messages: MutableSequence[Message],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse]:
        async def _stream() -> AsyncIterable[ChatResponseUpdate]:
            self.call_count += 1
            if self.streaming_responses:
                for update in self.streaming_responses.pop(0):
                    yield update
            else:
                yield ChatResponseUpdate(
                    contents=[Content.from_text("default streaming response")], role="assistant", finish_reason="stop"
                )

        def _finalize(updates: Sequence[ChatResponseUpdate]) -> ChatResponse:
            response_format = options.get("response_format")
            output_format_type = response_format if isinstance(response_format, type) else None
            return ChatResponse.from_updates(updates, output_format_type=output_format_type)

        return ResponseStream(_stream(), finalizer=_finalize)


class FunctionInvokingMockClient(
    ChatMiddlewareLayer[Any],
    FunctionInvocationLayer[Any],
    ChatTelemetryLayer[Any],
    _MockBaseChatClient,
):
    """Mock client with function invocation support."""

    pass


class TestKwargsPropagationToFunctionTool:
    """Test cases for kwargs flowing from get_response() to @tool functions."""

    async def test_kwargs_propagate_to_tool_with_kwargs(self) -> None:
        """Test that kwargs passed to get_response() are available in @tool **kwargs."""
        captured_kwargs: dict[str, Any] = {}

        @tool(approval_mode="never_require")
        def capture_kwargs_tool(x: int, **kwargs: Any) -> str:
            """A tool that captures kwargs for testing."""
            captured_kwargs.update(kwargs)
            return f"result: x={x}"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            # First response: function call
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_1", name="capture_kwargs_tool", arguments='{"x": 42}'
                            )
                        ],
                    )
                ]
            ),
            # Second response: final answer
            ChatResponse(messages=[Message(role="assistant", text="Done!")]),
        ]

        result = await client.get_response(
            messages=[Message(role="user", text="Test")],
            stream=False,
            options={
                "tools": [capture_kwargs_tool],
                "additional_function_arguments": {
                    "user_id": "user-123",
                    "session_token": "secret-token",
                    "custom_data": {"key": "value"},
                },
            },
        )

        # Verify the tool was called and received the kwargs
        assert "user_id" in captured_kwargs, f"Expected 'user_id' in captured kwargs: {captured_kwargs}"
        assert captured_kwargs["user_id"] == "user-123"
        assert "session_token" in captured_kwargs
        assert captured_kwargs["session_token"] == "secret-token"
        assert "custom_data" in captured_kwargs
        assert captured_kwargs["custom_data"] == {"key": "value"}
        # Verify result
        assert result.messages[-1].text == "Done!"

    async def test_kwargs_not_forwarded_to_tool_without_kwargs(self) -> None:
        """Test that kwargs are NOT forwarded to @tool that doesn't accept **kwargs."""

        @tool(approval_mode="never_require")
        def simple_tool(x: int) -> str:
            """A simple tool without **kwargs."""
            return f"result: x={x}"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(call_id="call_1", name="simple_tool", arguments='{"x": 99}')
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", text="Completed!")]),
        ]

        # Call with additional_function_arguments - the tool should work but not receive them
        result = await client.get_response(
            messages=[Message(role="user", text="Test")],
            stream=False,
            options={
                "tools": [simple_tool],
                "additional_function_arguments": {"user_id": "user-123"},
            },
        )

        # Verify the tool was called successfully (no error from extra kwargs)
        assert result.messages[-1].text == "Completed!"

    async def test_kwargs_isolated_between_function_calls(self) -> None:
        """Test that kwargs are consistent across multiple function call invocations."""
        invocation_kwargs: list[dict[str, Any]] = []

        @tool(approval_mode="never_require")
        def tracking_tool(name: str, **kwargs: Any) -> str:
            """A tool that tracks kwargs from each invocation."""
            invocation_kwargs.append(dict(kwargs))
            return f"called with {name}"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            # Two function calls in one response
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_1", name="tracking_tool", arguments='{"name": "first"}'
                            ),
                            Content.from_function_call(
                                call_id="call_2", name="tracking_tool", arguments='{"name": "second"}'
                            ),
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", text="All done!")]),
        ]

        result = await client.get_response(
            messages=[Message(role="user", text="Test")],
            stream=False,
            options={
                "tools": [tracking_tool],
                "additional_function_arguments": {
                    "request_id": "req-001",
                    "trace_context": {"trace_id": "abc"},
                },
            },
        )

        # Both invocations should have received the same kwargs
        assert len(invocation_kwargs) == 2
        for kwargs in invocation_kwargs:
            assert kwargs.get("request_id") == "req-001"
            assert kwargs.get("trace_context") == {"trace_id": "abc"}
        assert result.messages[-1].text == "All done!"

    async def test_streaming_response_kwargs_propagation(self) -> None:
        """Test that kwargs propagate to @tool in streaming mode."""
        captured_kwargs: dict[str, Any] = {}

        @tool(approval_mode="never_require")
        def streaming_capture_tool(value: str, **kwargs: Any) -> str:
            """A tool that captures kwargs during streaming."""
            captured_kwargs.update(kwargs)
            return f"processed: {value}"

        client = FunctionInvokingMockClient()
        client.streaming_responses = [
            # First stream: function call
            [
                ChatResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="stream_call_1",
                            name="streaming_capture_tool",
                            arguments='{"value": "streaming-test"}',
                        )
                    ],
                    finish_reason="stop",
                )
            ],
            # Second stream: final response
            [
                ChatResponseUpdate(
                    contents=[Content.from_text("Stream complete!")], role="assistant", finish_reason="stop"
                )
            ],
        ]

        # Collect streaming updates
        updates: list[ChatResponseUpdate] = []
        stream = client.get_response(
            messages=[Message(role="user", text="Test")],
            stream=True,
            options={
                "tools": [streaming_capture_tool],
                "additional_function_arguments": {
                    "streaming_session": "session-xyz",
                    "correlation_id": "corr-123",
                },
            },
        )
        async for update in stream:
            updates.append(update)

        # Verify kwargs were captured by the tool
        assert "streaming_session" in captured_kwargs, f"Expected 'streaming_session' in {captured_kwargs}"
        assert captured_kwargs["streaming_session"] == "session-xyz"
        assert captured_kwargs["correlation_id"] == "corr-123"
