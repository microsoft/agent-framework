# Copyright (c) Microsoft. All rights reserved.

import uuid
from collections.abc import Awaitable, Sequence
from typing import Any

import pytest
from typing_extensions import Never

from agent_framework import (
    AgentExecutorRequest,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    Content,
    Executor,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
    SupportsAgentRun,
    UsageDetails,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
    response_handler,
)


class SimpleExecutor(Executor):
    """Simple executor that emits a response based on input."""

    def __init__(self, id: str, response_text: str, streaming: bool = False):
        super().__init__(id=id)
        self.response_text = response_text
        self.streaming = streaming

    @handler
    async def handle_message(
        self,
        message: list[Message],
        ctx: WorkflowContext[list[Message], AgentResponseUpdate | AgentResponse],
    ) -> None:
        input_text = message[0].contents[0].text if message and message[0].contents[0].type == "text" else "no input"
        response_text = f"{self.response_text}: {input_text}"

        # Create response message for both streaming and non-streaming cases
        response_message = Message(role="assistant", contents=[Content.from_text(text=response_text)])

        if self.streaming:
            # Emit update event.
            streaming_update = AgentResponseUpdate(
                contents=[Content.from_text(text=response_text)], role="assistant", message_id=str(uuid.uuid4())
            )
            await ctx.yield_output(streaming_update)
        else:
            response = AgentResponse(messages=[response_message])
            await ctx.yield_output(response)

        # Pass message to next executor if any (for both streaming and non-streaming)
        await ctx.send_message([response_message])


class RequestingExecutor(Executor):
    """Executor that requests info."""

    def __init__(self, id: str, streaming: bool = False):
        super().__init__(id=id)
        self.streaming = streaming

    @handler
    async def handle_message(self, _: list[Message], ctx: WorkflowContext) -> None:
        # Send a RequestInfoMessage to trigger the request info process
        await ctx.request_info("Mock request data", str)

    @response_handler
    async def handle_request_response(
        self,
        original_request: str,
        response: str,
        ctx: WorkflowContext[Message, AgentResponseUpdate | AgentResponse],
    ) -> None:
        # Handle the response and emit completion response
        content = Content.from_text(text=f"Request completed with response: {response}")
        if self.streaming:
            await ctx.yield_output(
                AgentResponseUpdate(
                    contents=[content],
                    role="assistant",
                    message_id=str(uuid.uuid4()),
                )
            )
            return

        await ctx.yield_output(
            AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[content],
                    )
                ],
            )
        )


class ConversationHistoryCapturingExecutor(Executor):
    """Executor that captures the received conversation history for verification."""

    def __init__(self, id: str, streaming: bool = False):
        super().__init__(id=id)
        self.received_messages: list[Message] = []
        self.streaming = streaming

    @handler
    async def handle_message(
        self,
        messages: list[Message],
        ctx: WorkflowContext[list[Message], AgentResponseUpdate | AgentResponse],
    ) -> None:
        # Capture all received messages
        self.received_messages = list(messages)

        # Count messages by role for the response
        message_count = len(messages)
        response_text = f"Received {message_count} messages"

        response_message = Message(role="assistant", contents=[Content.from_text(text=response_text)])

        if self.streaming:
            # Emit streaming update
            streaming_update = AgentResponseUpdate(
                contents=[Content.from_text(text=response_text)], role="assistant", message_id=str(uuid.uuid4())
            )
            await ctx.yield_output(streaming_update)
        else:
            response = AgentResponse(messages=[response_message])
            await ctx.yield_output(response)

        await ctx.send_message([response_message])


