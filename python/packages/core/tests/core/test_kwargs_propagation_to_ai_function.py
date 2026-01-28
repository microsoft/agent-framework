# Copyright (c) Microsoft. All rights reserved.

"""Tests for kwargs propagation from get_response() to @tool functions."""

from typing import Any

from agent_framework import (
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    tool,
)
from agent_framework._tools import _handle_function_calls_response, _handle_function_calls_streaming_response


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

        # Create a mock client
        mock_client = type("MockClient", (), {})()

        call_count = [0]

        async def mock_get_response(self, messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: return a function call
                return ChatResponse(
                    messages=[
                        ChatMessage(
                            role="assistant",
                            contents=[
                                Content.from_function_call(
                                    call_id="call_1", name="capture_kwargs_tool", arguments='{"x": 42}'
                                )
                            ],
                        )
                    ]
                )
            # Second call: return final response
            return ChatResponse(messages=[ChatMessage(role="assistant", text="Done!")])

        # Wrap the function with function invocation decorator
        wrapped = _handle_function_calls_response(mock_get_response)

        # Call with custom kwargs that should propagate to the tool
        # Note: tools are passed in options dict, custom kwargs are passed separately
        result = await wrapped(
            mock_client,
            messages=[],
            options={"tools": [capture_kwargs_tool]},
            user_id="user-123",
            session_token="secret-token",
            custom_data={"key": "value"},
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
            # This should not receive any extra kwargs
            return f"result: x={x}"

        mock_client = type("MockClient", (), {})()

        call_count = [0]

        async def mock_get_response(self, messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ChatResponse(
                    messages=[
                        ChatMessage(
                            role="assistant",
                            contents=[
                                Content.from_function_call(call_id="call_1", name="simple_tool", arguments='{"x": 99}')
                            ],
                        )
                    ]
                )
            return ChatResponse(messages=[ChatMessage(role="assistant", text="Completed!")])

        wrapped = _handle_function_calls_response(mock_get_response)

        # Call with kwargs - the tool should work but not receive them
        result = await wrapped(
            mock_client,
            messages=[],
            options={"tools": [simple_tool]},
            user_id="user-123",  # This kwarg should be ignored by the tool
        )

        # Verify the tool was called successfully (no error from extra kwargs)
        assert result.messages[-1].text == "Completed!"

    async def test_kwargs_isolated_between_function_calls(self) -> None:
        """Test that kwargs don't leak between different function call invocations."""
        invocation_kwargs: list[dict[str, Any]] = []

        @tool(approval_mode="never_require")
        def tracking_tool(name: str, **kwargs: Any) -> str:
            """A tool that tracks kwargs from each invocation."""
            invocation_kwargs.append(dict(kwargs))
            return f"called with {name}"

        mock_client = type("MockClient", (), {})()

        call_count = [0]

        async def mock_get_response(self, messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Two function calls in one response
                return ChatResponse(
                    messages=[
                        ChatMessage(
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
                )
            return ChatResponse(messages=[ChatMessage(role="assistant", text="All done!")])

        wrapped = _handle_function_calls_response(mock_get_response)

        # Call with kwargs
        result = await wrapped(
            mock_client,
            messages=[],
            options={"tools": [tracking_tool]},
            request_id="req-001",
            trace_context={"trace_id": "abc"},
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

        mock_client = type("MockClient", (), {})()

        call_count = [0]

        async def mock_get_streaming_response(self, messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: return function call update
                yield ChatResponseUpdate(
                    role="assistant",
                    contents=[
                        Content.from_function_call(
                            call_id="stream_call_1",
                            name="streaming_capture_tool",
                            arguments='{"value": "streaming-test"}',
                        )
                    ],
                    is_finished=True,
                )
            else:
                # Second call: return final response
                yield ChatResponseUpdate(
                    text=Content.from_text(text="Stream complete!"), role="assistant", is_finished=True
                )

        wrapped = _handle_function_calls_streaming_response(mock_get_streaming_response)

        # Collect streaming updates
        updates: list[ChatResponseUpdate] = []
        async for update in wrapped(
            mock_client,
            messages=[],
            options={"tools": [streaming_capture_tool]},
            streaming_session="session-xyz",
            correlation_id="corr-123",
        ):
            updates.append(update)

        # Verify kwargs were captured by the tool
        assert "streaming_session" in captured_kwargs, f"Expected 'streaming_session' in {captured_kwargs}"
        assert captured_kwargs["streaming_session"] == "session-xyz"
        assert captured_kwargs["correlation_id"] == "corr-123"
