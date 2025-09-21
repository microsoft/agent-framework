# Copyright (c) Microsoft. All rights reserved.

import uuid
from typing import Any

import pytest

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentRunUpdateEvent,
    ChatMessage,
    Executor,
    FunctionCallContent,
    FunctionResultContent,
    RequestInfoExecutor,
    RequestInfoMessage,
    Role,
    TextContent,
    UsageContent,
    UsageDetails,
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
        response_text = f"{self.response_text}: {input_text}"

        # Create response message for both streaming and non-streaming cases
        response_message = ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=response_text)])

        # Emit update event.
        streaming_update = AgentRunResponseUpdate(
            contents=[TextContent(text=response_text)], role=Role.ASSISTANT, message_id=str(uuid.uuid4())
        )
        await ctx.add_event(AgentRunUpdateEvent(executor_id=self.id, data=streaming_update))

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
        update = AgentRunResponseUpdate(
            contents=[TextContent(text="Request completed successfully")],
            role=Role.ASSISTANT,
            message_id=str(uuid.uuid4()),
        )
        await ctx.add_event(AgentRunUpdateEvent(executor_id=self.id, data=update))


class TestWorkflowAgent:
    """Test cases for WorkflowAgent end-to-end functionality."""

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
        step1_messages: list[ChatMessage] = []
        step2_messages: list[ChatMessage] = []

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
        step1_text: str = step1_messages[0].contents[0].text  # type: ignore[attr-defined]
        step2_text: str = step2_messages[0].contents[0].text  # type: ignore[attr-defined]
        assert "Step1: Hello World" in step1_text
        assert "Step2: Step1: Hello World" in step2_text

    async def test_end_to_end_basic_workflow_streaming(self):
        """Test end-to-end workflow with streaming executor that emits AgentRunStreamingEvent."""
        # Create a single streaming executor
        executor1 = SimpleExecutor(id="stream1", response_text="Streaming1", emit_streaming=True)
        executor2 = SimpleExecutor(id="stream2", response_text="Streaming2", emit_streaming=True)

        # Create workflow with just one executor
        workflow = WorkflowBuilder().set_start_executor(executor1).add_edge(executor1, executor2).build()

        agent = WorkflowAgent(workflow=workflow, name="Streaming Test Agent")

        # Execute workflow streaming to capture streaming events
        updates: list[AgentRunResponseUpdate] = []
        async for update in agent.run_stream("Test input"):
            updates.append(update)

        # Should have received at least one streaming update
        assert len(updates) >= 2, f"Expected at least 2 updates, got {len(updates)}"

        # Verify we got a streaming update
        assert updates[0].contents is not None
        first_content: TextContent = updates[0].contents[0]  # type: ignore[assignment]
        second_content: TextContent = updates[1].contents[0]  # type: ignore[assignment]
        assert isinstance(first_content, TextContent)
        assert "Streaming1: Test input" in first_content.text
        assert isinstance(second_content, TextContent)
        assert "Streaming2: Streaming1: Test input" in second_content.text

    async def test_end_to_end_request_info_handling(self):
        """Test end-to-end workflow with RequestInfoEvent handling."""
        # Create workflow with requesting executor -> request info executor (no cycle)
        requesting_executor = RequestingExecutor(id="requester")
        request_info_executor = RequestInfoExecutor(id="request_info")

        workflow = (
            WorkflowBuilder()
            .set_start_executor(requesting_executor)
            .add_edge(requesting_executor, request_info_executor)
            .build()
        )

        agent = WorkflowAgent(workflow=workflow, name="Request Test Agent")

        # Execute workflow streaming to get request info event
        updates: list[AgentRunResponseUpdate] = []
        async for update in agent.run_stream("Start request"):
            updates.append(update)
        # Should have received a function call for the request info
        assert len(updates) > 0

        # Find the function call update (RequestInfoEvent converted to function call)
        function_call_update: AgentRunResponseUpdate | None = None
        for update in updates:
            if update.contents and hasattr(update.contents[0], "name") and update.contents[0].name == "request_info":  # type: ignore[attr-defined]
                function_call_update = update
                break

        assert function_call_update is not None, "Should have received a request_info function call"
        function_call: FunctionCallContent = function_call_update.contents[0]  # type: ignore[assignment]

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
            role=Role.USER,
            contents=[FunctionResultContent(call_id=function_call.call_id, result="User provided answer")],
        )

        # Continue the workflow with the response
        continuation_result = await agent.run(response_message)

        # Should complete successfully
        assert isinstance(continuation_result, AgentRunResponse)

        # Verify cleanup - pending requests should be cleared after function response handling
        assert len(agent.pending_requests) == 0

    def test_workflow_as_agent_method(self) -> None:
        """Test that Workflow.as_agent() creates a properly configured WorkflowAgent."""
        # Create a simple workflow
        executor = SimpleExecutor(id="executor1", response_text="Response", emit_streaming=False)
        workflow = WorkflowBuilder().set_start_executor(executor).build()

        # Test as_agent with a name
        agent = workflow.as_agent(name="TestAgent")

        # Verify the agent is properly configured
        assert isinstance(agent, WorkflowAgent)
        assert agent.name == "TestAgent"
        assert agent.workflow is workflow
        assert agent.workflow.id == workflow.id

        # Test as_agent without a name (should use default)
        agent_no_name = workflow.as_agent()
        assert isinstance(agent_no_name, WorkflowAgent)
        assert agent_no_name.workflow is workflow

    def test_workflow_as_agent_cannot_handle_agent_inputs(self) -> None:
        """Test that Workflow.as_agent() raises an error if the start executor cannot handle agent inputs."""

        class _Executor(Executor):
            @handler
            async def handle_bool(self, message: bool, context: WorkflowContext[Any]) -> None:
                raise ValueError("Unsupported message type")

        # Create a simple workflow
        executor = _Executor(id="test")
        workflow = WorkflowBuilder().set_start_executor(executor).build()

        # Try to create an agent with unsupported input types
        with pytest.raises(ValueError, match="Workflow's start executor cannot handle list\\[ChatMessage\\]"):
            workflow.as_agent()


