# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentExecutor handling of tool calls and results in streaming mode."""

from collections.abc import AsyncIterable
from typing import Any

from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentExecutorResponse,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentRunUpdateEvent,
    AgentThread,
    BaseAgent,
    ChatAgent,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    FunctionApprovalRequestContent,
    FunctionCallContent,
    FunctionResultContent,
    RequestInfoEvent,
    Role,
    TextContent,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    ai_function,
    executor,
    use_function_invocation,
)


class _ToolCallingAgent(BaseAgent):
    """Mock agent that simulates tool calls and results in streaming mode."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Non-streaming run - not used in this test."""
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="done")])

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Simulate streaming with tool calls and results."""
        # First update: some text
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="Let me search for that...")],
            role=Role.ASSISTANT,
        )

        # Second update: tool call (no text!)
        yield AgentRunResponseUpdate(
            contents=[
                FunctionCallContent(
                    call_id="call_123",
                    name="search",
                    arguments={"query": "weather"},
                )
            ],
            role=Role.ASSISTANT,
        )

        # Third update: tool result (no text!)
        yield AgentRunResponseUpdate(
            contents=[
                FunctionResultContent(
                    call_id="call_123",
                    result={"temperature": 72, "condition": "sunny"},
                )
            ],
            role=Role.TOOL,
        )

        # Fourth update: final text response
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="The weather is sunny, 72°F.")],
            role=Role.ASSISTANT,
        )


async def test_agent_executor_emits_tool_calls_in_streaming_mode() -> None:
    """Test that AgentExecutor emits updates containing FunctionCallContent and FunctionResultContent."""
    # Arrange
    agent = _ToolCallingAgent(id="tool_agent", name="ToolAgent")
    agent_exec = AgentExecutor(agent, id="tool_exec")

    workflow = WorkflowBuilder().set_start_executor(agent_exec).build()

    # Act: run in streaming mode
    events: list[AgentRunUpdateEvent] = []
    async for event in workflow.run_stream("What's the weather?"):
        if isinstance(event, AgentRunUpdateEvent):
            events.append(event)

    # Assert: we should receive 4 events (text, function call, function result, text)
    assert len(events) == 4, f"Expected 4 events, got {len(events)}"

    # First event: text update
    assert events[0].data is not None
    assert isinstance(events[0].data.contents[0], TextContent)
    assert "Let me search" in events[0].data.contents[0].text

    # Second event: function call
    assert events[1].data is not None
    assert isinstance(events[1].data.contents[0], FunctionCallContent)
    func_call = events[1].data.contents[0]
    assert func_call.call_id == "call_123"
    assert func_call.name == "search"

    # Third event: function result
    assert events[2].data is not None
    assert isinstance(events[2].data.contents[0], FunctionResultContent)
    func_result = events[2].data.contents[0]
    assert func_result.call_id == "call_123"

    # Fourth event: final text
    assert events[3].data is not None
    assert isinstance(events[3].data.contents[0], TextContent)
    assert "sunny" in events[3].data.contents[0].text


@ai_function(approval_mode="always_require")
def mock_tool_requiring_approval(query: str) -> str:
    """Mock tool that requires approval before execution."""
    return f"Executed tool with query: {query}"


@use_function_invocation
class MockChatClient:
    """Simple implementation of a chat client."""

    def __init__(self, parallel_request: bool = False) -> None:
        self.additional_properties: dict[str, Any] = {}
        self._iteration: int = 0
        self._parallel_request: bool = parallel_request

    async def get_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **kwargs: Any,
    ) -> ChatResponse:
        if self._iteration == 0:
            if self._parallel_request:
                response = ChatResponse(
                    messages=ChatMessage(
                        role="assistant",
                        contents=[
                            FunctionCallContent(
                                call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                            ),
                            FunctionCallContent(
                                call_id="2", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                            ),
                        ],
                    )
                )
            else:
                response = ChatResponse(
                    messages=ChatMessage(
                        role="assistant",
                        contents=[
                            FunctionCallContent(
                                call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                            )
                        ],
                    )
                )
        else:
            response = ChatResponse(messages=ChatMessage(role="assistant", text="Tool executed successfully."))

        self._iteration += 1
        return response

    async def get_streaming_response(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        if self._iteration == 0:
            if self._parallel_request:
                yield ChatResponseUpdate(
                    contents=[
                        FunctionCallContent(
                            call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                        ),
                        FunctionCallContent(
                            call_id="2", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                        ),
                    ],
                    role="assistant",
                )
            else:
                yield ChatResponseUpdate(
                    contents=[
                        FunctionCallContent(
                            call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                        )
                    ],
                    role="assistant",
                )
        else:
            yield ChatResponseUpdate(text=TextContent(text="Tool executed "), role="assistant")
            yield ChatResponseUpdate(contents=[TextContent(text="successfully.")], role="assistant")

        self._iteration += 1


@executor(id="test_executor")
async def test_executor(agent_executor_response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output(agent_executor_response.agent_run_response.text)


async def test_agent_executor_tool_call_with_approval() -> None:
    """Test that AgentExecutor handles tool calls requiring approval."""
    # Arrange
    agent = ChatAgent(
        chat_client=MockChatClient(),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )

    workflow = WorkflowBuilder().set_start_executor(agent).add_edge(agent, test_executor).build()

    # Act
    events = await workflow.run("Invoke tool requiring approval")

    # Assert
    assert len(events.get_request_info_events()) == 1
    approval_request = events.get_request_info_events()[0]
    assert isinstance(approval_request.data, FunctionApprovalRequestContent)
    assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
    assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    events = await workflow.send_responses({approval_request.request_id: approval_request.data.create_response(True)})

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

    workflow = WorkflowBuilder().set_start_executor(agent).add_edge(agent, test_executor).build()

    # Act
    request_info_events: list[RequestInfoEvent] = []
    async for event in workflow.run_stream("Invoke tool requiring approval"):
        if isinstance(event, RequestInfoEvent):
            request_info_events.append(event)

    # Assert
    assert len(request_info_events) == 1
    approval_request = request_info_events[0]
    assert isinstance(approval_request.data, FunctionApprovalRequestContent)
    assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
    assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    output: str | None = None
    async for event in workflow.send_responses_streaming({
        approval_request.request_id: approval_request.data.create_response(True)
    }):
        if isinstance(event, WorkflowOutputEvent):
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

    workflow = WorkflowBuilder().set_start_executor(agent).add_edge(agent, test_executor).build()

    # Act
    events = await workflow.run("Invoke tool requiring approval")

    # Assert
    assert len(events.get_request_info_events()) == 2
    for approval_request in events.get_request_info_events():
        assert isinstance(approval_request.data, FunctionApprovalRequestContent)
        assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
        assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    responses = {
        approval_request.request_id: approval_request.data.create_response(True)  # type: ignore
        for approval_request in events.get_request_info_events()
    }
    events = await workflow.send_responses(responses)

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

    workflow = WorkflowBuilder().set_start_executor(agent).add_edge(agent, test_executor).build()

    # Act
    request_info_events: list[RequestInfoEvent] = []
    async for event in workflow.run_stream("Invoke tool requiring approval"):
        if isinstance(event, RequestInfoEvent):
            request_info_events.append(event)

    # Assert
    assert len(request_info_events) == 2
    for approval_request in request_info_events:
        assert isinstance(approval_request.data, FunctionApprovalRequestContent)
        assert approval_request.data.function_call.name == "mock_tool_requiring_approval"
        assert approval_request.data.function_call.arguments == '{"query": "test"}'

    # Act
    responses = {
        approval_request.request_id: approval_request.data.create_response(True)  # type: ignore
        for approval_request in request_info_events
    }

    output: str | None = None
    async for event in workflow.send_responses_streaming(responses):
        if isinstance(event, WorkflowOutputEvent):
            output = event.data

    # Assert
    assert output is not None
    assert output == "Tool executed successfully."
