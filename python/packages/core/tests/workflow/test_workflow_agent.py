# Copyright (c) Microsoft. All rights reserved.

import uuid
from typing import Any

import pytest

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentRunUpdateEvent,
    AgentThread,
    ChatMessage,
    ChatMessageStore,
    DataContent,
    Executor,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    Role,
    TextContent,
    UriContent,
    UsageContent,
    UsageDetails,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
    response_handler,
)


class SimpleExecutor(Executor):
    """Simple executor that emits AgentRunEvent or AgentRunStreamingEvent."""

    def __init__(self, id: str, response_text: str, emit_streaming: bool = False):
        super().__init__(id=id)
        self.response_text = response_text
        self.emit_streaming = emit_streaming

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
    """Executor that requests info."""

    @handler
    async def handle_message(self, _: list[ChatMessage], ctx: WorkflowContext) -> None:
        # Send a RequestInfoMessage to trigger the request info process
        await ctx.request_info("Mock request data", str)

    @response_handler
    async def handle_request_response(
        self, original_request: str, response: str, ctx: WorkflowContext[ChatMessage]
    ) -> None:
        # Handle the response and emit completion response
        update = AgentRunResponseUpdate(
            contents=[TextContent(text="Request completed successfully")],
            role=Role.ASSISTANT,
            message_id=str(uuid.uuid4()),
        )
        await ctx.add_event(AgentRunUpdateEvent(executor_id=self.id, data=update))


