# Copyright (c) Microsoft. All rights reserved.

"""Tests for AgentExecutor handling of tool calls and results in streaming mode."""

from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, Literal, overload

import pytest
from typing_extensions import Never

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorResponse,
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    AgentSession,
    BaseAgent,
    ChatResponse,
    ChatResponseUpdate,
    ComputerSafetyCheck,
    Content,
    FunctionTool,
    InMemoryCheckpointStorage,
    Message,
    ResponseStream,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowExecutor,
    executor,
    tool,
)
from agent_framework._clients import BaseChatClient
from agent_framework._tools import FunctionInvocationLayer
from agent_framework.exceptions import AgentInvalidResponseException


class _ToolCallingAgent(BaseAgent):
    """Mock agent that simulates tool calls and results in streaming mode."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        if stream:
            return ResponseStream(self._run_stream_impl(), finalizer=AgentResponse.from_updates)

        async def _run() -> AgentResponse[Any]:
            return AgentResponse(messages=[Message("assistant", ["done"])])

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
    assert events[0].data.contents[0].text is not None
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
    assert events[3].data.contents[0].text is not None
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
        messages: Sequence[Message],
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
                    messages=Message(
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
                    messages=Message(
                        "assistant",
                        [
                            Content.from_function_call(
                                call_id="1", name="mock_tool_requiring_approval", arguments='{"query": "test"}'
                            )
                        ],
                    )
                )
        else:
            response = ChatResponse(messages=Message("assistant", ["Tool executed successfully."]))

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
async def test_executor(agent_executor_response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
    await ctx.yield_output(agent_executor_response.agent_response.text)


async def test_agent_executor_tool_call_with_approval() -> None:
    """Test that AgentExecutor handles tool calls requiring approval."""
    # Arrange
    agent = Agent(
        client=MockChatClient(),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )

    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

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
    agent = Agent(
        client=MockChatClient(),
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
    agent = Agent(
        client=MockChatClient(parallel_request=True),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )

    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

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


async def test_workflow_cancels_nested_pending_request_without_blocking_sibling() -> None:
    """Cancelling one nested request lets its resolved sibling complete the workflow."""
    agent = Agent(
        client=MockChatClient(parallel_request=True),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )
    child = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()
    nested = WorkflowExecutor(
        child,
        id="nested-workflow",
        propagate_request=True,
        allow_direct_output=True,
    )
    parent = WorkflowBuilder(start_executor=nested).build()

    paused = await parent.run([Message(role="user", contents=["Invoke tool requiring approval"])])
    first_request, second_request = paused.get_request_info_events()

    await parent.cancel_pending_requests([first_request.request_id])
    resumed = await parent.run(
        responses={
            second_request.request_id: second_request.data.to_function_approval_response(True),
        }
    )

    assert resumed.get_outputs() == ["Tool executed successfully."]


async def test_workflow_final_cancellation_resumes_accumulated_sibling_response() -> None:
    """Cancelling the final request resumes an agent that already received its sibling response."""
    agent = Agent(
        client=MockChatClient(parallel_request=True),
        name="ApprovalAgent",
        tools=[mock_tool_requiring_approval],
    )
    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

    paused = await workflow.run("Invoke tool requiring approval")
    first_request, second_request = paused.get_request_info_events()
    partial = await workflow.run(
        responses={
            first_request.request_id: first_request.data.to_function_approval_response(True),
        }
    )

    cancelled = await workflow.cancel_pending_requests([second_request.request_id])

    assert partial.get_outputs() == []
    assert cancelled.get_outputs() == ["Tool executed successfully."]


async def test_workflow_final_cancellation_preserves_runtime_tool_for_approved_sibling() -> None:
    """Cancellation continuation keeps request-scoped tools needed by an accepted sibling."""
    executed_queries: list[str] = []

    def execute_runtime_tool(query: str) -> str:
        executed_queries.append(query)
        return f"Executed runtime tool with query: {query}"

    runtime_tool = FunctionTool(
        name="mock_tool_requiring_approval",
        description="Request-scoped approval tool",
        func=execute_runtime_tool,
        approval_mode="always_require",
    )
    agent = Agent(
        client=MockChatClient(parallel_request=True),
        name="ApprovalAgent",
    )
    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

    paused = await workflow.run("Invoke tool requiring approval", tools=[runtime_tool])
    first_request, second_request = paused.get_request_info_events()
    partial = await workflow.run(
        responses={
            first_request.request_id: first_request.data.to_function_approval_response(True),
        },
        tools=[runtime_tool],
    )

    cancelled = await workflow.cancel_pending_requests(
        [second_request.request_id],
        tools=[runtime_tool],
    )

    assert partial.get_outputs() == []
    assert cancelled.get_outputs() == ["Tool executed successfully."]
    assert executed_queries == ["test"]


async def test_agent_executor_parallel_tool_call_with_approval_streaming() -> None:
    """Test that AgentExecutor handles parallel tool calls requiring approval in streaming mode."""
    # Arrange
    agent = Agent(
        client=MockChatClient(parallel_request=True),
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


# --- Declaration-only tool tests ---

declaration_only_tool = FunctionTool(
    name="client_side_tool",
    func=None,
    description="A client-side tool that the framework cannot execute.",
    input_model={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)


class DeclarationOnlyMockChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """Mock chat client that calls a declaration-only tool on first iteration."""

    def __init__(
        self,
        parallel_request: bool = False,
        mixed_request: bool = False,
        duplicate_host_call_id: bool = False,
    ) -> None:
        FunctionInvocationLayer.__init__(self)
        BaseChatClient.__init__(self)
        self._iteration: int = 0
        self._parallel_request: bool = parallel_request
        self._mixed_request: bool = mixed_request
        self._duplicate_host_call_id: bool = duplicate_host_call_id
        self.received_messages: list[list[Message]] = []

    def _mixed_request_contents(self) -> list[Content]:
        contents = [
            Content.from_function_call(
                call_id="approval-call",
                name="mock_tool_requiring_approval",
                arguments='{"query": "approved"}',
            ),
            Content.from_function_call(
                call_id="host-call",
                name="client_side_tool",
                arguments='{"query": "hosted"}',
            ),
        ]
        if self._duplicate_host_call_id:
            contents.append(
                Content.from_function_call(
                    call_id="host-call",
                    name="client_side_tool",
                    arguments='{"query": "also-hosted"}',
                )
            )
        return contents

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.received_messages.append(list(messages))
        if stream:
            return self._build_response_stream(self._stream_response())

        async def _get_response() -> ChatResponse:
            return self._create_response()

        return _get_response()

    def _create_response(self) -> ChatResponse:
        if self._iteration == 0:
            if self._mixed_request:
                response = ChatResponse(messages=Message("assistant", self._mixed_request_contents()))
            elif self._parallel_request:
                response = ChatResponse(
                    messages=Message(
                        "assistant",
                        [
                            Content.from_function_call(
                                call_id="1", name="client_side_tool", arguments='{"query": "test"}'
                            ),
                            Content.from_function_call(
                                call_id="2", name="client_side_tool", arguments='{"query": "test2"}'
                            ),
                        ],
                    )
                )
            else:
                response = ChatResponse(
                    messages=Message(
                        "assistant",
                        [
                            Content.from_function_call(
                                call_id="1", name="client_side_tool", arguments='{"query": "test"}'
                            )
                        ],
                    )
                )
        else:
            response = ChatResponse(messages=Message("assistant", ["Tool executed successfully."]))

        self._iteration += 1
        return response

    async def _stream_response(self) -> AsyncIterable[ChatResponseUpdate]:
        if self._iteration == 0:
            if self._mixed_request:
                yield ChatResponseUpdate(
                    contents=self._mixed_request_contents(),
                    role="assistant",
                )
            elif self._parallel_request:
                yield ChatResponseUpdate(
                    contents=[
                        Content.from_function_call(call_id="1", name="client_side_tool", arguments='{"query": "test"}'),
                        Content.from_function_call(
                            call_id="2", name="client_side_tool", arguments='{"query": "test2"}'
                        ),
                    ],
                    role="assistant",
                )
            else:
                yield ChatResponseUpdate(
                    contents=[
                        Content.from_function_call(call_id="1", name="client_side_tool", arguments='{"query": "test"}')
                    ],
                    role="assistant",
                )
        else:
            yield ChatResponseUpdate(contents=[Content.from_text(text="Tool executed ")], role="assistant")
            yield ChatResponseUpdate(contents=[Content.from_text(text="successfully.")], role="assistant")

        self._iteration += 1


class ComputerUseMockChatClient(BaseChatClient[Any]):
    """Emit a computer request, then record the result used to resume it."""

    def __init__(self, *, parallel_requests: bool = False) -> None:
        super().__init__()
        self.parallel_requests = parallel_requests
        self.received_messages: list[list[Message]] = []

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        self.received_messages.append(list(messages))
        if len(self.received_messages) == 1:
            contents = [
                Content.from_computer_tool_call(
                    id="computer-item-1",
                    call_id="computer-call-1",
                    actions=[{"type": "move", "x": 1, "y": 2}, {"type": "click", "x": 1, "y": 2}],
                    pending_safety_checks=[{"id": "safety-1", "message": "Review before clicking."}],
                )
            ]
            if self.parallel_requests:
                contents.append(
                    Content.from_computer_tool_call(
                        id="computer-item-2",
                        call_id="computer-call-2",
                        actions=[{"type": "click", "x": 3, "y": 4}],
                        pending_safety_checks=[{"id": "safety-2", "message": "Review before clicking."}],
                    )
                )
        else:
            contents = [Content.from_text("Computer task complete.")]

        if stream:

            async def updates() -> AsyncIterable[ChatResponseUpdate]:
                yield ChatResponseUpdate(contents=contents, role="assistant")

            return self._build_response_stream(updates())

        async def response() -> ChatResponse:
            return ChatResponse(messages=Message(role="assistant", contents=contents))

        return response()


async def test_workflow_agent_computer_call_resumes_with_explicit_safety_acknowledgment() -> None:
    client = ComputerUseMockChatClient()
    agent = Agent(client=client, name="ComputerAgent")
    workflow = WorkflowBuilder(start_executor=agent).build()
    workflow_agent = workflow.as_agent()

    paused = await workflow_agent.run("Use the computer")
    [request] = paused.user_input_requests
    assert request.type == "computer_tool_call"
    assert request.id == "computer-item-1"
    assert request.call_id == "computer-call-1"
    assert request.actions == [{"type": "move", "x": 1, "y": 2}, {"type": "click", "x": 1, "y": 2}]
    assert request.pending_safety_checks == [{"id": "safety-1", "message": "Review before clicking."}]
    assert len(client.received_messages) == 1

    result = Content.from_computer_tool_result(
        call_id=request.call_id or "",
        screenshot=Content.from_data(b"png", "image/png"),
        acknowledged_safety_checks=[{"id": "safety-1"}],
    )
    resumed = await workflow_agent.run(Message(role="tool", contents=[result]))
    assert resumed.text == "Computer task complete."
    [tool_message] = [message for message in client.received_messages[-1] if message.role == "tool"]
    assert tool_message.role == "tool"
    [received_result] = tool_message.contents
    assert received_result.type == "computer_tool_result"
    assert received_result.call_id == "computer-call-1"
    assert received_result.screenshot is not None
    assert received_result.screenshot.uri == "data:image/png;base64,cG5n"
    assert received_result.acknowledged_safety_checks == [{"id": "safety-1"}]


async def test_workflow_agent_computer_call_resumes_without_screenshot() -> None:
    client = ComputerUseMockChatClient()
    workflow_agent = WorkflowBuilder(start_executor=Agent(client=client, name="ComputerAgent")).build().as_agent()

    paused = await workflow_agent.run("Use the computer")
    [request] = paused.user_input_requests
    result = Content.from_computer_tool_result(
        call_id="computer-call-1", acknowledged_safety_checks=[{"id": "safety-1"}]
    )

    resumed = await workflow_agent.run(Message(role="tool", contents=[result]))

    assert request.call_id == result.call_id
    assert resumed.text == "Computer task complete."
    [tool_message] = [message for message in client.received_messages[-1] if message.role == "tool"]
    [received_result] = tool_message.contents
    assert received_result.call_id == request.call_id
    assert received_result.screenshot is None
    assert received_result.acknowledged_safety_checks == [{"id": "safety-1"}]


@pytest.mark.parametrize(
    ("call_id", "acknowledged_checks", "message"),
    [
        ("computer-call-1", None, "explicitly acknowledge exactly"),
        ("computer-call-1", [{"id": "not-pending"}], "explicitly acknowledge exactly"),
        ("other-call", [{"id": "safety-1"}], "must match exactly one pending request"),
    ],
)
async def test_workflow_agent_computer_call_rejects_unmatched_safety_or_call_id(
    call_id: str, acknowledged_checks: list[ComputerSafetyCheck] | None, message: str
) -> None:
    client = ComputerUseMockChatClient()
    workflow_agent = WorkflowBuilder(start_executor=Agent(client=client, name="ComputerAgent")).build().as_agent()
    paused = await workflow_agent.run("Use the computer")
    assert len(paused.user_input_requests) == 1

    with pytest.raises(AgentInvalidResponseException, match=message):
        await workflow_agent.run(
            Message(
                role="tool",
                contents=[
                    Content.from_computer_tool_result(
                        call_id=call_id,
                        screenshot=Content.from_data(b"png", "image/png"),
                        acknowledged_safety_checks=acknowledged_checks,
                    )
                ],
            )
        )
    assert len(client.received_messages) == 1


async def test_workflow_agent_streams_computer_request_and_resume() -> None:
    client = ComputerUseMockChatClient()
    workflow_agent = WorkflowBuilder(start_executor=Agent(client=client, name="ComputerAgent")).build().as_agent()

    updates = [update async for update in workflow_agent.run("Use the computer", stream=True)]
    requests = [content for update in updates for content in update.user_input_requests]
    [request] = requests
    assert request.id == "computer-item-1"
    assert request.actions is not None
    assert [action["type"] for action in request.actions] == ["move", "click"]

    result = Content.from_computer_tool_result(
        call_id=request.call_id or "",
        screenshot=Content.from_uri("https://example.com/screenshot.png", media_type="image/png"),
        acknowledged_safety_checks=[{"id": "safety-1"}],
    )
    resumed = [update async for update in workflow_agent.run(Message(role="tool", contents=[result]), stream=True)]
    assert any(update.text == "Computer task complete." for update in resumed)
    [tool_message] = [message for message in client.received_messages[-1] if message.role == "tool"]
    [received_result] = tool_message.contents
    assert received_result.type == "computer_tool_result"
    assert received_result.screenshot is result.screenshot


@pytest.mark.parametrize(
    ("stream", "restore_checkpoint"),
    [(False, False), (True, False), (False, True)],
)
async def test_workflow_parallel_computer_results_keep_request_order(stream: bool, restore_checkpoint: bool) -> None:
    client = ComputerUseMockChatClient(parallel_requests=True)
    storage = InMemoryCheckpointStorage() if restore_checkpoint else None
    workflow = WorkflowBuilder(
        start_executor=Agent(client=client, name="ComputerAgent"),
        checkpoint_storage=storage,
    ).build()

    if stream:
        requests = [
            event async for event in workflow.run("Use the computer", stream=True) if event.type == "request_info"
        ]
    else:
        requests = (await workflow.run("Use the computer")).get_request_info_events()
    assert [request.data.call_id for request in requests] == ["computer-call-1", "computer-call-2"]

    first, second = requests
    first_result = Content.from_computer_tool_result(
        call_id="computer-call-1",
        screenshot=Content.from_data(b"first", "image/png"),
        acknowledged_safety_checks=[{"id": "safety-1"}],
    )
    second_result = Content.from_computer_tool_result(
        call_id="computer-call-2",
        screenshot=Content.from_data(b"second", "image/png"),
        acknowledged_safety_checks=[{"id": "safety-2"}],
    )
    if stream:
        partial = [event async for event in workflow.run(responses={second.request_id: second_result}, stream=True)]
        assert not any(event.type == "output" for event in partial)
    else:
        partial = await workflow.run(responses={second.request_id: second_result})
        assert partial.get_outputs() == []
    assert len(client.received_messages) == 1

    if storage is not None:
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        partial_checkpoint = next(
            checkpoint
            for checkpoint in reversed(checkpoints)
            if first.request_id in checkpoint.pending_request_info_events
            and checkpoint.state.get("_executor_state", {}).get("ComputerAgent", {}).get("pending_responses_to_agent")
        )
        workflow = WorkflowBuilder(
            name=workflow.name,
            start_executor=Agent(client=client, name="ComputerAgent"),
            checkpoint_storage=storage,
        ).build()
        resumed = await workflow.run(
            checkpoint_id=partial_checkpoint.checkpoint_id,
            responses={first.request_id: first_result},
        )
        assert resumed.get_outputs()
    elif stream:
        resumed_updates = [
            event async for event in workflow.run(responses={first.request_id: first_result}, stream=True)
        ]
        assert any(event.type == "output" for event in resumed_updates)
    else:
        resumed = await workflow.run(responses={first.request_id: first_result})
        assert resumed.get_outputs()

    [tool_message] = [message for message in client.received_messages[-1] if message.role == "tool"]
    assert [content.call_id for content in tool_message.contents] == ["computer-call-1", "computer-call-2"]
    assert [content.acknowledged_safety_checks for content in tool_message.contents] == [
        [{"id": "safety-1"}],
        [{"id": "safety-2"}],
    ]


async def test_workflow_agent_parallel_computer_results_follow_call_order() -> None:
    client = ComputerUseMockChatClient(parallel_requests=True)
    workflow_agent = WorkflowBuilder(start_executor=Agent(client=client, name="ComputerAgent")).build().as_agent()
    first, second = (await workflow_agent.run("Use the computer")).user_input_requests

    resumed = await workflow_agent.run(
        Message(
            role="tool",
            contents=[
                Content.from_computer_tool_result(
                    call_id=second.call_id or "",
                    screenshot=Content.from_data(b"second", "image/png"),
                    acknowledged_safety_checks=[{"id": "safety-2"}],
                ),
                Content.from_computer_tool_result(
                    call_id=first.call_id or "",
                    screenshot=Content.from_data(b"first", "image/png"),
                    acknowledged_safety_checks=[{"id": "safety-1"}],
                ),
            ],
        )
    )

    assert resumed.text == "Computer task complete."
    [tool_message] = [message for message in client.received_messages[-1] if message.role == "tool"]
    assert [content.call_id for content in tool_message.contents] == ["computer-call-1", "computer-call-2"]


async def test_workflow_reverse_computer_cancellations_keep_request_order() -> None:
    client = ComputerUseMockChatClient(parallel_requests=True)
    workflow = WorkflowBuilder(start_executor=Agent(client=client, name="ComputerAgent")).build()
    first, second = (await workflow.run("Use the computer")).get_request_info_events()

    partial = await workflow.cancel_pending_requests([second.request_id])
    assert partial.get_outputs() == []

    cancelled = await workflow.cancel_pending_requests([first.request_id])
    errors = [
        content.message
        for output in cancelled.get_outputs()
        for message in output.messages
        for content in message.contents
        if content.type == "error"
    ]
    assert errors == [
        "Computer call computer-call-1 was cancelled without a result.",
        "Computer call computer-call-2 was cancelled without a result.",
    ]
    assert len(client.received_messages) == 1


async def test_workflow_cancellation_does_not_fabricate_computer_result() -> None:
    client = ComputerUseMockChatClient()
    workflow = WorkflowBuilder(start_executor=Agent(client=client, name="ComputerAgent")).build()
    paused = await workflow.run("Use the computer")
    [request] = paused.get_request_info_events()
    assert request.request_id == "computer-item-1"
    assert request.data.call_id == "computer-call-1"

    cancelled = await workflow.cancel_pending_requests([request.request_id])
    outputs = cancelled.get_outputs()
    assert len(client.received_messages) == 1
    assert all(
        content.type != "computer_tool_result"
        for output in outputs
        for msg in output.messages
        for content in msg.contents
    )
    errors = [
        content
        for output in outputs
        for msg in output.messages
        for content in msg.contents
        if content.type == "error" and content.additional_properties.get("cancelled_computer_call")
    ]
    assert len(errors) == 1
    assert errors[0].message == "Computer call computer-call-1 was cancelled without a result."


async def test_agent_executor_declaration_only_tool_emits_request_info() -> None:
    """Test that AgentExecutor emits request_info when agent calls a declaration-only tool."""
    agent = Agent(
        client=DeclarationOnlyMockChatClient(),
        name="DeclarationOnlyAgent",
        tools=[declaration_only_tool],
    )

    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

    # Act
    events = await workflow.run("Use the client side tool")

    # Assert - workflow should pause with a request_info event
    request_info_events = events.get_request_info_events()
    assert len(request_info_events) == 1
    request = request_info_events[0]
    assert request.data.type == "function_call"
    assert request.data.name == "client_side_tool"
    assert request.data.call_id == "1"

    # Act - provide the function result to resume the workflow
    events = await workflow.run(
        responses={
            request.request_id: Content.from_function_result(call_id=request.data.call_id, result="client result")
        }
    )

    # Assert - workflow should complete
    final_response = events.get_outputs()
    assert len(final_response) == 1
    assert final_response[0] == "Tool executed successfully."


async def test_workflow_agent_preserves_structured_declaration_only_tool_result() -> None:
    """WorkflowAgent keeps a client-tool result typed and tool-role for the owning AgentExecutor."""
    client = DeclarationOnlyMockChatClient()
    agent = Agent(
        client=client,
        name="DeclarationOnlyAgent",
        tools=[declaration_only_tool],
    )
    workflow = WorkflowBuilder(start_executor=agent).build()
    workflow_agent = workflow.as_agent()

    paused = await workflow_agent.run("Use the client side tool")
    [request] = paused.user_input_requests
    assert request.call_id is not None

    resumed = await workflow_agent.run(
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id=request.call_id, result={"answer": 42})],
        )
    )

    assert resumed.text == "Tool executed successfully."
    tool_messages = [message for message in client.received_messages[-1] if message.role == "tool"]
    assert len(tool_messages) == 1
    [result] = tool_messages[0].contents
    assert result.type == "function_result"
    assert result.result == '{"answer": 42}'


async def test_agent_executor_declaration_only_tool_emits_request_info_streaming() -> None:
    """Test that AgentExecutor emits request_info for declaration-only tools in streaming mode."""
    agent = Agent(
        client=DeclarationOnlyMockChatClient(),
        name="DeclarationOnlyAgent",
        tools=[declaration_only_tool],
    )

    workflow = WorkflowBuilder(start_executor=agent).add_edge(agent, test_executor).build()

    # Act
    request_info_events: list[WorkflowEvent] = []
    async for event in workflow.run("Use the client side tool", stream=True):
        if event.type == "request_info":
            request_info_events.append(event)

    # Assert
    assert len(request_info_events) == 1
    request = request_info_events[0]
    assert request.data.type == "function_call"
    assert request.data.name == "client_side_tool"
    assert request.data.call_id == "1"

    # Act - provide the function result
    output: str | None = None
    async for event in workflow.run(
        stream=True,
        responses={
            request.request_id: Content.from_function_result(call_id=request.data.call_id, result="client result")
        },
    ):
        if event.type == "output":
            output = event.data

    # Assert
    assert output is not None
    assert output == "Tool executed successfully."


async def test_agent_executor_parallel_declaration_only_tool_emits_request_info() -> None:
    """Test that AgentExecutor emits request_info for parallel declaration-only tool calls."""
    agent = Agent(
        client=DeclarationOnlyMockChatClient(parallel_request=True),
        name="DeclarationOnlyAgent",
        tools=[declaration_only_tool],
    )

    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

    # Act
    events = await workflow.run("Use the client side tool")

    # Assert - should get 2 request_info events
    request_info_events = events.get_request_info_events()
    assert len(request_info_events) == 2
    for req in request_info_events:
        assert req.data.type == "function_call"
        assert req.data.name == "client_side_tool"

    # Act - provide both function results
    responses = {
        req.request_id: Content.from_function_result(call_id=req.data.call_id, result=f"result for {req.data.call_id}")
        for req in request_info_events
    }
    events = await workflow.run(responses=responses)

    # Assert - workflow should complete
    final_response = events.get_outputs()
    assert len(final_response) == 1
    assert final_response[0] == "Tool executed successfully."


async def test_workflow_cancels_host_member_of_mixed_batch_with_terminal_result() -> None:
    """Cancelling a Host-owned sibling completes the mixed batch with its exact call identity."""
    client = DeclarationOnlyMockChatClient(mixed_request=True)
    agent = Agent(
        client=client,
        name="MixedApprovalAgent",
        tools=[mock_tool_requiring_approval, declaration_only_tool],
    )
    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

    paused = await workflow.run("Run both tools")
    requests = paused.get_request_info_events()
    approval_request = next(request for request in requests if request.data.type == "function_approval_request")
    host_request = next(request for request in requests if request.data.type == "function_call")

    cancelled = await workflow.cancel_pending_requests([host_request.request_id])
    assert cancelled.get_outputs() == []

    resumed = await workflow.run(
        responses={
            approval_request.request_id: approval_request.data.to_function_approval_response(approved=True),
        }
    )

    assert resumed.get_outputs() == ["Tool executed successfully."]
    function_results = [
        content
        for message in client.received_messages[-1]
        for content in message.contents
        if content.type == "function_result"
    ]
    cancelled_result = next(result for result in function_results if result.call_id == host_request.data.call_id)
    assert cancelled_result.additional_properties["cancelled"] is True


async def test_workflow_host_cancellation_preserves_occurrence_with_reused_call_id() -> None:
    """A Host cancellation identifies the exact occurrence when sibling call IDs are reused."""
    client = DeclarationOnlyMockChatClient(mixed_request=True, duplicate_host_call_id=True)
    agent = Agent(
        client=client,
        name="MixedApprovalAgent",
        tools=[mock_tool_requiring_approval, declaration_only_tool],
    )
    workflow = WorkflowBuilder(start_executor=agent, output_from=[test_executor]).add_edge(agent, test_executor).build()

    paused = await workflow.run("Run all tools")
    requests = paused.get_request_info_events()
    approval_request = next(request for request in requests if request.data.type == "function_approval_request")
    host_requests = [request for request in requests if request.data.type == "function_call"]
    assert len(host_requests) == 2
    assert host_requests[0].data.call_id == host_requests[1].data.call_id
    assert host_requests[0].data.id != host_requests[1].data.id

    cancelled = await workflow.cancel_pending_requests([host_requests[0].request_id])
    assert cancelled.get_outputs() == []

    sibling_result = Content.from_function_result(
        call_id=host_requests[1].data.call_id,
        result="Host sibling completed.",
    )
    sibling_result.id = host_requests[1].data.id
    resumed = await workflow.run(
        responses={
            approval_request.request_id: approval_request.data.to_function_approval_response(approved=True),
            host_requests[1].request_id: sibling_result,
        }
    )

    assert resumed.get_outputs() == ["Tool executed successfully."]
    function_results = [
        content
        for message in client.received_messages[-1]
        for content in message.contents
        if content.type == "function_result" and content.call_id == host_requests[0].data.call_id
    ]
    assert {result.id for result in function_results} == {
        host_requests[0].data.id,
        host_requests[1].data.id,
    }
    cancelled_result = next(result for result in function_results if result.id == host_requests[0].data.id)
    assert cancelled_result.additional_properties["cancelled"] is True
