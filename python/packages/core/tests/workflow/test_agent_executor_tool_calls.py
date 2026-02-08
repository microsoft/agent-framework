# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentExecutor handling of tool calls and results in streaming mode."""

from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any

from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentExecutorResponse,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatAgent,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    ResponseStream,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    executor,
    tool,
)
from agent_framework._clients import BaseChatClient
from agent_framework._tools import FunctionInvocationLayer


class _ToolCallingAgent(BaseAgent):
    """Mock agent that simulates tool calls and results in streaming mode."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def run(
        self,
        messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
        *,
        stream: bool = False,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
        if stream:
            return ResponseStream(self._run_stream_impl(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[ChatMessage("assistant", ["done"])])

        return _run()

    async def _run_stream_impl(self) -> AsyncIterable[AgentResponseUpdate]:
        """Simulate streaming with tool calls and results."""
        # First update: some text
        yield AgentResponseUpdate(
            contents=[Content.from_text(text="Let me search for that...")],
            role="assistant",
        )

        # Second update: tool call (no text!)
        yield AgentResponseUpdate(
            contents=[
                Content.from_function_call(
                    call_id="call_123",
                    name="search",
                    arguments={"query": "weather"},
                )
            ],
            role="assistant",
        )

        # Third update: tool result (no text!)
        yield AgentResponseUpdate(
            contents=[
                Content.from_function_result(
                    call_id="call_123",
                    result={"temperature": 72, "condition": "sunny"},
                )
            ],
            role="tool",
        )

        # Fourth update: final text response
        yield AgentResponseUpdate(
            contents=[Content.from_text(text="The weather is sunny, 72°F.")],
            role="assistant",
        )


async def test_agent_executor_emits_tool_calls_in_streaming_mode() -> None:
    """Test that AgentExecutor emits updates containing FunctionCallContent and FunctionResultContent."""
    # Arrange
    agent = _ToolCallingAgent(id="tool_agent", name="ToolAgent")
    agent_exec = AgentExecutor(agent, id="tool_exec")

    workflow = WorkflowBuilder(start_executor=agent_exec).build()

    # Act: run in streaming mode
    events: list[WorkflowEvent[AgentResponseUpdate]] = []
    async for event in workflow.run("What's the weather?", stream=True):
        if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            events.append(event)

    # Assert: we should receive 4 events (text, function call, function result, text)
    assert len(events) == 4, f"Expected 4 events, got {len(events)}"

    # First event: text update
    assert events[0].data is not None
    assert events[0].data.contents[0].type == "text"
    assert "Let me search" in events[0].data.contents[0].text

    # Second event: function call
    assert events[1].data is not None
    assert events[1].data.contents[0].type == "function_call"
    func_call = events[1].data.contents[0]
    assert func_call.call_id == "call_123"
    assert func_call.name == "search"

    # Third event: function result
    assert events[2].data is not None
    assert events[2].data.contents[0].type == "function_result"
    func_result = events[2].data.contents[0]
    assert func_result.call_id == "call_123"

    # Fourth event: final text
    assert events[3].data is not None
    assert events[3].data.contents[0].type == "text"
    assert "sunny" in events[3].data.contents[0].text


@tool(approval_mode="always_require")
def mock_tool_requiring_approval(query: str) -> str:
    """Mock tool that requires approval before execution."""
    return f"Executed tool with query: {query}"


class MockChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Simple implementation of a chat client with function invocation support.

    This mock uses the proper layer hierarchy:
    - FunctionInvocationLayer.get_response intercepts calls and handles tool invocation
    - BaseChatClient.get_response prepares messages and calls _inner_get_response
    - _inner_get_response provides the actual mock responses
    """

    def __init__(self, parallel_request: bool = False) -> None:
        FunctionInvocationLayer.__init__(self)
        BaseChatClient.__init__(self)
        self._iteration: int = 0
        self._parallel_request: bool = parallel_request

    def _inner_get_response(
        self,
        *,
        messages: Sequence[ChatMessage],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Provide mock responses for the function invocation layer."""
        if stream:
            return self._build_response_stream(self._stream_response())

        async def _get_response() -> ChatResponse:
            return self._create_response()

        return _get_response()

    def _create_response(self) -> ChatResponse:
        """Create a mock response based on iteration count."""
        if self._iteration == 0:
            if self._parallel_request:
                response = ChatResponse(
                    messages=ChatMessage(
                        "assistant",
                        [
                            Content.from_function_call(
                                call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                            ),
                            Content.from_function_call(
                                call_id="2", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                            ),
                        ],
                    )
                )
            else:
                response = ChatResponse(
                    messages=ChatMessage(
                        "assistant",
                        [
                            Content.from_function_call(
                                call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                            )
                        ],
                    )
                )
        else:
            response = ChatResponse(messages=ChatMessage("assistant", ["Tool executed successfully."]))

        self._iteration += 1
        return response

    async def _stream_response(self) -> AsyncIterable[ChatResponseUpdate]:
        """Generate mock streaming responses."""
        if self._iteration == 0:
            if self._parallel_request:
                yield ChatResponseUpdate(
                    contents=[
                        Content.from_function_call(
                            call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                        ),
                        Content.from_function_call(
                            call_id="2", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                        ),
                    ],
                    role="assistant",
                )
            else:
                yield ChatResponseUpdate(
                    contents=[
                        Content.from_function_call(
                            call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                        )
                    ],
                    role="assistant",
                )
        else:
            yield ChatResponseUpdate(contents=[Content.from_text(text="Tool executed ")], role="assistant")
            yield ChatResponseUpdate(contents=[Content.from_text(text="successfully.")], role="assistant")

        self._iteration += 1


@executor(id="test_executor")
async def test_executor(agent_executor_response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output(agent_executor_response.agent_response.text)


async def test_agent_executor_tool_call_with_approval() -> None:
    """Test that AgentExecutor handles tool calls requiring approval."""
    # Arrange
    agent = ChatAgent(
        chat_client=MockChatClient(),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )

    workflow = (
        WorkflowBuilder(start_executor=agent, output_executors=[test_executor]).add_edge(agent, test_executor).build()
    )

    # Act
    events = await workflow.run("Invoke tool requiring approval")

    # Assert
    assert len(events.get_request_info_events()) == 1
    approval_request = events.get_request_info_events()[0]
    assert approval_request.data.type == "function_approval_request"
    assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
    assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    events = await workflow.run(
        responses={approval_request.request_id: approval_request.data.to_function_approval_response(True)}
    )

    # Assert
    final_response = events.get_outputs()
    assert len(final_response) == 1
    assert final_response[0] == "Tool executed successfully."


async def test_agent_executor_tool_call_with_approval_streaming() -> None:
    """Test that AgentExecutor handles tool calls requiring approval in streaming mode."""
    # Arrange
    agent = ChatAgent(
        chat_client=MockChatClient(),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )

    workflow = WorkflowBuilder(start_executor=agent).add_edge(agent, test_executor).build()

    # Act
    request_info_events: list[WorkflowEvent] = []
    async for event in workflow.run("Invoke tool requiring approval", stream=True):
        if event.type == "request_info":
            request_info_events.append(event)

    # Assert
    assert len(request_info_events) == 1
    approval_request = request_info_events[0]
    assert approval_request.data.type == "function_approval_request"
    assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
    assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    output: str | None = None
    async for event in workflow.run(
        stream=True, responses={approval_request.request_id: approval_request.data.to_function_approval_response(True)}
    ):
        if event.type == "output":
            output = event.data

    # Assert
    assert output is not None
    assert output == "Tool executed successfully."


async def test_agent_executor_parallel_tool_call_with_approval() -> None:
    """Test that AgentExecutor handles parallel tool calls requiring approval."""
    # Arrange
    agent = ChatAgent(
        chat_client=MockChatClient(parallel_request=True),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )

    workflow = (
        WorkflowBuilder(start_executor=agent, output_executors=[test_executor]).add_edge(agent, test_executor).build()
    )

    # Act
    events = await workflow.run("Invoke tool requiring approval")

    # Assert
    assert len(events.get_request_info_events()) == 2
    for approval_request in events.get_request_info_events():
        assert approval_request.data.type == "function_approval_request"
        assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
        assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    responses = {
        approval_request.request_id: approval_request.data.to_function_approval_response(True)  # type: ignore
        for approval_request in events.get_request_info_events()
    }
    events = await workflow.run(responses=responses)

    # Assert
    final_response = events.get_outputs()
    assert len(final_response) == 1
    assert final_response[0] == "Tool executed successfully."


async def test_agent_executor_parallel_tool_call_with_approval_streaming() -> None:
    """Test that AgentExecutor handles parallel tool calls requiring approval in streaming mode."""
    # Arrange
    agent = ChatAgent(
        chat_client=MockChatClient(parallel_request=True),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )

    workflow = WorkflowBuilder(start_executor=agent).add_edge(agent, test_executor).build()

    # Act
    request_info_events: list[WorkflowEvent] = []
    async for event in workflow.run("Invoke tool requiring approval", stream=True):
        if event.type == "request_info":
            request_info_events.append(event)

    # Assert
    assert len(request_info_events) == 2
    for approval_request in request_info_events:
        assert approval_request.data.type == "function_approval_request"
        assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
        assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    responses = {
        approval_request.request_id: approval_request.data.to_function_approval_response(True)  # type: ignore
        for approval_request in request_info_events
    }

    output: str | None = None
    async for event in workflow.run(stream=True, responses=responses):
        if event.type == "output":
            output = event.data

    # Assert
    assert output is not None
    assert output == "Tool executed successfully."
