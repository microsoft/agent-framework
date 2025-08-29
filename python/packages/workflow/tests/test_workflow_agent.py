# Copyright (c) Microsoft. All rights reserved.

from typing import Any

import pytest
from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ChatRole,
    FunctionResultContent,
    TextContent,
)
from agent_framework.workflow import (
    AgentRunEvent,
    AgentRunStreamingEvent,
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)


class SimpleExecutor(Executor):
    """Simple executor that emits AgentRunEvent or AgentRunStreamingEvent."""

    response_text: str
    emit_streaming: bool = False

    def __init__(self, id: str, response_text: str, emit_streaming: bool = False):
        super().__init__(id=id, response_text=response_text, emit_streaming=emit_streaming)

    @handler
    async def handle_message(self, message: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        input_text = (
            message[0].contents[0].text if message and isinstance(message[0].contents[0], TextContent) else "no input"
        )
        await self._process_message(input_text, ctx)

    async def _process_message(self, input_text: str, ctx: WorkflowContext[list[ChatMessage]]) -> None:
        response_text = f"{self.response_text}: {input_text}"

        # Create response message for both streaming and non-streaming cases
        response_message = ChatMessage(role=ChatRole.ASSISTANT, contents=[TextContent(text=response_text)])

        if self.emit_streaming:
            # Emit streaming update
            streaming_update = AgentRunResponseUpdate(
                contents=[TextContent(text=response_text)],
                role=ChatRole.ASSISTANT,
            )
            await ctx.add_event(AgentRunStreamingEvent(executor_id=self.id, data=streaming_update))
        else:
            # Emit agent run event
            agent_response = AgentRunResponse(messages=[response_message])
            await ctx.add_event(AgentRunEvent(executor_id=self.id, data=agent_response))

        # Pass message to next executor if any (for both streaming and non-streaming)
        await ctx.send_message([response_message])


class RequestingExecutor(Executor):
    """Executor that sends RequestInfoMessage to trigger RequestInfoEvent."""

    @handler
    async def handle_message(self, _: list[ChatMessage], ctx: WorkflowContext[RequestInfoMessage]) -> None:
        # Send a RequestInfoMessage to trigger the request info process
        await ctx.send_message(RequestInfoMessage())

    @handler
    async def handle_request_response(self, _: Any, ctx: WorkflowContext[ChatMessage]) -> None:
        # Handle the response and emit completion response
        response_message = ChatMessage(
            role=ChatRole.ASSISTANT, contents=[TextContent(text="Request completed successfully")]
        )
        agent_response = AgentRunResponse(messages=[response_message])
        await ctx.add_event(AgentRunEvent(executor_id=self.id, data=agent_response))


class TestWorkflowAgent:
    """Test cases for WorkflowAgent end-to-end functionality."""

    @pytest.mark.asyncio
    async def test_end_to_end_basic_workflow(self):
        """Test basic end-to-end workflow execution with 2 executors emitting AgentRunEvent."""
        # Create workflow with two executors
        executor1 = SimpleExecutor(id="executor1", response_text="Step1", emit_streaming=False)
        executor2 = SimpleExecutor(id="executor2", response_text="Step2", emit_streaming=False)

        workflow = WorkflowBuilder().set_start_executor(executor1).add_edge(executor1, executor2).build()

        agent = WorkflowAgent(workflow=workflow, name="Test Agent")

        # Execute workflow end-to-end
        result = await agent.run("Hello World")

        # Verify we got responses from both executors
        assert isinstance(result, AgentRunResponse)
        assert len(result.messages) >= 2, f"Expected at least 2 messages, got {len(result.messages)}"

        # Find messages from each executor
        step1_messages = []
        step2_messages = []

        for message in result.messages:
            first_content = message.contents[0]
            if isinstance(first_content, TextContent):
                text = first_content.text
                if text.startswith("Step1:"):
                    step1_messages.append(message)
                elif text.startswith("Step2:"):
                    step2_messages.append(message)

        # Verify both executors produced output
        assert len(step1_messages) >= 1, "Should have received message from Step1 executor"
        assert len(step2_messages) >= 1, "Should have received message from Step2 executor"

        # Verify the processing worked for both
        step1_text = step1_messages[0].contents[0].text
        step2_text = step2_messages[0].contents[0].text
        assert "Step1: Hello World" in step1_text
        assert "Step2: Step1: Hello World" in step2_text

    @pytest.mark.asyncio
    async def test_end_to_end_basic_workflow_streaming(self):
        """Test end-to-end workflow with streaming executor that emits AgentRunStreamingEvent."""
        # Create a single streaming executor
        executor1 = SimpleExecutor(id="stream1", response_text="Streaming1", emit_streaming=True)
        executor2 = SimpleExecutor(id="stream2", response_text="Streaming2", emit_streaming=True)

        # Create workflow with just one executor
        workflow = WorkflowBuilder().set_start_executor(executor1).add_edge(executor1, executor2).build()

        agent = WorkflowAgent(workflow=workflow, name="Streaming Test Agent")

        # Execute workflow streaming to capture streaming events
        updates = []
        async for update in agent.run_streaming("Test input"):
            updates.append(update)

        # Should have received at least one streaming update
        assert len(updates) >= 2, f"Expected at least 2 updates, got {len(updates)}"

        # Verify we got a streaming update
        assert updates[0].contents is not None
        first_content = updates[0].contents[0]
        second_content = updates[1].contents[0]
        assert isinstance(first_content, TextContent)
        assert "Streaming1: Test input" in first_content.text
        assert isinstance(second_content, TextContent)
        assert "Streaming2: Streaming1: Test input" in second_content.text

    @pytest.mark.asyncio
    async def test_end_to_end_request_info_handling(self):
        """Test end-to-end workflow with RequestInfoEvent handling."""
        # Create workflow with requesting executor -> request info executor (no cycle)
        requesting_executor = RequestingExecutor(id="requester")
        request_info_executor = RequestInfoExecutor()

        workflow = (
            WorkflowBuilder()
            .set_start_executor(requesting_executor)
            .add_edge(requesting_executor, request_info_executor)
            .build()
        )

        agent = WorkflowAgent(workflow=workflow, name="Request Test Agent")

        # Execute workflow streaming to get request info event
        updates = []
        async for update in agent.run_streaming("Start request"):
            updates.append(update)
        # Should have received a function call for the request info
        assert len(updates) > 0

        # Find the function call update (RequestInfoEvent converted to function call)
        function_call_update = None
        for update in updates:
            if update.contents and hasattr(update.contents[0], "name") and update.contents[0].name == "request_info":
                function_call_update = update
                break

        assert function_call_update is not None, "Should have received a request_info function call"
        function_call = function_call_update.contents[0]

        # Verify the function call has expected structure
        assert function_call.call_id is not None
        assert function_call.name == "request_info"
        assert isinstance(function_call.arguments, dict)
        assert "request_id" in function_call.arguments

        # Verify the request is tracked in pending_requests
        assert len(agent.pending_requests) == 1
        assert function_call.call_id in agent.pending_requests

        # Now provide a function result response to test continuation
        response_message = ChatMessage(
            role=ChatRole.USER,
            contents=[FunctionResultContent(call_id=function_call.call_id, result="User provided answer")],
        )

        # Continue the workflow with the response
        continuation_result = await agent.run(response_message)

        # Should complete successfully
        assert isinstance(continuation_result, AgentRunResponse)

        # Verify cleanup - pending requests should be cleared after function response handling
        assert len(agent.pending_requests) == 0
