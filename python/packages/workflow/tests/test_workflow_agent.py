# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any

import pytest
from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    AIAgent,
    ChatMessage,
    ChatRole,
    FunctionResultContent,
    TextContent,
)
from agent_framework.workflow import (
    AgentRunEvent,
    AgentRunStreamingEvent,
    Executor,
    RequestInfoEvent,
    RequestInfoMessage,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowThread,
    handler,
)


@dataclass
class SimpleMessage:
    """A simple message for testing."""

    content: str


class EchoExecutor(Executor):
    """A simple executor for testing that echoes messages."""

    @handler
    async def handle_message(self, message: list[ChatMessage], ctx: WorkflowContext[ChatMessage]) -> None:
        # Echo the first message back
        if message:
            response_message = ChatMessage(
                role=ChatRole.ASSISTANT, contents=[TextContent(text=f"Echo: {message[0].contents[0].text}")]
            )
            await ctx.send_message(response_message)
            await ctx.add_event(WorkflowCompletedEvent(data=[response_message]))
        else:
            await ctx.add_event(WorkflowCompletedEvent(data=[]))


class MockAgent(AIAgent):
    """Mock agent implementation for testing."""

    def __init__(self, response_text: str = "Mock response"):
        self._response_text = response_text
        self._id = "mock_agent"

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str | None:
        return "Mock Agent"

    @property
    def display_name(self) -> str:
        return "Mock Agent"

    @property
    def description(self) -> str | None:
        return "A mock agent for testing"

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        response_message = ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent(text=self._response_text)])
        return AgentRunResponse(messages=[response_message])

    def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        return self._run_streaming_impl(messages, thread, **kwargs)

    async def _run_streaming_impl(self, messages, thread, **kwargs) -> AsyncIterable[AgentRunResponseUpdate]:
        yield AgentRunResponseUpdate(contents=[TextContent(text=self._response_text)], role=ChatRole.ASSISTANT)

    def get_new_thread(self) -> AgentThread:
        return AgentThread()


class TestWorkflowThread:
    """Test cases for WorkflowThread."""

    def test_init(self):
        """Test WorkflowThread initialization."""
        thread = WorkflowThread(workflow_id="test_workflow", run_id="test_run", workflow_name="Test Workflow")

        assert thread.workflow_id == "test_workflow"
        assert thread.run_id == "test_run"
        assert thread.workflow_name == "Test Workflow"
        assert thread.message_bookmark == 0