class TestWorkflowAgentMergeUpdates:
    """Test cases specifically for the WorkflowAgent.merge_updates static method."""

    def test_merge_updates_ordering_by_response_and_message_id(self):
        """Test that merge_updates correctly orders messages by response_id groups and message_id chronologically."""
        # Create updates with different response_ids and message_ids in non-chronological order
        updates = [
            # Response B, Message 2 (latest in resp B)
            AgentRunResponseUpdate(
                contents=[TextContent(text="RespB-Msg2")],
                role=Role.ASSISTANT,
                response_id="resp-b",
                message_id="msg-2",
                created_at="2024-01-01T12:02:00Z",
            ),
            # Response A, Message 1 (earliest overall)
            AgentRunResponseUpdate(
                contents=[TextContent(text="RespA-Msg1")],
                role=Role.ASSISTANT,
                response_id="resp-a",
                message_id="msg-1",
                created_at="2024-01-01T12:00:00Z",
            ),
            # Response B, Message 1 (earlier in resp B)
            AgentRunResponseUpdate(
                contents=[TextContent(text="RespB-Msg1")],
                role=Role.ASSISTANT,
                response_id="resp-b",
                message_id="msg-1",
                created_at="2024-01-01T12:01:00Z",
            ),
            # Response A, Message 2 (later in resp A)
            AgentRunResponseUpdate(
                contents=[TextContent(text="RespA-Msg2")],
                role=Role.ASSISTANT,
                response_id="resp-a",
                message_id="msg-2",
                created_at="2024-01-01T12:00:30Z",
            ),
            # Global dangling update (no response_id) - should go at end
            AgentRunResponseUpdate(
                contents=[TextContent(text="Global-Dangling")],
                role=Role.ASSISTANT,
                response_id=None,
                message_id="msg-global",
                created_at="2024-01-01T11:59:00Z",  # Earliest timestamp but should be last
            ),
        ]

        result = WorkflowAgent.merge_updates(updates, "final-response-id")

        # Verify correct response_id is set
        assert result.response_id == "final-response-id"

        # Should have 5 messages total
        assert len(result.messages) == 5

        # Verify ordering: responses are processed by response_id groups,
        # within each group messages are chronologically ordered,
        # global dangling goes at the end
        message_texts = [
            msg.contents[0].text if isinstance(msg.contents[0], TextContent) else "" for msg in result.messages
        ]

        # The exact order depends on dict iteration order for response_ids,
        # but within each response group, chronological order should be maintained
        # and global dangling should be last
        assert "Global-Dangling" in message_texts[-1]  # Global dangling at end

        # Find positions of resp-a and resp-b messages
        resp_a_positions = [i for i, text in enumerate(message_texts) if "RespA" in text]
        resp_b_positions = [i for i, text in enumerate(message_texts) if "RespB" in text]

        # Within resp-a group: Msg1 (earlier) should come before Msg2 (later)
        resp_a_texts = [message_texts[i] for i in resp_a_positions]
        assert resp_a_texts.index("RespA-Msg1") < resp_a_texts.index("RespA-Msg2")

        # Within resp-b group: Msg1 (earlier) should come before Msg2 (later)
        resp_b_texts = [message_texts[i] for i in resp_b_positions]
        assert resp_b_texts.index("RespB-Msg1") < resp_b_texts.index("RespB-Msg2")

        # ENHANCED: Verify response group separation and ordering
        # Messages from the same response_id should be grouped together (not interleaved)

        # Check resp-a group is contiguous (all positions are consecutive)
        if len(resp_a_positions) > 1:
            for i in range(1, len(resp_a_positions)):
                assert resp_a_positions[i] == resp_a_positions[i - 1] + 1, (
                    f"RespA messages are not contiguous: positions {resp_a_positions}"
                )

        # Check resp-b group is contiguous (all positions are consecutive)
        if len(resp_b_positions) > 1:
            for i in range(1, len(resp_b_positions)):
                assert resp_b_positions[i] == resp_b_positions[i - 1] + 1, (
                    f"RespB messages are not contiguous: positions {resp_b_positions}"
                )

        # Response groups are no longer required to be ordered by latest timestamp
        # We only ensure messages within each group are chronologically ordered
        # Verify global dangling message position (should be last, after all response groups)
        global_dangling_pos = message_texts.index("Global-Dangling")
        if resp_a_positions:
            assert global_dangling_pos > max(resp_a_positions), "Global dangling should come after resp-a group"
        if resp_b_positions:
            assert global_dangling_pos > max(resp_b_positions), "Global dangling should come after resp-b group"

    def test_merge_updates_metadata_aggregation(self):
        """Test that merge_updates correctly aggregates usage details, timestamps, and additional properties."""
        # Create updates with various metadata including usage details
        updates = [
            AgentRunResponseUpdate(
                contents=[
                    TextContent(text="First"),
                    UsageContent(
                        details=UsageDetails(input_token_count=10, output_token_count=5, total_token_count=15)
                    ),
                ],
                role=Role.ASSISTANT,
                response_id="resp-1",
                message_id="msg-1",
                created_at="2024-01-01T12:00:00Z",
                additional_properties={"source": "executor1", "priority": "high"},
            ),
            AgentRunResponseUpdate(
                contents=[
                    TextContent(text="Second"),
                    UsageContent(
                        details=UsageDetails(input_token_count=20, output_token_count=8, total_token_count=28)
                    ),
                ],
                role=Role.ASSISTANT,
                response_id="resp-2",
                message_id="msg-2",
                created_at="2024-01-01T12:01:00Z",  # Later timestamp
                additional_properties={"source": "executor2", "category": "analysis"},
            ),
            AgentRunResponseUpdate(
                contents=[
                    TextContent(text="Third"),
                    UsageContent(details=UsageDetails(input_token_count=5, output_token_count=3, total_token_count=8)),
                ],
                role=Role.ASSISTANT,
                response_id="resp-1",  # Same response_id as first
                message_id="msg-3",
                created_at="2024-01-01T11:59:00Z",  # Earlier timestamp
                additional_properties={"details": "merged", "priority": "low"},  # Different priority value
            ),
        ]

        result = WorkflowAgent.merge_updates(updates, "aggregated-response")

        # Verify response_id is set correctly
        assert result.response_id == "aggregated-response"

        # Verify latest timestamp is used (should be 12:01:00Z from second update)
        assert result.created_at == "2024-01-01T12:01:00Z"

        # Verify messages are present
        assert len(result.messages) == 3

        # Verify usage details are aggregated correctly
        # Should sum all usage details: (10+20+5) + (5+8+3) + (15+28+8) = 35+16+51 = 51 total tokens
        expected_usage = UsageDetails(input_token_count=35, output_token_count=16, total_token_count=51)
        assert result.usage_details == expected_usage

        # Verify additional properties are merged correctly
        # Note: Within response groups, later updates' properties win conflicts,
        # but across response groups, the dict.update() order determines which wins
        expected_properties = {
            "source": "executor2",  # From resp-2 (latest source value)
            "priority": "high",  # From resp-1 first update (resp-1 processed before resp-2)
            "category": "analysis",  # From resp-2 (only place this appears)
            # "details": "merged" is NOT in final result because resp-1's aggregated
            # properties only include final merged result from its own updates
        }
        assert result.additional_properties == expected_properties