class TestWorkflowAgent:
    """Test cases for WorkflowAgent end-to-end functionality."""

    async def test_end_to_end_basic_workflow(self):
        """Test basic end-to-end workflow execution with 2 executors emitting AgentResponse."""
        # Create workflow with two executors
        executor1 = SimpleExecutor(id="executor1", response_text="Step1", streaming=False)
        executor2 = SimpleExecutor(id="executor2", response_text="Step2", streaming=False)

        workflow = WorkflowBuilder(start_executor=executor1).add_edge(executor1, executor2).build()

        agent = WorkflowAgent(workflow=workflow, name="Test Agent")

        # Execute workflow end-to-end
        result = await agent.run("Hello World")

        # Verify we got responses from both executors
        assert isinstance(result, AgentResponse)
        assert len(result.messages) >= 2, f"Expected at least 2 messages, got {len(result.messages)}"

        # Find messages from each executor
        step1_messages: list[Message] = []
        step2_messages: list[Message] = []

        for message in result.messages:
            first_content = message.contents[0]
            if first_content.type == "text":
                text = first_content.text
                assert text is not None
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
        assert step1_text is not None
        assert step2_text is not None
        assert "Step1: Hello World" in step1_text
        assert "Step2: Step1: Hello World" in step2_text

    async def test_end_to_end_basic_workflow_streaming(self):
        """Test end-to-end workflow with streaming executor that emits AgentRunStreamingEvent."""
        # Create a single streaming executor
        executor1 = SimpleExecutor(id="stream1", response_text="Streaming1")
        executor2 = SimpleExecutor(id="stream2", response_text="Streaming2")

        # Create workflow with just one executor
        workflow = WorkflowBuilder(start_executor=executor1).add_edge(executor1, executor2).build()

        agent = WorkflowAgent(workflow=workflow, name="Streaming Test Agent")

        # Execute workflow streaming to capture streaming events
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("Test input", stream=True):
            updates.append(update)

        # Should have received at least one streaming update
        assert len(updates) >= 2, f"Expected at least 2 updates, got {len(updates)}"

        # Verify we got a streaming update
        assert updates[0].contents is not None
        first_content: Content = updates[0].contents[0]  # type: ignore[assignment]
        second_content: Content = updates[1].contents[0]  # type: ignore[assignment]
        assert first_content.type == "text"
        assert first_content.text is not None
        assert "Streaming1: Test input" in first_content.text
        assert second_content.type == "text"
        assert second_content.text is not None
        assert "Streaming2: Streaming1: Test input" in second_content.text

    async def test_end_to_end_request_info_handling(self):
        """Test end-to-end workflow with request_info event (type='request_info') handling."""
        # Create workflow with requesting executor -> request info executor (no cycle)
        simple_executor = SimpleExecutor(id="simple", response_text="SimpleResponse", streaming=False)
        requesting_executor = RequestingExecutor(id="requester", streaming=False)

        workflow = (
            WorkflowBuilder(start_executor=simple_executor).add_edge(simple_executor, requesting_executor).build()
        )

        agent = WorkflowAgent(workflow=workflow, name="Request Test Agent")

        # Execute workflow streaming to get request info event
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("Start request", stream=True):
            updates.append(update)
        # Should have received an approval request for the request info
        assert len(updates) > 0

        approval_update: AgentResponseUpdate | None = None
        for update in updates:
            if any(content.type == "function_approval_request" for content in update.contents):
                approval_update = update
                break

        assert approval_update is not None, "Should have received a request_info approval request"

        function_call = next(content for content in approval_update.contents if content.type == "function_call")
        approval_request = next(
            content for content in approval_update.contents if content.type == "function_approval_request"
        )

        # Verify the function call has expected structure
        assert function_call.call_id is not None
        assert function_call.name == "request_info"
        assert isinstance(function_call.arguments, dict)
        assert function_call.arguments.get("request_id") == approval_request.id

        # Approval request should reference the same function call
        assert approval_request.id is not None
        assert approval_request.function_call is not None
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

        approval_response = Content.from_function_approval_response(
            approved=True,
            id=approval_request.id,
            function_call=Content.from_function_call(
                call_id=function_call.call_id,
                name=function_call.name,
                arguments=response_args,
            ),
        )

        response_message = Message(role="user", contents=[approval_response])

        # Continue the workflow with the response
        continuation_result = await agent.run(response_message)

        # Should complete successfully
        assert isinstance(continuation_result, AgentResponse)

        # Verify cleanup - pending requests should be cleared after function response handling
        assert len(agent.pending_requests) == 0

    def test_workflow_as_agent_method(self) -> None:
        """Test that Workflow.as_agent() creates a properly configured WorkflowAgent."""
        # Create a simple workflow
        executor = SimpleExecutor(id="executor1", response_text="Response")
        workflow = WorkflowBuilder(start_executor=executor).build()

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
        workflow = WorkflowBuilder(start_executor=executor).build()

        # Try to create an agent with unsupported input types
        with pytest.raises(ValueError, match="Workflow's start executor cannot handle list\\[Message\\]"):
            workflow.as_agent()

    async def test_workflow_as_agent_yield_output_surfaces_as_agent_response(self) -> None:
        """Test that ctx.yield_output() in a workflow executor surfaces as agent output when using .as_agent().

        This validates the fix for issue #2813: output event (type='output') should be converted to
        AgentResponseUpdate when the workflow is wrapped via .as_agent().
        """

        @executor
        async def yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
            # Extract text from input for demonstration
            input_text = messages[0].text if messages else "no input"
            await ctx.yield_output(f"processed: {input_text}")

        workflow = WorkflowBuilder(start_executor=yielding_executor).build()

        # Run directly - should return output event (type='output') in result
        direct_result = await workflow.run([Message(role="user", text="hello")])
        direct_outputs = direct_result.get_outputs()
        assert len(direct_outputs) == 1
        assert direct_outputs[0] == "processed: hello"

        # Run as agent - yield_output should surface as agent response message
        agent = workflow.as_agent("test-agent")
        agent_result = await agent.run("hello")

        assert isinstance(agent_result, AgentResponse)
        assert len(agent_result.messages) == 1
        assert agent_result.messages[0].text == "processed: hello"

    async def test_workflow_as_agent_yield_output_surfaces_in_run_stream(self) -> None:
        """Test that ctx.yield_output() surfaces as AgentResponseUpdate when streaming."""

        @executor
        async def yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
            await ctx.yield_output("first output")
            await ctx.yield_output("second output")

        workflow = WorkflowBuilder(start_executor=yielding_executor).build()
        agent = workflow.as_agent("test-agent")

        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("hello", stream=True):
            updates.append(update)

        # Should have received updates for both yield_output calls
        texts = [u.text for u in updates if u.text]
        assert "first output" in texts
        assert "second output" in texts

    async def test_workflow_as_agent_yield_output_with_content_types(self) -> None:
        """Test that yield_output preserves different content types (Content, Content, etc.)."""

        @executor
        async def content_yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, Content]) -> None:
            # Yield different content types
            await ctx.yield_output(Content.from_text(text="text content"))
            await ctx.yield_output(Content.from_data(data=b"binary data", media_type="application/octet-stream"))
            await ctx.yield_output(Content.from_uri(uri="https://example.com/image.png", media_type="image/png"))

        workflow = WorkflowBuilder(start_executor=content_yielding_executor).build()
        agent = workflow.as_agent("content-test-agent")

        result = await agent.run("test")

        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 3

        # Verify each content type is preserved
        assert result.messages[0].contents[0].type == "text"
        assert result.messages[0].contents[0].text == "text content"

        assert result.messages[1].contents[0].type == "data"
        assert result.messages[1].contents[0].media_type == "application/octet-stream"

        assert result.messages[2].contents[0].type == "uri"
        assert result.messages[2].contents[0].uri == "https://example.com/image.png"

    async def test_workflow_as_agent_yield_output_with_chat_message(self) -> None:
        """Test that yield_output with Message preserves the message structure."""

        @executor
        async def chat_message_executor(messages: list[Message], ctx: WorkflowContext[Never, Message]) -> None:
            msg = Message(
                role="assistant",
                contents=[Content.from_text(text="response text")],
                author_name="custom-author",
            )
            await ctx.yield_output(msg)

        workflow = WorkflowBuilder(start_executor=chat_message_executor).build()
        agent = workflow.as_agent("chat-msg-agent")

        result = await agent.run("test")

        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
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
        async def raw_yielding_executor(
            messages: list[Message], ctx: WorkflowContext[Never, Content | CustomData | str]
        ) -> None:
            # Yield different types of data
            await ctx.yield_output("simple string")
            await ctx.yield_output(Content.from_text(text="text content"))
            custom = CustomData(42)
            await ctx.yield_output(custom)

        workflow = WorkflowBuilder(start_executor=raw_yielding_executor).build()
        agent = workflow.as_agent("raw-test-agent")

        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("test", stream=True):
            updates.append(update)

        # Should have 3 updates
        assert len(updates) == 3

        # Verify raw_representation is set for each update
        assert updates[0].raw_representation == "simple string"

        assert isinstance(updates[1].raw_representation, Content)
        assert updates[1].raw_representation.type == "text"
        assert updates[1].raw_representation.text == "text content"

        assert isinstance(updates[2].raw_representation, CustomData)
        assert updates[2].raw_representation.value == 42

    async def test_workflow_as_agent_yield_output_with_list_of_chat_messages(self) -> None:
        """Test that yield_output with list[Message] extracts contents from all messages.

        Note: Content items are coalesced by _finalize_response, so multiple text contents
        become a single merged Content in the final response.
        """

        @executor
        async def list_yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, list[Message]]) -> None:
            # Yield a list of Messages (as SequentialBuilder does)
            msg_list = [
                Message(role="user", text="first message"),
                Message(role="assistant", text="second message"),
                Message(
                    role="assistant",
                    contents=[Content.from_text(text="third"), Content.from_text(text="fourth")],
                ),
            ]
            await ctx.yield_output(msg_list)

        workflow = WorkflowBuilder(start_executor=list_yielding_executor).build()
        agent = workflow.as_agent("list-msg-agent")

        # Verify streaming returns the update with all 4 contents before coalescing
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("test", stream=True):
            updates.append(update)

        assert len(updates) == 3
        full_response = AgentResponse.from_updates(updates)
        assert len(full_response.messages) == 3
        texts = [message.text for message in full_response.messages]
        # Note: `from_agent_run_response_updates` coalesces multiple text contents into one content
        assert texts == ["first message", "second message", "thirdfourth"]

        # Verify run()
        result = await agent.run("test")

        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 3
        texts = [message.text for message in result.messages]
        assert texts == ["first message", "second message", "third fourth"]

    async def test_session_conversation_history_included_in_workflow_run(self) -> None:
        """Test that messages provided to agent.run() are passed through to the workflow."""
        # Create an executor that captures all received messages
        capturing_executor = ConversationHistoryCapturingExecutor(id="capturing", streaming=False)
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Session History Test Agent")

        # Create a session
        session = AgentSession()

        # Run the agent with the session and a new message
        new_message = "New user question"
        await agent.run(new_message, session=session)

        # Verify the executor received the message
        assert len(capturing_executor.received_messages) == 1
        assert capturing_executor.received_messages[0].text == "New user question"

    async def test_session_conversation_history_included_in_workflow_stream(self) -> None:
        """Test that messages provided to agent.run() are passed through when streaming WorkflowAgent."""
        # Create an executor that captures all received messages
        capturing_executor = ConversationHistoryCapturingExecutor(id="capturing_stream")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Session Stream Test Agent")

        # Create a session
        session = AgentSession()

        # Stream from the agent with the session and a new message
        async for _ in agent.run("How are you?", stream=True, session=session):
            pass

        # Verify the executor received the message
        assert len(capturing_executor.received_messages) == 1
        assert capturing_executor.received_messages[0].text == "How are you?"

    async def test_empty_session_works_correctly(self) -> None:
        """Test that an empty session (no message store) works correctly."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="empty_session_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Empty Session Test Agent")

        # Create an empty session
        session = AgentSession()

        # Run with the empty session
        await agent.run("Just a new message", session=session)

        # Should only receive the new message
        assert len(capturing_executor.received_messages) == 1
        assert capturing_executor.received_messages[0].text == "Just a new message"

    async def test_workflow_as_agent_adds_default_history_provider(self) -> None:
        """Test that workflow.as_agent() defaults to in-memory history when no providers are configured."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="default_history_provider_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = workflow.as_agent(name="Default History Provider Agent")
        session = AgentSession()

        await agent.run("first message", session=session)
        await agent.run("second message", session=session)

        assert any(isinstance(provider, InMemoryHistoryProvider) for provider in agent.context_providers)
        texts = [message.text for message in capturing_executor.received_messages]
        assert "first message" in texts
        assert "second message" in texts

    async def test_workflow_agent_keeps_explicit_context_providers(self) -> None:
        """Test that WorkflowAgent does not append defaults when context providers are explicitly provided."""
        workflow = WorkflowBuilder(
            start_executor=ConversationHistoryCapturingExecutor(id="explicit_provider_test")
        ).build()
        explicit_provider = InMemoryHistoryProvider("custom-memory")
        agent = WorkflowAgent(
            workflow=workflow,
            name="Explicit Provider Agent",
            context_providers=[explicit_provider],
        )

        assert agent.context_providers == [explicit_provider]

    async def test_checkpoint_storage_passed_to_workflow(self) -> None:
        """Test that checkpoint_storage parameter is passed through to the workflow."""
        from agent_framework import InMemoryCheckpointStorage

        capturing_executor = ConversationHistoryCapturingExecutor(id="checkpoint_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Checkpoint Test Agent")

        # Create checkpoint storage
        checkpoint_storage = InMemoryCheckpointStorage()

        # Run with checkpoint storage enabled
        async for _ in agent.run("Test message", stream=True, checkpoint_storage=checkpoint_storage):
            pass

        # Drain workflow events to get checkpoint
        # The workflow should have created checkpoints
        checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow.name)
        assert len(checkpoints) > 0, "Checkpoints should have been created when checkpoint_storage is provided"

    async def test_agent_executor_output_response_false_filters_streaming_events(self):
        """Test that AgentExecutor with output_response=False does not surface streaming events."""

        class MockAgent(SupportsAgentRun):
            """Mock agent for testing."""

            def __init__(self, name: str, response_text: str) -> None:
                self.id = str(uuid.uuid4())
                self.name = name
                self.description: str | None = None
                self._response_text = response_text

            def create_session(self, **kwargs: Any) -> AgentSession:
                return AgentSession()

            def run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
                *,
                stream: bool = False,
                session: AgentSession | None = None,
                **kwargs: Any,
            ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
                if stream:
                    return self._run_stream(messages=messages, session=session, **kwargs)
                return self._run(messages=messages, session=session, **kwargs)

            async def _run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
                *,
                stream: bool = False,
                session: AgentSession | None = None,
                **kwargs: Any,
            ) -> AgentResponse:

                return AgentResponse(
                    messages=[Message("assistant", [self._response_text])],
                )

            def _run_stream(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
                *,
                session: AgentSession | None = None,
                **kwargs: Any,
            ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
                async def _iter():
                    for word in self._response_text.split():
                        yield AgentResponseUpdate(
                            contents=[Content.from_text(text=word + " ")],
                            role="assistant",
                            author_name=self.name,
                        )

                return ResponseStream(_iter(), finalizer=AgentResponse.from_updates)

        @executor
        async def start_exec(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
            await ctx.yield_output("Start output")
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        agent1 = MockAgent("agent1", "Agent1 output - should NOT appear")
        agent2 = MockAgent("agent2", "Agent2 output - SHOULD appear")

        # Build workflow: start -> agent1 (no output) -> agent2 (output visible)
        workflow = (
            WorkflowBuilder(start_executor=start_exec, output_executors=[start_exec, agent2])
            .add_edge(start_exec, agent1)
            .add_edge(agent1, agent2)
            .build()
        )

        agent = WorkflowAgent(workflow=workflow, name="Test Agent")
        result = await agent.run("Test input")

        # Collect all message texts
        texts = [msg.text for msg in result.messages if msg.text]

        # Start output should appear (from yield_output)
        assert any("Start output" in t for t in texts), "Start output should appear"

        # Agent1 output should NOT appear (output_response=False)
        assert not any("Agent1" in t for t in texts), "Agent1 output should NOT appear"

        # Agent2 output should appear (output_response=True)
        assert any("Agent2" in t for t in texts), "Agent2 output should appear"

    async def test_agent_executor_output_response_no_duplicate_from_workflow_output_event(self):
        """Test that AgentExecutor with output_response=True does not duplicate content."""

        class MockAgent(SupportsAgentRun):
            """Mock agent for testing."""

            def __init__(self, name: str, response_text: str) -> None:
                self.id = str(uuid.uuid4())
                self.name = name
                self.description: str | None = None
                self._response_text = response_text

            def create_session(self, **kwargs: Any) -> AgentSession:
                return AgentSession()

            def run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
                *,
                stream: bool = False,
                session: AgentSession | None = None,
                **kwargs: Any,
            ) -> Awaitable[AgentResponse] | ResponseStream[AgentResponseUpdate, AgentResponse]:
                if stream:
                    return self._run_stream(messages=messages, session=session, **kwargs)
                return self._run(messages=messages, session=session, **kwargs)

            async def _run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
                *,
                stream: bool = False,
                session: AgentSession | None = None,
                **kwargs: Any,
            ) -> AgentResponse:

                return AgentResponse(
                    messages=[Message("assistant", [self._response_text])],
                )

            def _run_stream(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
                *,
                session: AgentSession | None = None,
                **kwargs: Any,
            ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
                async def _iter():
                    for word in self._response_text.split():
                        yield AgentResponseUpdate(
                            contents=[Content.from_text(text=word + " ")],
                            role="assistant",
                            author_name=self.name,
                        )

                return ResponseStream(_iter(), finalizer=AgentResponse.from_updates)

        @executor
        async def start_exec(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        mock_agent = MockAgent("agent", "Unique response text")

        # Build workflow with single agent
        workflow = WorkflowBuilder(start_executor=start_exec).add_edge(start_exec, mock_agent).build()

        agent = WorkflowAgent(workflow=workflow, name="Test Agent")
        result = await agent.run("Test input")

        # Count occurrences of the unique response text
        unique_text_count = sum(1 for msg in result.messages if msg.text and "Unique response text" in msg.text)

        # Should appear exactly once (not duplicated from both streaming and output event)
        assert unique_text_count == 1, f"Response should appear exactly once, but appeared {unique_text_count} times"


class TestWorkflowAgentAuthorName:
    """Test cases for author_name enrichment in WorkflowAgent (GitHub issue #1331)."""

    async def test_agent_response_update_gets_executor_id_as_author_name(self):
        """Test that AgentResponseUpdate gets executor_id as author_name when not already set.

        This validates the fix for GitHub issue #1331: agent responses should include
        identification of which agent produced them in multi-agent workflows.
        """
        # Create workflow with executor that emits AgentResponseUpdate without author_name
        executor1 = SimpleExecutor(id="my_executor_id", response_text="Response", streaming=True)
        workflow = WorkflowBuilder(start_executor=executor1).build()
        agent = WorkflowAgent(workflow=workflow, name="Test Agent")

        # Collect streaming updates
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            updates.append(update)

        # Verify at least one update was received
        assert len(updates) >= 1

        # Verify author_name is set to executor_id
        assert updates[0].author_name == "my_executor_id"

    async def test_agent_response_update_preserves_existing_author_name(self):
        """Test that existing author_name is preserved and not overwritten."""

        class AuthorNameExecutor(Executor):
            """Executor that sets author_name explicitly."""

            @handler
            async def handle_message(
                self,
                message: list[Message],
                ctx: WorkflowContext[list[Message], AgentResponseUpdate],
            ) -> None:
                # Emit update with explicit author_name
                update = AgentResponseUpdate(
                    contents=[Content.from_text(text="Response with author")],
                    role="assistant",
                    author_name="custom_author_name",  # Explicitly set
                    message_id=str(uuid.uuid4()),
                )
                await ctx.yield_output(update)

        executor = AuthorNameExecutor(id="executor_id")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Test Agent")

        # Collect streaming updates
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            updates.append(update)

        # Verify author_name is preserved (not overwritten with executor_id)
        assert len(updates) >= 1
        assert updates[0].author_name == "custom_author_name"

    async def test_multiple_executors_have_distinct_author_names(self):
        """Test that multiple executors in a workflow have their own author_name."""
        # Create workflow with two executors
        executor1 = SimpleExecutor(id="first_executor", response_text="First")
        executor2 = SimpleExecutor(id="second_executor", response_text="Second")

        workflow = WorkflowBuilder(start_executor=executor1).add_edge(executor1, executor2).build()
        agent = WorkflowAgent(workflow=workflow, name="Multi-Executor Agent")

        # Collect streaming updates
        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("Hello", stream=True):
            updates.append(update)

        # Should have updates from both executors
        assert len(updates) >= 2

        # Verify each update has the correct author_name matching its executor
        author_names = [u.author_name for u in updates]
        assert "first_executor" in author_names
        assert "second_executor" in author_names


class TestWorkflowAgentMergeUpdates:
    """Test cases specifically for the WorkflowAgent.merge_updates static method."""

    def test_merge_updates_ordering_by_response_and_message_id(self):
        """Test that merge_updates correctly orders messages by response_id groups and message_id chronologically."""
        # Create updates with different response_ids and message_ids in non-chronological order
        updates = [
            # Response B, Message 2 (latest in resp B)
            AgentResponseUpdate(
                contents=[Content.from_text(text="RespB-Msg2")],
                role="assistant",
                response_id="resp-b",
                message_id="msg-2",
                created_at="2024-01-01T12:02:00Z",
            ),
            # Response A, Message 1 (earliest overall)
            AgentResponseUpdate(
                contents=[Content.from_text(text="RespA-Msg1")],
                role="assistant",
                response_id="resp-a",
                message_id="msg-1",
                created_at="2024-01-01T12:00:00Z",
            ),
            # Response B, Message 1 (earlier in resp B)
            AgentResponseUpdate(
                contents=[Content.from_text(text="RespB-Msg1")],
                role="assistant",
                response_id="resp-b",
                message_id="msg-1",
                created_at="2024-01-01T12:01:00Z",
            ),
            # Response A, Message 2 (later in resp A)
            AgentResponseUpdate(
                contents=[Content.from_text(text="RespA-Msg2")],
                role="assistant",
                response_id="resp-a",
                message_id="msg-2",
                created_at="2024-01-01T12:00:30Z",
            ),
            # Global dangling update (no response_id) - should go at end
            AgentResponseUpdate(
                contents=[Content.from_text(text="Global-Dangling")],
                role="assistant",
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
        message_texts = [msg.contents[0].text if msg.contents[0].type == "text" else "" for msg in result.messages]

        # The exact order depends on dict iteration order for response_ids,
        # but within each response group, chronological order should be maintained
        # and global dangling should be last
        assert "Global-Dangling" in message_texts[-1]  # type: ignore # Global dangling at end

        # Find positions of resp-a and resp-b messages
        resp_a_positions = [i for i, text in enumerate(message_texts) if "RespA" in text]  # type: ignore
        resp_b_positions = [i for i, text in enumerate(message_texts) if "RespB" in text]  # type: ignore

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
            AgentResponseUpdate(
                contents=[
                    Content.from_text(text="First"),
                    Content.from_usage(
                        usage_details={"input_token_count": 10, "output_token_count": 5, "total_token_count": 15}
                    ),
                ],
                role="assistant",
                response_id="resp-1",
                message_id="msg-1",
                created_at="2024-01-01T12:00:00Z",
                additional_properties={"source": "executor1", "priority": "high"},
            ),
            AgentResponseUpdate(
                contents=[
                    Content.from_text(text="Second"),
                    Content.from_usage(
                        usage_details={"input_token_count": 20, "output_token_count": 8, "total_token_count": 28}
                    ),
                ],
                role="assistant",
                response_id="resp-2",
                message_id="msg-2",
                created_at="2024-01-01T12:01:00Z",  # Later timestamp
                additional_properties={"source": "executor2", "category": "analysis"},
            ),
            AgentResponseUpdate(
                contents=[
                    Content.from_text(text="Third"),
                    Content.from_usage(
                        usage_details={"input_token_count": 5, "output_token_count": 3, "total_token_count": 8}
                    ),
                ],
                role="assistant",
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

    def test_merge_updates_function_result_ordering_github_2977(self):
        """Test that FunctionResultContent updates are placed after their FunctionCallContent.

        This test reproduces GitHub issue #2977: When using a session with WorkflowAgent,
        FunctionResultContent updates without response_id were being added to global_dangling
        and placed at the end of messages. This caused OpenAI to reject the conversation because
        "An assistant message with 'tool_calls' must be followed by tool messages responding
        to each 'tool_call_id'."

        The expected ordering should be:
        - User Question
        - FunctionCallContent (assistant)
        - FunctionResultContent (tool)
        - Assistant Answer

        NOT:
        - User Question
        - FunctionCallContent (assistant)
        - Assistant Answer
        - FunctionResultContent (tool)  <-- This was the bug
        """
        call_id = "call_F09je20iUue6DlFRDLLh3dGK"

        updates = [
            # User question
            AgentResponseUpdate(
                contents=[Content.from_text(text="What is the weather?")],
                role="user",
                response_id="resp-1",
                message_id="msg-1",
                created_at="2024-01-01T12:00:00Z",
            ),
            # Assistant with function call
            AgentResponseUpdate(
                contents=[
                    Content.from_function_call(call_id=call_id, name="get_weather", arguments='{"location": "NYC"}')
                ],
                role="assistant",
                response_id="resp-1",
                message_id="msg-2",
                created_at="2024-01-01T12:00:01Z",
            ),
            # Function result: no response_id previously caused this to go to global_dangling
            # and be placed at the end (the bug); fix now correctly associates via call_id
            AgentResponseUpdate(
                contents=[Content.from_function_result(call_id=call_id, result="Sunny, 72F")],
                role="tool",
                response_id=None,
                message_id="msg-3",
                created_at="2024-01-01T12:00:02Z",
            ),
            # Final assistant answer
            AgentResponseUpdate(
                contents=[Content.from_text(text="The weather in NYC is sunny and 72F.")],
                role="assistant",
                response_id="resp-1",
                message_id="msg-4",
                created_at="2024-01-01T12:00:03Z",
            ),
        ]

        result = WorkflowAgent.merge_updates(updates, "final-response")

        assert len(result.messages) == 4

        # Extract content types for verification
        content_sequence: list[tuple[str, str]] = []
        for msg in result.messages:
            for content in msg.contents:
                if content.type == "text":
                    content_sequence.append(("text", msg.role))
                elif content.type == "function_call":
                    content_sequence.append(("function_call", msg.role))
                elif content.type == "function_result":
                    content_sequence.append(("function_result", msg.role))

        # Verify correct ordering: user -> function_call -> function_result -> assistant_answer
        expected_sequence = [
            ("text", "user"),
            ("function_call", "assistant"),
            ("function_result", "tool"),
            ("text", "assistant"),
        ]

        # Compare using role.value for Role enum
        actual_sequence_normalized = [(t, r.value if hasattr(r, "value") else r) for t, r in content_sequence]

        assert actual_sequence_normalized == expected_sequence, (
            f"FunctionResultContent should come immediately after FunctionCallContent. "
            f"Got: {content_sequence}, Expected: {expected_sequence}"
        )

        # Additional check: verify FunctionResultContent call_id matches FunctionCallContent
        function_call_idx = None
        function_result_idx = None
        for i, msg in enumerate(result.messages):
            for content in msg.contents:
                if content.type == "function_call":
                    function_call_idx = i
                    assert content.call_id == call_id
                elif content.type == "function_result":
                    function_result_idx = i
                    assert content.call_id == call_id

        assert function_call_idx is not None
        assert function_result_idx is not None
        assert function_result_idx == function_call_idx + 1, (
            f"FunctionResultContent at index {function_result_idx} should immediately follow "
            f"FunctionCallContent at index {function_call_idx}"
        )

    def test_merge_updates_multiple_function_results_ordering_github_2977(self):
        """Test ordering with multiple FunctionCallContent/FunctionResultContent pairs.

        Validates that multiple tool calls and results appear before the final assistant
        answer, even when results arrive without response_id and in different order than calls.

        OpenAI requires that tool results appear after their calls and before the next
        assistant text message, but doesn't require strict interleaving (result_1 immediately
        after call_1). The key constraint is: calls -> results -> final_answer.
        """
        call_id_1 = "call_weather_001"
        call_id_2 = "call_time_002"

        updates = [
            # User question
            AgentResponseUpdate(
                contents=[Content.from_text(text="What's the weather and time?")],
                role="user",
                response_id="resp-1",
                message_id="msg-1",
                created_at="2024-01-01T12:00:00Z",
            ),
            # Assistant with first function call
            AgentResponseUpdate(
                contents=[
                    Content.from_function_call(call_id=call_id_1, name="get_weather", arguments='{"location": "NYC"}')
                ],
                role="assistant",
                response_id="resp-1",
                message_id="msg-2",
                created_at="2024-01-01T12:00:01Z",
            ),
            # Assistant with second function call
            AgentResponseUpdate(
                contents=[
                    Content.from_function_call(call_id=call_id_2, name="get_time", arguments='{"timezone": "EST"}')
                ],
                role="assistant",
                response_id="resp-1",
                message_id="msg-3",
                created_at="2024-01-01T12:00:02Z",
            ),
            # Second function result arrives first (no response_id)
            AgentResponseUpdate(
                contents=[Content.from_function_result(call_id=call_id_2, result="3:00 PM EST")],
                role="tool",
                response_id=None,
                message_id="msg-4",
                created_at="2024-01-01T12:00:03Z",
            ),
            # First function result arrives second (no response_id)
            AgentResponseUpdate(
                contents=[Content.from_function_result(call_id=call_id_1, result="Sunny, 72F")],
                role="tool",
                response_id=None,
                message_id="msg-5",
                created_at="2024-01-01T12:00:04Z",
            ),
            # Final assistant answer
            AgentResponseUpdate(
                contents=[Content.from_text(text="It's sunny (72F) and 3 PM in NYC.")],
                role="assistant",
                response_id="resp-1",
                message_id="msg-6",
                created_at="2024-01-01T12:00:05Z",
            ),
        ]

        result = WorkflowAgent.merge_updates(updates, "final-response")

        assert len(result.messages) == 6

        # Build a sequence of (content_type, call_id_if_applicable)
        content_sequence: list[tuple[str, str | None]] = []
        for msg in result.messages:
            for content in msg.contents:
                if content.type == "text":
                    content_sequence.append(("text", None))
                elif content.type == "function_call":
                    content_sequence.append(("function_call", content.call_id))
                elif content.type == "function_result":
                    content_sequence.append(("function_result", content.call_id))

        # Verify all function results appear before the final assistant text
        # Find indices
        call_indices = [i for i, (t, _) in enumerate(content_sequence) if t == "function_call"]
        result_indices = [i for i, (t, _) in enumerate(content_sequence) if t == "function_result"]
        final_text_idx = len(content_sequence) - 1  # Last item should be final text

        # All calls should have corresponding results
        call_ids_in_calls = {content_sequence[i][1] for i in call_indices}
        call_ids_in_results = {content_sequence[i][1] for i in result_indices}
        assert call_ids_in_calls == call_ids_in_results, "All function calls should have matching results"

        # All results should appear after all calls and before final text
        assert all(r > max(call_indices) for r in result_indices), (
            "All function results should appear after all function calls"
        )
        assert all(r < final_text_idx for r in result_indices), (
            "All function results should appear before the final assistant answer"
        )
        assert content_sequence[final_text_idx] == ("text", None), "Final message should be assistant text"

    def test_merge_updates_function_result_no_matching_call(self):
        """Test that FunctionResultContent without matching FunctionCallContent still appears.

        If a FunctionResultContent has a call_id that doesn't match any FunctionCallContent
        in the messages, it should be appended at the end (fallback behavior).
        """
        updates = [
            AgentResponseUpdate(
                contents=[Content.from_text(text="Hello")],
                role="user",
                response_id="resp-1",
                message_id="msg-1",
                created_at="2024-01-01T12:00:00Z",
            ),
            # Function result with no matching call
            AgentResponseUpdate(
                contents=[Content.from_function_result(call_id="orphan_call_id", result="orphan result")],
                role="tool",
                response_id=None,
                message_id="msg-2",
                created_at="2024-01-01T12:00:01Z",
            ),
            AgentResponseUpdate(
                contents=[Content.from_text(text="Goodbye")],
                role="assistant",
                response_id="resp-1",
                message_id="msg-3",
                created_at="2024-01-01T12:00:02Z",
            ),
        ]

        result = WorkflowAgent.merge_updates(updates, "final-response")

        assert len(result.messages) == 3

        # Orphan function result should be at the end since it can't be matched
        content_types: list[str] = []
        for msg in result.messages:
            for content in msg.contents:
                if content.type == "text":
                    content_types.append("text")
                elif content.type == "function_result":
                    content_types.append("function_result")

        # Order: text (user), text (assistant), function_result (orphan at end)
        assert content_types == ["text", "text", "function_result"]