class ConversationHistoryCapturingExecutor(Executor):
    """Executor that captures the received conversation history for verification."""

    def __init__(self, id: str):
        super().__init__(id=id)
        self.received_messages: list[ChatMessage] = []

    @handler
    async def handle_message(self, messages: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        # Capture all received messages
        self.received_messages = list(messages)

        # Count messages by role for the response
        message_count = len(messages)
        response_text = f"Received {message_count} messages"

        response_message = ChatMessage(role=Role.ASSISTANT, contents=[TextContent(text=response_text)])

        streaming_update = AgentRunResponseUpdate(
            contents=[TextContent(text=response_text)], role=Role.ASSISTANT, message_id=str(uuid.uuid4())
        )
        await ctx.add_event(AgentRunUpdateEvent(executor_id=self.id, data=streaming_update))
        await ctx.send_message([response_message])


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
        simple_executor = SimpleExecutor(id="simple", response_text="SimpleResponse", emit_streaming=False)
        requesting_executor = RequestingExecutor(id="requester")

        workflow = (
            WorkflowBuilder().set_start_executor(simple_executor).add_edge(simple_executor, requesting_executor).build()
        )

        agent = WorkflowAgent(workflow=workflow, name="Request Test Agent")

        # Execute workflow streaming to get request info event
        updates: list[AgentRunResponseUpdate] = []
        async for update in agent.run_stream("Start request"):
            updates.append(update)
        # Should have received an approval request for the request info
        assert len(updates) > 0

        approval_update: AgentRunResponseUpdate | None = None
        for update in updates:
            if any(isinstance(content, FunctionApprovalRequestContent) for content in update.contents):
                approval_update = update
                break

        assert approval_update is not None, "Should have received a request_info approval request"

        function_call = next(
            content for content in approval_update.contents if isinstance(content, FunctionCallContent)
        )
        approval_request = next(
            content for content in approval_update.contents if isinstance(content, FunctionApprovalRequestContent)
        )

        # Verify the function call has expected structure
        assert function_call.call_id is not None
        assert function_call.name == "request_info"
        assert isinstance(function_call.arguments, dict)
        assert function_call.arguments.get("request_id") == approval_request.id

        # Approval request should reference the same function call
        assert approval_request.function_call.call_id == function_call.call_id
        assert approval_request.function_call.name == function_call.name

        # Verify the request is tracked in pending_requests
        assert len(agent.pending_requests) == 1
        assert function_call.call_id in agent.pending_requests

        # Now provide an approval response with updated arguments to test continuation
        response_args = WorkflowAgent.RequestInfoFunctionArgs(
            request_id=approval_request.id,
            data="User provided answer",
        ).to_dict()

        approval_response = FunctionApprovalResponseContent(
            approved=True,
            id=approval_request.id,
            function_call=FunctionCallContent(
                call_id=function_call.call_id,
                name=function_call.name,
                arguments=response_args,
            ),
        )

        response_message = ChatMessage(role=Role.USER, contents=[approval_response])

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

    async def test_workflow_as_agent_yield_output_surfaces_as_agent_response(self) -> None:
        """Test that ctx.yield_output() in a workflow executor surfaces as agent output when using .as_agent().

        This validates the fix for issue #2813: WorkflowOutputEvent should be converted to
        AgentRunResponseUpdate when the workflow is wrapped via .as_agent().
        """

        @executor
        async def yielding_executor(messages: list[ChatMessage], ctx: WorkflowContext) -> None:
            # Extract text from input for demonstration
            input_text = messages[0].text if messages else "no input"
            await ctx.yield_output(f"processed: {input_text}")

        workflow = WorkflowBuilder().set_start_executor(yielding_executor).build()

        # Run directly - should return WorkflowOutputEvent in result
        direct_result = await workflow.run([ChatMessage(role=Role.USER, contents=[TextContent(text="hello")])])
        direct_outputs = direct_result.get_outputs()
        assert len(direct_outputs) == 1
        assert direct_outputs[0] == "processed: hello"

        # Run as agent - yield_output should surface as agent response message
        agent = workflow.as_agent("test-agent")
        agent_result = await agent.run("hello")

        assert isinstance(agent_result, AgentRunResponse)
        assert len(agent_result.messages) == 1
        assert agent_result.messages[0].text == "processed: hello"

    async def test_workflow_as_agent_yield_output_surfaces_in_run_stream(self) -> None:
        """Test that ctx.yield_output() surfaces as AgentRunResponseUpdate when streaming."""

        @executor
        async def yielding_executor(messages: list[ChatMessage], ctx: WorkflowContext) -> None:
            await ctx.yield_output("first output")
            await ctx.yield_output("second output")

        workflow = WorkflowBuilder().set_start_executor(yielding_executor).build()
        agent = workflow.as_agent("test-agent")

        updates: list[AgentRunResponseUpdate] = []
        async for update in agent.run_stream("hello"):
            updates.append(update)

        # Should have received updates for both yield_output calls
        texts = [u.text for u in updates if u.text]
        assert "first output" in texts
        assert "second output" in texts

    async def test_workflow_as_agent_yield_output_with_content_types(self) -> None:
        """Test that yield_output preserves different content types (TextContent, DataContent, etc.)."""

        @executor
        async def content_yielding_executor(messages: list[ChatMessage], ctx: WorkflowContext) -> None:
            # Yield different content types
            await ctx.yield_output(TextContent(text="text content"))
            await ctx.yield_output(DataContent(data=b"binary data", media_type="application/octet-stream"))
            await ctx.yield_output(UriContent(uri="https://example.com/image.png", media_type="image/png"))

        workflow = WorkflowBuilder().set_start_executor(content_yielding_executor).build()
        agent = workflow.as_agent("content-test-agent")

        result = await agent.run("test")

        assert isinstance(result, AgentRunResponse)
        assert len(result.messages) == 3

        # Verify each content type is preserved
        assert isinstance(result.messages[0].contents[0], TextContent)
        assert result.messages[0].contents[0].text == "text content"

        assert isinstance(result.messages[1].contents[0], DataContent)
        assert result.messages[1].contents[0].media_type == "application/octet-stream"

        assert isinstance(result.messages[2].contents[0], UriContent)
        assert result.messages[2].contents[0].uri == "https://example.com/image.png"

    async def test_workflow_as_agent_yield_output_with_chat_message(self) -> None:
        """Test that yield_output with ChatMessage preserves the message structure."""

        @executor
        async def chat_message_executor(messages: list[ChatMessage], ctx: WorkflowContext) -> None:
            msg = ChatMessage(
                role=Role.ASSISTANT,
                contents=[TextContent(text="response text")],
                author_name="custom-author",
            )
            await ctx.yield_output(msg)

        workflow = WorkflowBuilder().set_start_executor(chat_message_executor).build()
        agent = workflow.as_agent("chat-msg-agent")

        result = await agent.run("test")

        assert len(result.messages) == 1
        assert result.messages[0].role == Role.ASSISTANT
        assert result.messages[0].text == "response text"
        assert result.messages[0].author_name == "custom-author"

    async def test_workflow_as_agent_yield_output_sets_raw_representation(self) -> None:
        """Test that yield_output sets raw_representation with the original data."""

        # A custom object to verify raw_representation preserves the original data
        class CustomData:
            def __init__(self, value: int):
                self.value = value

            def __str__(self) -> str:
                return f"CustomData({self.value})"

        @executor
        async def raw_yielding_executor(messages: list[ChatMessage], ctx: WorkflowContext) -> None:
            # Yield different types of data
            await ctx.yield_output("simple string")
            await ctx.yield_output(TextContent(text="text content"))
            custom = CustomData(42)
            await ctx.yield_output(custom)

        workflow = WorkflowBuilder().set_start_executor(raw_yielding_executor).build()
        agent = workflow.as_agent("raw-test-agent")

        updates: list[AgentRunResponseUpdate] = []
        async for update in agent.run_stream("test"):
            updates.append(update)

        # Should have 3 updates
        assert len(updates) == 3

        # Verify raw_representation is set for each update
        assert updates[0].raw_representation == "simple string"
        assert isinstance(updates[1].raw_representation, TextContent)
        assert updates[1].raw_representation.text == "text content"
        assert isinstance(updates[2].raw_representation, CustomData)
        assert updates[2].raw_representation.value == 42

    async def test_thread_conversation_history_included_in_workflow_run(self) -> None:
        """Test that conversation history from thread is included when running WorkflowAgent.

        This verifies that when a thread with existing messages is provided to agent.run(),
        the workflow receives the complete conversation history (thread history + new messages).
        """
        # Create an executor that captures all received messages
        capturing_executor = ConversationHistoryCapturingExecutor(id="capturing")
        workflow = WorkflowBuilder().set_start_executor(capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Thread History Test Agent")

        # Create a thread with existing conversation history
        history_messages = [
            ChatMessage(role=Role.USER, text="Previous user message"),
            ChatMessage(role=Role.ASSISTANT, text="Previous assistant response"),
        ]
        message_store = ChatMessageStore(messages=history_messages)
        thread = AgentThread(message_store=message_store)

        # Run the agent with the thread and a new message
        new_message = "New user question"
        await agent.run(new_message, thread=thread)

        # Verify the executor received both history AND new message
        assert len(capturing_executor.received_messages) == 3

        # Verify the order: history first, then new message
        assert capturing_executor.received_messages[0].text == "Previous user message"
        assert capturing_executor.received_messages[1].text == "Previous assistant response"
        assert capturing_executor.received_messages[2].text == "New user question"

    async def test_thread_conversation_history_included_in_workflow_stream(self) -> None:
        """Test that conversation history from thread is included when streaming WorkflowAgent.

        This verifies that run_stream also includes thread history.
        """
        # Create an executor that captures all received messages
        capturing_executor = ConversationHistoryCapturingExecutor(id="capturing_stream")
        workflow = WorkflowBuilder().set_start_executor(capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Thread Stream Test Agent")

        # Create a thread with existing conversation history
        history_messages = [
            ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
            ChatMessage(role=Role.USER, text="Hello"),
            ChatMessage(role=Role.ASSISTANT, text="Hi there!"),
        ]
        message_store = ChatMessageStore(messages=history_messages)
        thread = AgentThread(message_store=message_store)

        # Stream from the agent with the thread and a new message
        async for _ in agent.run_stream("How are you?", thread=thread):
            pass

        # Verify the executor received all messages (3 from history + 1 new)
        assert len(capturing_executor.received_messages) == 4

        # Verify the order
        assert capturing_executor.received_messages[0].text == "You are a helpful assistant"
        assert capturing_executor.received_messages[1].text == "Hello"
        assert capturing_executor.received_messages[2].text == "Hi there!"
        assert capturing_executor.received_messages[3].text == "How are you?"

    async def test_empty_thread_works_correctly(self) -> None:
        """Test that an empty thread (no message store) works correctly."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="empty_thread_test")
        workflow = WorkflowBuilder().set_start_executor(capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Empty Thread Test Agent")

        # Create an empty thread
        thread = AgentThread()

        # Run with the empty thread
        await agent.run("Just a new message", thread=thread)

        # Should only receive the new message
        assert len(capturing_executor.received_messages) == 1
        assert capturing_executor.received_messages[0].text == "Just a new message"

    async def test_checkpoint_storage_passed_to_workflow(self) -> None:
        """Test that checkpoint_storage parameter is passed through to the workflow."""
        from agent_framework import InMemoryCheckpointStorage

        capturing_executor = ConversationHistoryCapturingExecutor(id="checkpoint_test")
        workflow = WorkflowBuilder().set_start_executor(capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Checkpoint Test Agent")

        # Create checkpoint storage
        checkpoint_storage = InMemoryCheckpointStorage()

        # Run with checkpoint storage enabled
        async for _ in agent.run_stream("Test message", checkpoint_storage=checkpoint_storage):
            pass

        # Drain workflow events to get checkpoint
        # The workflow should have created checkpoints
        checkpoints = await checkpoint_storage.list_checkpoints(workflow.id)
        assert len(checkpoints) > 0, "Checkpoints should have been created when checkpoint_storage is provided"


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
