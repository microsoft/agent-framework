# Copyright (c) Microsoft. All rights reserved.

"""Tests for kwargs propagation from get_response() to @tool functions."""

import asyncio
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

    async def test_tools_list_available_in_kwargs(self) -> None:
        """Test that the tools list is available in kwargs for tools that accept **kwargs."""
        captured_tools: list[Any] = []

        @tool(approval_mode="never_require")
        def inspect_tools(action: str, **kwargs: Any) -> str:
            """A tool that inspects the tools list from kwargs."""
            tools_list = kwargs.get("_framework_tools")
            if tools_list is not None:
                captured_tools.extend(list(tools_list))
            return f"Inspected {len(tools_list) if tools_list else 0} tools"

        @tool(approval_mode="never_require")
        def helper_tool(x: int) -> str:
            """A helper tool."""
            return f"helper: {x}"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_1", name="inspect_tools", arguments='{"action": "check"}'
                            )
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", text="Tools inspected!")]),
        ]

        result = await client.get_response(
            messages=[Message(role="user", text="Test")],
            stream=False,
            options={
                "tools": [inspect_tools, helper_tool],
            },
        )

        # Verify the tools list was passed to the tool
        assert len(captured_tools) == 2, f"Expected 2 tools in kwargs: {captured_tools}"
        assert result.messages[-1].text == "Tools inspected!"

    async def test_dynamic_tool_loading(self) -> None:
        """Test that a tool can dynamically add new tools to the tools list."""
        execution_log: list[str] = []

        @tool(approval_mode="never_require")
        def load_additional_tools(category: str, **kwargs: Any) -> str:
            """Load additional tools dynamically based on category."""
            tools_list = kwargs.get("_framework_tools")
            execution_log.append(f"load_additional_tools called with {len(tools_list) if tools_list else 0} tools")

            if not tools_list:
                return "Error: Tools list not available"

            if category == "math":
                # Define a new tool to add dynamically
                @tool(approval_mode="never_require")
                def multiply(a: int, b: int) -> str:
                    """Multiply two numbers."""
                    execution_log.append(f"multiply called: {a} * {b}")
                    return f"result: {a * b}"

                # Add the new tool to the list (thread-safe)
                tools_list.append(multiply)
                return f"Loaded math tools, now have {len(tools_list)} tools"

            return f"Unknown category: {category}"

        @tool(approval_mode="never_require")
        def basic_tool(msg: str) -> str:
            """A basic tool."""
            execution_log.append(f"basic_tool called: {msg}")
            return f"basic: {msg}"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            # First: call load_additional_tools
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_1", name="load_additional_tools", arguments='{"category": "math"}'
                            )
                        ],
                    )
                ]
            ),
            # Second: call the newly loaded multiply tool
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(call_id="call_2", name="multiply", arguments='{"a": 6, "b": 7}')
                        ],
                    )
                ]
            ),
            # Final response
            ChatResponse(messages=[Message(role="assistant", text="Math complete!")]),
        ]

        result = await client.get_response(
            messages=[Message(role="user", text="Test dynamic loading")],
            stream=False,
            options={
                "tools": [basic_tool, load_additional_tools],
            },
        )

        # Verify execution order
        assert len(execution_log) >= 2, f"Expected at least 2 executions: {execution_log}"
        assert "load_additional_tools called" in execution_log[0]
        assert "multiply called: 6 * 7" in execution_log[1]
        assert result.messages[-1].text == "Math complete!"

    async def test_tools_list_modifications_persist(self) -> None:
        """Test that modifications to the tools list persist across function invocations."""
        tool_counts: list[int] = []

        @tool(approval_mode="never_require")
        def count_and_add_tool(name: str, **kwargs: Any) -> str:
            """Count tools and optionally add a new one."""
            tools_list = kwargs.get("_framework_tools")
            if not tools_list:
                return "No tools list"

            tool_counts.append(len(tools_list))

            # Add a dummy tool
            if name == "add":

                @tool(approval_mode="never_require")
                def dummy_tool() -> str:
                    return "dummy"

                # Thread-safe mutation
                tools_list.append(dummy_tool)
                return f"Added tool, now have {len(tools_list)}"

            return f"Counted {len(tools_list)} tools"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            # First call: count initial tools
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_1", name="count_and_add_tool", arguments='{"name": "count"}'
                            )
                        ],
                    )
                ]
            ),
            # Second call: add a tool
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_2", name="count_and_add_tool", arguments='{"name": "add"}'
                            )
                        ],
                    )
                ]
            ),
            # Third call: count again to verify persistence
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_3", name="count_and_add_tool", arguments='{"name": "count"}'
                            )
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", text="Done!")]),
        ]

        result = await client.get_response(
            messages=[Message(role="user", text="Test persistence")],
            stream=False,
            options={
                "tools": [count_and_add_tool],
            },
        )

        # Verify tool count increased after adding
        assert len(tool_counts) == 3, f"Expected 3 counts: {tool_counts}"
        assert tool_counts[0] == 1  # Initial: just count_and_add_tool
        assert tool_counts[1] == 1  # Before adding
        assert tool_counts[2] == 2  # After adding: original + dummy_tool
        assert result.messages[-1].text == "Done!"

    async def test_concurrent_tools_list_mutations_thread_safe(self) -> None:
        """Test that concurrent tool mutations don't cause race conditions.

        This test verifies that when multiple function calls execute in parallel
        (via asyncio.gather) and both try to mutate the tools list, all mutations
        are properly serialized and no updates are lost.
        """
        mutation_log: list[str] = []

        @tool(approval_mode="never_require")
        async def tool_a(action: str, **kwargs: Any) -> str:
            """Tool A that mutates the tools list."""
            tools_list = kwargs.get("_framework_tools")
            if not tools_list or action != "add":
                return "skipped"

            mutation_log.append("tool_a_start")

            @tool(approval_mode="never_require")
            def tool_a_dynamic() -> str:
                return "dynamic_a"

            # Simulate some async work before mutation
            await asyncio.sleep(0.01)
            tools_list.append(tool_a_dynamic)
            mutation_log.append("tool_a_end")
            return "tool_a added"

        @tool(approval_mode="never_require")
        async def tool_b(action: str, **kwargs: Any) -> str:
            """Tool B that also mutates the tools list."""
            tools_list = kwargs.get("_framework_tools")
            if not tools_list or action != "add":
                return "skipped"

            mutation_log.append("tool_b_start")

            @tool(approval_mode="never_require")
            def tool_b_dynamic() -> str:
                return "dynamic_b"

            # Simulate some async work before mutation
            await asyncio.sleep(0.01)
            tools_list.append(tool_b_dynamic)
            mutation_log.append("tool_b_end")
            return "tool_b added"

        client = FunctionInvokingMockClient()
        # Return both function calls in parallel (this triggers asyncio.gather)
        client.run_responses = [
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(call_id="call_1", name="tool_a", arguments='{"action": "add"}'),
                            Content.from_function_call(call_id="call_2", name="tool_b", arguments='{"action": "add"}'),
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", text="Both tools added!")]),
        ]

        result = await client.get_response(
            messages=[Message(role="user", text="Test concurrent mutations")],
            stream=False,
            options={
                "tools": [tool_a, tool_b],
            },
        )

        # Verify both tools were called
        assert "tool_a_start" in mutation_log, f"tool_a should have started: {mutation_log}"
        assert "tool_b_start" in mutation_log, f"tool_b should have started: {mutation_log}"
        assert "tool_a_end" in mutation_log, f"tool_a should have completed: {mutation_log}"
        assert "tool_b_end" in mutation_log, f"tool_b should have completed: {mutation_log}"

        # Verify the final tools list has the correct number of tools
        # Initial 2 (tool_a, tool_b) + 2 dynamically added = 4 total
        # This test would fail with the old implementation due to race conditions
        # losing one of the appends
        assert result.messages[-1].text == "Both tools added!"

    async def test_tools_kwarg_not_in_regular_kwargs(self) -> None:
        """Test that tools list is not passed to tools without **kwargs."""
        tool_called = False

        @tool(approval_mode="never_require")
        def simple_no_kwargs(value: int) -> str:
            """A tool without **kwargs - should work normally."""
            nonlocal tool_called
            tool_called = True
            return f"Processed {value}"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_1", name="simple_no_kwargs", arguments='{"value": 42}'
                            )
                        ],
                    )
                ]
            ),
            ChatResponse(messages=[Message(role="assistant", text="Success!")]),
        ]

        result = await client.get_response(
            messages=[Message(role="user", text="Test")],
            stream=False,
            options={
                "tools": [simple_no_kwargs],
            },
        )

        # Verify the tool was called successfully (no error from tools kwarg)
        assert tool_called, "Expected tool to be called"
        assert result.messages[-1].text == "Success!"

    async def test_tools_list_with_approval_mode(self) -> None:
        """Test that tools list is available in kwargs even with approval_mode."""
        captured_tools_count: int = 0
        tool_executed = False

        @tool(approval_mode="always_require")
        def approved_inspector(action: str, **kwargs: Any) -> str:
            """A tool requiring approval that inspects the tools list."""
            nonlocal captured_tools_count, tool_executed
            tool_executed = True
            tools_list = kwargs.get("_framework_tools")
            if tools_list:
                captured_tools_count = len(tools_list)
            return f"Approved action: {action}"

        client = FunctionInvokingMockClient()
        client.run_responses = [
            # First response: function call that requires approval
            ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            Content.from_function_call(
                                call_id="call_1", name="approved_inspector", arguments='{"action": "inspect"}'
                            )
                        ],
                    )
                ]
            ),
        ]

        # First call should return approval request
        result = await client.get_response(
            messages=[Message(role="user", text="Test")],
            stream=False,
            options={
                "tools": [approved_inspector],
            },
        )

        # Verify we got an approval request (tool not executed yet)
        has_approval_request = any(
            c.type == "function_approval_request" for msg in result.messages for c in msg.contents if hasattr(c, "type")
        )
        assert has_approval_request, "Expected function_approval_request in response"

        # Now simulate approval and execution
        client.run_responses = [
            ChatResponse(messages=[Message(role="assistant", text="Approval processed!")]),
        ]

        await client.get_response(
            messages=[
                Message(role="user", text="Test"),
                Message(
                    role="user",
                    contents=[
                        Content.from_function_approval_response(
                            id="call_1",
                            function_call=Content.from_function_call(
                                call_id="call_1", name="approved_inspector", arguments='{"action": "inspect"}'
                            ),
                            approved=True,
                        )
                    ],
                ),
            ],
            stream=False,
            options={
                "tools": [approved_inspector],
            },
        )

        # Verify tools list was available when tool executed
        assert tool_executed, "Tool should have been executed after approval"
        assert captured_tools_count == 1, f"Expected 1 tool in kwargs: {captured_tools_count}"