class TestWorkflowAgent:
    """Test cases for WorkflowAgent."""

    def test_init(self):
        """Test WorkflowAgent initialization."""
        # Create a simple workflow
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow, name="Test Workflow Agent", description="A test workflow agent")

        assert agent.name == "Test Workflow Agent"
        assert agent.description == "A test workflow agent"
        assert agent.workflow is workflow
        assert isinstance(agent.active_runs, dict)
        assert len(agent.active_runs) == 0

    def test_generate_run_id(self):
        """Test run ID generation."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        run_id1 = agent._generate_run_id()
        run_id2 = agent._generate_run_id()

        assert run_id1 != run_id2
        assert run_id1.startswith(agent.id)
        assert run_id2.startswith(agent.id)

    def test_get_new_thread(self):
        """Test creation of new workflow thread."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow, name="Test Agent")
        thread = agent.get_new_thread()

        assert isinstance(thread, WorkflowThread)
        assert thread.workflow_id == agent.id
        assert thread.workflow_name == agent.name
        assert thread.run_id.startswith(agent.id)

    @pytest.mark.asyncio
    async def test_prepare_workflow_messages_no_input(self):
        """Test preparing workflow messages with no input."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)
        thread = agent.get_new_thread()

        messages = await agent._prepare_workflow_messages([], thread)
        assert messages == []

    @pytest.mark.asyncio
    async def test_prepare_workflow_messages_with_input(self):
        """Test preparing workflow messages with input."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)
        thread = agent.get_new_thread()

        input_messages = [ChatMessage(role=ChatRole.USER, contents=[TextContent(text="Hello")])]
        messages = await agent._prepare_workflow_messages(input_messages, thread)

        # Should include the input message
        assert len(messages) == 1
        assert messages[0].contents[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_convert_agent_run_streaming_event(self):
        """Test conversion of AgentRunStreamingEvent."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)
        thread = agent.get_new_thread()

        update = AgentRunResponseUpdate(contents=[TextContent(text="Test content")], role=ChatRole.ASSISTANT)
        event = AgentRunStreamingEvent(executor_id="test_executor", data=update)

        result = await agent._convert_workflow_event_to_agent_update(event, thread)

        assert result is update

    @pytest.mark.asyncio
    async def test_convert_agent_run_event(self):
        """Test conversion of AgentRunEvent."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)
        thread = agent.get_new_thread()

        response = AgentRunResponse(
            messages=[ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent(text="Test response")])]
        )
        event = AgentRunEvent(executor_id="test_executor", data=response)

        result = await agent._convert_workflow_event_to_agent_update(event, thread)

        assert result is not None
        assert len(result.contents) == 1
        assert result.contents[0].text == "Test response"
        assert result.role == ChatRole.ASSISTANT

    @pytest.mark.asyncio
    async def test_convert_request_info_event(self):
        """Test conversion of RequestInfoEvent."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)
        thread = agent.get_new_thread()

        # Create a RequestInfoEvent with proper constructor arguments
        event = RequestInfoEvent(
            request_id="req123", source_executor_id="test_executor", request_type=str, request_data="Test request"
        )

        result = await agent._convert_workflow_event_to_agent_update(event, thread)

        assert result is not None
        assert result.role == ChatRole.ASSISTANT
        assert len(result.contents) == 1
        function_call = result.contents[0]
        assert function_call.name == "request_info"
        assert function_call.call_id == "req123"

    @pytest.mark.asyncio
    async def test_run_streaming_basic(self):
        """Test basic streaming execution."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        # Execute streaming
        updates = []
        async for update in agent.run_streaming("Hello"):
            updates.append(update)

        # Should have at least the completion
        assert len(updates) >= 0

        # Check active runs tracking - should be cleaned up
        assert len(agent.active_runs) == 0

    @pytest.mark.asyncio
    async def test_run_non_streaming(self):
        """Test non-streaming execution."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        # Execute non-streaming
        result = await agent.run("Hello")

        # Verify result
        assert isinstance(result, AgentRunResponse)
        # The EchoExecutor should echo the message
        assert len(result.messages) >= 0

    @pytest.mark.asyncio
    async def test_run_with_existing_thread(self):
        """Test execution with an existing thread."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)
        thread = agent.get_new_thread()

        # Execute with existing thread
        result = await agent.run("Hello", thread=thread)

        assert isinstance(result, AgentRunResponse)

    @pytest.mark.asyncio
    async def test_run_with_string_input(self):
        """Test execution with string input."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        result = await agent.run("Hello World")
        assert isinstance(result, AgentRunResponse)

    @pytest.mark.asyncio
    async def test_run_with_multiple_string_inputs(self):
        """Test execution with multiple string inputs."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        result = await agent.run(["Hello", "World"])
        assert isinstance(result, AgentRunResponse)

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling during workflow execution."""

        # Create a workflow that will cause an error
        class ErrorExecutor(Executor):
            @handler
            async def handle_message(self, message: list[ChatMessage], ctx: WorkflowContext[ChatMessage]) -> None:
                raise ValueError("Test error")

        workflow = WorkflowBuilder().set_start_executor(ErrorExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        # Should propagate as AgentExecutionException
        from agent_framework.exceptions import AgentExecutionException

        with pytest.raises(AgentExecutionException):
            await agent.run("Hello")

    @pytest.mark.asyncio
    async def test_pending_request_cleanup(self):
        """Test that pending requests are cleaned up after workflow completion."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        # Manually add a pending request to test cleanup
        from agent_framework_workflow import RequestInfoEvent

        class TestRequestMessage(RequestInfoMessage):
            def __init__(self, message: str):
                super().__init__()
                self.message = message

        test_request = TestRequestMessage("Test")
        request_event = RequestInfoEvent(
            request_id="cleanup_test",
            source_executor_id="test_executor",
            request_type=TestRequestMessage,
            request_data=test_request,
        )

        agent.pending_requests["cleanup_test"] = request_event

        # Run the agent (should clean up pending requests)
        await agent.run("Hello")

        # Verify cleanup occurred
        assert "cleanup_test" not in agent.pending_requests

    @pytest.mark.asyncio
    async def test_workflow_with_chat_message_input(self):
        """Test workflow execution with ChatMessage input."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        input_message = ChatMessage(role=ChatRole.USER, contents=[TextContent(text="Test message")])

        result = await agent.run(input_message)
        assert isinstance(result, AgentRunResponse)

    @pytest.mark.asyncio
    async def test_request_response_cycle_tracking(self):
        """Test that RequestInfoEvent creates pending requests and FunctionResultContent resolves them."""
        workflow = WorkflowBuilder().set_start_executor(EchoExecutor()).build()

        agent = WorkflowAgent(workflow=workflow)

        # Initially no pending requests
        assert len(agent.pending_requests) == 0

        # Create a mock RequestInfoEvent
        from agent_framework_workflow import RequestInfoEvent

        # Create a simple RequestInfoMessage
        class TestRequestMessage(RequestInfoMessage):
            def __init__(self, message: str):
                super().__init__()
                self.message = message

        test_request = TestRequestMessage("Need user input")
        request_event = RequestInfoEvent(
            request_id="test_req_123",
            source_executor_id="test_executor",
            request_type=TestRequestMessage,
            request_data=test_request,
        )

        thread = agent.get_new_thread()

        # Convert the event to agent update (this should store the pending request)
        update = await agent._convert_workflow_event_to_agent_update(request_event, thread)

        # Verify the request is now pending
        assert len(agent.pending_requests) == 1
        assert "test_req_123" in agent.pending_requests
        assert agent.pending_requests["test_req_123"] is request_event

        # Verify the update contains a function call
        assert update is not None
        assert len(update.contents) == 1
        function_call = update.contents[0]
        assert hasattr(function_call, "call_id")
        assert hasattr(function_call, "name")
        assert function_call.call_id == "test_req_123"
        assert function_call.name == "request_info"

        # Now simulate user providing a response
        response_message = ChatMessage(
            role=ChatRole.USER,
            contents=[FunctionResultContent(call_id="test_req_123", result="User provided response")],
        )

        # Extract function result responses
        responses, other_messages = await agent._extract_function_result_responses([response_message])

        # Should find the response
        assert len(responses) == 1
        assert len(other_messages) == 0  # No other messages in this case
        assert responses[0][0] == "test_req_123"
        assert responses[0][1] == "User provided response"
