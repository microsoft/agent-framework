# Copyright (c) Microsoft. All rights reserved.

import uuid
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, overload

import pytest
from typing_extensions import Never

from agent_framework import (
    AgentExecutorRequest,
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    Content,
    Executor,
    HistoryProvider,
    InMemoryHistoryProvider,
    Message,
    ResponseStream,
    ServiceSessionId,
    SupportsAgentRun,
    UsageDetails,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    executor,
    handler,
    response_handler,
)
from agent_framework._workflows._typing_utils import deserialize_type


@dataclass
class HandoffRequest:
    """Module-level dataclass used by request_info tests.

    Defined at module scope (not nested inside a test method) so
    ``serialize_type``/``deserialize_type`` can round-trip the request_type via
    the importable qualified name ``tests.workflow.test_workflow_agent.HandoffRequest``.
    """

    target_agent: str
    reason: str


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

        request_update: AgentResponseUpdate | None = None
        for update in updates:
            if any(content.type == "function_call" for content in update.contents):
                request_update = update
                break

        assert request_update is not None, "Should have received a request_info wrapped in a function_call content"

        request_function_call = next(content for content in request_update.contents if content.type == "function_call")
        assert request_function_call.call_id is not None

        # Verify the function call has expected structure
        assert request_function_call.name == WorkflowAgent.REQUEST_INFO_FUNCTION_NAME
        assert isinstance(request_function_call.arguments, dict)
        assert request_function_call.arguments.get("request_id") is not None
        assert request_function_call.arguments.get("request_event") is not None
        request_event = request_function_call.arguments["request_event"]
        assert request_event.get("type") == "request_info"
        assert deserialize_type(request_event.get("response_type")) is str

        deserialized_args = WorkflowAgent.RequestInfoFunctionArgs.from_dict(request_function_call.arguments)  # ty: ignore[invalid-argument-type]
        assert deserialized_args.request_id == request_function_call.call_id
        assert isinstance(deserialized_args.request_event, WorkflowEvent)
        assert deserialized_args.request_event.type == "request_info"
        assert deserialized_args.request_event.data == "Mock request data"
        assert deserialized_args.request_event.response_type is str

        # Verify the request is tracked in pending_requests
        pending_requests = await workflow._runner_context.get_pending_request_info_events()
        assert len(pending_requests) == 1
        assert request_function_call.call_id in pending_requests

        # Now provide a function result response with updated arguments to test continuation
        function_result = Content.from_function_result(
            call_id=request_function_call.call_id,
            result="Mock response to request info",
        )

        response_message = Message(role="user", contents=[function_result])

        # Continue the workflow with the response
        continuation_result = await agent.run(response_message)

        # Should complete successfully
        assert isinstance(continuation_result, AgentResponse)

        # Verify cleanup - pending requests should be cleared after function response handling
        pending_requests = await workflow._runner_context.get_pending_request_info_events()
        assert len(pending_requests) == 0

    def test_request_info_dataclass_arguments_are_serialized_when_content_is_created(self) -> None:
        """Test WorkflowAgent prepares request_info arguments before observability captures messages."""
        executor = SimpleExecutor(id="executor1", response_text="Response")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Request Test Agent")
        event = WorkflowEvent.request_info(
            request_id="request_123",
            source_executor_id="executor1",
            request_data=HandoffRequest(target_agent="helper", reason="overflow"),
            response_type=str,
        )

        request_function_call = agent._process_request_info_event(event)  # pyright: ignore[reportPrivateUsage]

        assert request_function_call.call_id == "request_123"
        assert isinstance(request_function_call.arguments, dict)
        assert request_function_call.arguments.get("request_event") is not None
        request_event = request_function_call.arguments["request_event"]
        assert request_event.get("type") == "request_info"
        assert request_event.get("request_id") == "request_123"
        assert request_event.get("source_executor_id") == "executor1"
        assert deserialize_type(request_event.get("response_type")) is str
        assert request_event.get("data") == HandoffRequest(target_agent="helper", reason="overflow")

        deserialized_args = WorkflowAgent.RequestInfoFunctionArgs.from_dict(request_function_call.arguments)  # ty: ignore[invalid-argument-type]
        assert deserialized_args.request_id == "request_123"
        assert isinstance(deserialized_args.request_event, WorkflowEvent)
        assert deserialized_args.request_event.type == "request_info"
        assert deserialized_args.request_event.data == HandoffRequest(target_agent="helper", reason="overflow")
        assert deserialized_args.request_event.response_type is str

    def test_process_request_info_event_passes_through_function_approval_request(self) -> None:
        """If the event data is already a function approval request, it is forwarded unchanged.

        Tool-approval requests emitted by an inner agent surface as ``Content``
        objects with ``user_input_request=True``. ``WorkflowAgent`` must not
        re-wrap these inside a synthesized ``request_info`` function call;
        instead it should return the original content as-is so callers can
        respond with a matching ``function_approval_response``.
        """
        executor = SimpleExecutor(id="executor1", response_text="Response")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Passthrough Agent")

        approval_id = "approval-passthrough-1"
        inner_function_call = Content.from_function_call(
            call_id="tool-call-1",
            name="delete_file",
            arguments={"path": "/tmp/x"},
        )
        approval_request = Content.from_function_approval_request(
            id=approval_id,
            function_call=inner_function_call,
        )
        event = WorkflowEvent.request_info(
            request_id=approval_id,
            source_executor_id="executor1",
            request_data=approval_request,
            response_type=Content,
        )

        result = agent._process_request_info_event(event)  # pyright: ignore[reportPrivateUsage]

        # The original FunctionApprovalRequestContent is returned as-is — same
        # instance, with the original tool name preserved (NOT replaced by the
        # synthesized REQUEST_INFO_FUNCTION_NAME).
        assert result is approval_request
        assert result.type == "function_approval_request"
        assert result.id == approval_id
        assert result.user_input_request is True
        assert result.function_call is inner_function_call  # type: ignore[attr-defined]
        assert result.function_call.name == "delete_file"  # type: ignore[attr-defined]
        assert result.function_call.name != WorkflowAgent.REQUEST_INFO_FUNCTION_NAME  # type: ignore[attr-defined]

    def test_extract_function_responses_passes_through_approval_response_approved(self) -> None:
        """A function_approval_response with approved=True is keyed by content.id and forwarded as-is.

        After the refactor, ``WorkflowAgent`` no longer unwraps a synthesized
        ``request_info`` function call from approval responses — the response
        content is routed straight back to the workflow under its own ``id``,
        which matches the pending request id surfaced by
        ``_process_request_info_event``.
        """
        executor = SimpleExecutor(id="executor1", response_text="Response")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Response Agent")

        approval_id = "approval-response-approved-1"
        inner_function_call = Content.from_function_call(
            call_id="tool-call-1",
            name="delete_file",
            arguments={"path": "/tmp/x"},
        )
        approval_request = Content.from_function_approval_request(
            id=approval_id,
            function_call=inner_function_call,
        )
        approval_response = approval_request.to_function_approval_response(approved=True)  # type: ignore[attr-defined]
        message = Message(role="user", contents=[approval_response])

        responses = agent._extract_function_responses([message])  # pyright: ignore[reportPrivateUsage]

        assert set(responses.keys()) == {approval_id}
        assert responses[approval_id] is approval_response
        assert responses[approval_id].approved is True  # type: ignore[attr-defined]

    def test_extract_function_responses_passes_through_approval_response_denied(self) -> None:
        """A function_approval_response with approved=False is forwarded the same way as an approval.

        Only the ``approved`` flag changes — routing back to the workflow is
        identical for accept and reject paths.
        """
        executor = SimpleExecutor(id="executor1", response_text="Response")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Response Agent")

        approval_id = "approval-response-denied-1"
        inner_function_call = Content.from_function_call(
            call_id="tool-call-2",
            name="send_email",
            arguments={"to": "alice@example.com"},
        )
        approval_request = Content.from_function_approval_request(
            id=approval_id,
            function_call=inner_function_call,
        )
        approval_response = approval_request.to_function_approval_response(approved=False)  # type: ignore[attr-defined]
        message = Message(role="user", contents=[approval_response])

        responses = agent._extract_function_responses([message])  # pyright: ignore[reportPrivateUsage]

        assert set(responses.keys()) == {approval_id}
        assert responses[approval_id] is approval_response
        assert responses[approval_id].approved is False  # type: ignore[attr-defined]

    async def test_function_approval_request_flows_end_to_end_approved(self) -> None:
        """End-to-end: an executor emits a function_approval_request, the agent
        forwards it unchanged, and an ``approved=True`` response resumes the workflow.

        This exercises the full pass-through path:
        ``ctx.request_info(approval_content, ...)`` -> ``WorkflowAgent`` surfaces
        the original ``FunctionApprovalRequestContent`` -> caller responds with a
        ``FunctionApprovalResponseContent`` -> ``WorkflowAgent`` routes it back
        to the workflow which delivers it to the executor's ``@response_handler``.
        """
        approval_id = "e2e-approval-1"
        inner_function_call = Content.from_function_call(
            call_id="tool-call-e2e-1",
            name="delete_file",
            arguments={"path": "/tmp/x"},
        )
        approval_request = Content.from_function_approval_request(
            id=approval_id,
            function_call=inner_function_call,
        )

        class ApprovalRequestingExecutor(Executor):
            @handler
            async def handle_message(self, _: list[Message], ctx: WorkflowContext) -> None:
                await ctx.request_info(approval_request, Content, request_id=approval_id)

            @response_handler
            async def handle_response(
                self,
                original_request: Content,
                response: Content,
                ctx: WorkflowContext[Never, AgentResponse],  # type: ignore[valid-type]
            ) -> None:
                assert response.type == "function_approval_response"
                assert response.id == approval_id  # type: ignore[attr-defined]
                approved = bool(response.approved)  # type: ignore[attr-defined]
                tool_name = original_request.function_call.name  # type: ignore[attr-defined, union-attr]  # ty: ignore[unresolved-attribute]
                await ctx.yield_output(
                    AgentResponse(
                        messages=[
                            Message(
                                role="assistant",
                                contents=[Content.from_text(text=f"{tool_name} approved={approved}")],
                            )
                        ]
                    )
                )

        executor = ApprovalRequestingExecutor(id="approval_requester")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="E2E Approval Agent")

        # First run: workflow pauses with the approval request.
        first = await agent.run("please delete it")
        assert isinstance(first, AgentResponse)

        forwarded = next(
            (
                c
                for m in first.messages
                for c in m.contents
                if c.type == "function_approval_request" and c.id == approval_id
            ),
            None,
        )
        assert forwarded is approval_request, "Approval request must surface unchanged"

        pending = await workflow._runner_context.get_pending_request_info_events()
        assert approval_id in pending

        # Respond with approved=True.
        approval_response = approval_request.to_function_approval_response(approved=True)  # type: ignore[attr-defined]
        final = await agent.run(Message(role="user", contents=[approval_response]))

        assert isinstance(final, AgentResponse)
        final_text = " ".join(m.text or "" for m in final.messages)
        assert "delete_file approved=True" in final_text

        pending = await workflow._runner_context.get_pending_request_info_events()
        assert approval_id not in pending

    async def test_function_approval_request_flows_end_to_end_denied(self) -> None:
        """End-to-end denied path: ``approved=False`` is delivered to the executor's
        response handler so the workflow can branch on the rejection."""
        approval_id = "e2e-approval-deny-1"
        inner_function_call = Content.from_function_call(
            call_id="tool-call-e2e-deny-1",
            name="send_email",
            arguments={"to": "alice@example.com"},
        )
        approval_request = Content.from_function_approval_request(
            id=approval_id,
            function_call=inner_function_call,
        )

        class ApprovalRequestingExecutor(Executor):
            @handler
            async def handle_message(self, _: list[Message], ctx: WorkflowContext) -> None:
                await ctx.request_info(approval_request, Content, request_id=approval_id)

            @response_handler
            async def handle_response(
                self,
                original_request: Content,
                response: Content,
                ctx: WorkflowContext[Never, AgentResponse],  # type: ignore[valid-type]
            ) -> None:
                assert response.type == "function_approval_response"
                assert response.id == approval_id  # type: ignore[attr-defined]
                approved = bool(response.approved)  # type: ignore[attr-defined]
                tool_name = original_request.function_call.name  # type: ignore[attr-defined, union-attr]  # ty: ignore[unresolved-attribute]
                await ctx.yield_output(
                    AgentResponse(
                        messages=[
                            Message(
                                role="assistant",
                                contents=[Content.from_text(text=f"{tool_name} approved={approved}")],
                            )
                        ]
                    )
                )

        executor = ApprovalRequestingExecutor(id="approval_requester_deny")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="E2E Approval Deny Agent")

        first = await agent.run("please send")
        assert isinstance(first, AgentResponse)
        forwarded = next(
            (
                c
                for m in first.messages
                for c in m.contents
                if c.type == "function_approval_request" and c.id == approval_id
            ),
            None,
        )
        assert forwarded is approval_request

        # Respond with approved=False.
        approval_response = approval_request.to_function_approval_response(approved=False)  # type: ignore[attr-defined]
        final = await agent.run(Message(role="user", contents=[approval_response]))

        assert isinstance(final, AgentResponse)
        final_text = " ".join(m.text or "" for m in final.messages)
        assert "send_email approved=False" in final_text

        pending = await workflow._runner_context.get_pending_request_info_events()
        assert approval_id not in pending

    async def test_request_info_non_approval_flows_end_to_end(self) -> None:
        """End-to-end: when request data is not a function approval content, the
        agent surfaces a synthesized ``function_call`` (name=REQUEST_INFO_FUNCTION_NAME)
        and routes a matching ``function_result`` back to the executor.
        """
        captured: dict[str, Any] = {}

        class HandoffRequestingExecutor(Executor):
            @handler
            async def handle_message(self, _: list[Message], ctx: WorkflowContext) -> None:
                await ctx.request_info(
                    HandoffRequest(target_agent="helper", reason="overflow"),
                    str,
                )

            @response_handler
            async def handle_response(
                self,
                original_request: HandoffRequest,
                response: str,
                ctx: WorkflowContext[Never, AgentResponse],  # type: ignore[valid-type]
            ) -> None:
                captured["original"] = original_request
                captured["response"] = response
                await ctx.yield_output(
                    AgentResponse(
                        messages=[
                            Message(
                                role="assistant",
                                contents=[
                                    Content.from_text(text=f"handoff to {original_request.target_agent}: {response}")
                                ],
                            )
                        ]
                    )
                )

        executor = HandoffRequestingExecutor(id="handoff_requester")
        workflow = WorkflowBuilder(start_executor=executor).build()
        agent = WorkflowAgent(workflow=workflow, name="E2E Handoff Agent")

        # First run: workflow pauses with a synthesized request_info function_call.
        first = await agent.run("start handoff")
        assert isinstance(first, AgentResponse)

        function_call = next(
            (
                c
                for m in first.messages
                for c in m.contents
                if c.type == "function_call" and c.name == WorkflowAgent.REQUEST_INFO_FUNCTION_NAME
            ),
            None,
        )
        assert function_call is not None, "Expected a synthesized request_info function_call"
        assert function_call.call_id is not None
        assert isinstance(function_call.arguments, dict)
        request_id = function_call.arguments["request_id"]
        assert function_call.call_id == request_id
        request_payload = function_call.arguments["request_event"]
        assert request_payload.get("type") == "request_info"
        assert request_payload.get("data") == HandoffRequest(target_agent="helper", reason="overflow")

        deserialized_args = WorkflowAgent.RequestInfoFunctionArgs.from_dict(function_call.arguments)  # ty: ignore[invalid-argument-type]
        assert deserialized_args.request_id == request_id
        assert isinstance(deserialized_args.request_event, WorkflowEvent)
        assert deserialized_args.request_event.type == "request_info"
        assert deserialized_args.request_event.data == HandoffRequest(target_agent="helper", reason="overflow")
        assert deserialized_args.request_event.response_type is str

        pending = await workflow._runner_context.get_pending_request_info_events()
        assert request_id in pending

        # Respond with a function_result keyed by the call_id.
        function_result = Content.from_function_result(call_id=request_id, result="ok-do-it")
        final = await agent.run(Message(role="user", contents=[function_result]))

        assert isinstance(final, AgentResponse)
        final_text = " ".join(m.text or "" for m in final.messages)
        assert "handoff to helper: ok-do-it" in final_text

        # The executor's response handler received the original request and the response.
        assert isinstance(captured.get("original"), HandoffRequest)
        assert captured["original"].target_agent == "helper"
        assert captured["response"] == "ok-do-it"

        pending = await workflow._runner_context.get_pending_request_info_events()
        assert request_id not in pending

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

    def test_workflow_as_agent_with_description_and_context_providers(self) -> None:
        """Test that Workflow.as_agent() forwards description and context_providers."""
        executor = SimpleExecutor(id="executor1", response_text="Response")
        workflow = WorkflowBuilder(start_executor=executor).build()

        history_provider = InMemoryHistoryProvider()
        agent = workflow.as_agent(
            name="MyAgent",
            description="A test agent",
            context_providers=[history_provider],
        )

        assert isinstance(agent, WorkflowAgent)
        assert agent.name == "MyAgent"
        assert agent.description == "A test agent"
        assert history_provider in agent.context_providers

    def test_workflow_as_agent_defaults_name_and_description_from_workflow(self) -> None:
        """Test that as_agent() defaults name and description to the workflow's own values."""
        executor = SimpleExecutor(id="executor1", response_text="Response")
        workflow = WorkflowBuilder(
            start_executor=executor,
            name="my-workflow",
            description="Workflow description",
        ).build()

        agent = workflow.as_agent()

        assert agent.name == "my-workflow"
        assert agent.description == "Workflow description"

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
        async def yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
            # Extract text from input for demonstration
            input_text = messages[0].text if messages else "no input"
            await ctx.yield_output(f"processed: {input_text}")

        workflow = WorkflowBuilder(start_executor=yielding_executor).build()

        # Run directly - should return output event (type='output') in result
        direct_result = await workflow.run([Message(role="user", contents=["hello"])])
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
        async def yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:  # type: ignore[valid-type]
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
        async def content_yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, Content]) -> None:  # type: ignore[valid-type]
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
        async def chat_message_executor(messages: list[Message], ctx: WorkflowContext[Never, Message]) -> None:  # type: ignore[valid-type]
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
            messages: list[Message],
            ctx: WorkflowContext[Never, Content | CustomData | str],  # type: ignore[valid-type]
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
        async def list_yielding_executor(messages: list[Message], ctx: WorkflowContext[Never, list[Message]]) -> None:  # type: ignore[valid-type]
            # Yield a list of Messages (as SequentialBuilder does)
            msg_list = [
                Message(role="user", contents=["first message"]),
                Message(role="assistant", contents=["second message"]),
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

    async def test_multi_turn_session_stores_responses(self) -> None:
        """Test that WorkflowAgent stores response messages in session history (issue #1694).

        Previously, session_context._response was not set before running after_run
        providers, so InMemoryHistoryProvider never persisted response messages.
        On subsequent runs the workflow only received prior user inputs, not prior
        assistant responses, breaking multi-turn conversations.
        """
        capturing_executor = ConversationHistoryCapturingExecutor(id="multi_turn_test", streaming=False)
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = workflow.as_agent(name="Multi Turn Agent")
        session = AgentSession()

        # First turn
        await agent.run("My name is Bob", session=session)

        # Second turn — the executor should see prior user+assistant messages plus new input
        await agent.run("What is my name?", session=session)

        received = capturing_executor.received_messages
        roles = [m.role for m in received]
        texts = [m.text for m in received]

        # History should include: user("My name is Bob"), assistant(response), user("What is my name?")
        assert len(received) == 3, f"Expected 3 messages (user, assistant, user), got {len(received)}: {roles}"
        assert roles[0] == "user"
        assert "My name is Bob" in (texts[0] or "")
        assert roles[1] == "assistant"
        assert roles[2] == "user"
        assert "What is my name?" in (texts[2] or "")

    async def test_multi_turn_session_stores_responses_streaming(self) -> None:
        """Streaming variant: WorkflowAgent stores response messages in session history."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="multi_turn_stream_test", streaming=True)
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = workflow.as_agent(name="Multi Turn Stream Agent")
        session = AgentSession()

        # First turn (streaming)
        stream = agent.run("Hello", stream=True, session=session)
        async for _ in stream:
            pass
        await stream.get_final_response()

        # Second turn — should include prior history
        stream2 = agent.run("Follow up", stream=True, session=session)
        async for _ in stream2:
            pass
        await stream2.get_final_response()

        received = capturing_executor.received_messages
        roles = [m.role for m in received]

        assert len(received) == 3, f"Expected 3 messages, got {len(received)}: {roles}"
        assert roles[0] == "user"
        assert roles[1] == "assistant"
        assert roles[2] == "user"

    async def test_multi_turn_session_roundtrip_serialization(self) -> None:
        """Test that session can be serialized/deserialized and multi-turn still works."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="roundtrip_test", streaming=False)
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = workflow.as_agent(name="Roundtrip Agent")
        session = AgentSession()

        # First turn
        await agent.run("My name is Bob", session=session)

        # Serialize and deserialize the session
        serialized = session.to_dict()
        restored_session = AgentSession.from_dict(serialized)

        # Second turn with restored session
        await agent.run("What is my name?", session=restored_session)

        received = capturing_executor.received_messages
        roles = [m.role for m in received]
        texts = [m.text for m in received]

        assert len(received) == 3, f"Expected 3 messages, got {len(received)}: {roles}"
        assert roles[0] == "user"
        assert "My name is Bob" in (texts[0] or "")
        assert roles[1] == "assistant"
        assert roles[2] == "user"
        assert "What is my name?" in (texts[2] or "")

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

    async def test_no_history_provider_injected_when_session_is_none(self) -> None:
        """Test that InMemoryHistoryProvider is NOT injected when session is None."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="no_session_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="No Session Agent")

        await agent.run("hello")

        assert not any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)

    async def test_no_history_provider_injected_when_session_is_none_streaming(self) -> None:
        """Test that InMemoryHistoryProvider is NOT injected when session is None (streaming)."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="no_session_stream_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="No Session Stream Agent")

        async for _ in agent.run("hello", stream=True):
            pass

        assert not any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)

    async def test_no_injection_when_history_provider_with_load_messages_exists(self) -> None:
        """Test that no InMemoryHistoryProvider is injected when an existing HistoryProvider has load_messages=True."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="existing_provider_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        existing_provider = InMemoryHistoryProvider("custom", load_messages=True)
        agent = WorkflowAgent(
            workflow=workflow,
            name="Existing Provider Agent",
            context_providers=[existing_provider],
        )
        session = AgentSession()

        await agent.run("hello", session=session)

        # Should still have only the original provider
        history_providers = [p for p in agent.context_providers if isinstance(p, HistoryProvider)]
        assert len(history_providers) == 1
        assert history_providers[0] is existing_provider

    async def test_injection_when_history_provider_with_load_messages_false(self) -> None:
        """Test that InMemoryHistoryProvider IS injected when existing HistoryProvider has load_messages=False."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="no_load_provider_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        audit_provider = InMemoryHistoryProvider("audit", load_messages=False)
        agent = WorkflowAgent(
            workflow=workflow,
            name="Audit Provider Agent",
            context_providers=[audit_provider],
        )
        session = AgentSession()

        await agent.run("hello", session=session)

        # Should have injected an additional InMemoryHistoryProvider with load_messages=True
        history_providers = [p for p in agent.context_providers if isinstance(p, HistoryProvider)]
        assert len(history_providers) == 2
        loading_providers = [p for p in history_providers if p.load_messages]
        assert len(loading_providers) == 1
        assert isinstance(loading_providers[0], InMemoryHistoryProvider)

    async def test_no_duplicate_injection_on_multiple_runs(self) -> None:
        """Test that calling run() multiple times does not keep adding InMemoryHistoryProvider."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="no_dup_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="No Dup Agent")
        session = AgentSession()

        await agent.run("first", session=session)
        await agent.run("second", session=session)
        await agent.run("third", session=session)

        history_providers = [p for p in agent.context_providers if isinstance(p, InMemoryHistoryProvider)]
        assert len(history_providers) == 1

    async def test_no_duplicate_injection_on_multiple_runs_streaming(self) -> None:
        """Test that calling run(stream=True) multiple times does not keep adding InMemoryHistoryProvider."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="no_dup_stream_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="No Dup Stream Agent")
        session = AgentSession()

        async for _ in agent.run("first", stream=True, session=session):
            pass
        async for _ in agent.run("second", stream=True, session=session):
            pass
        async for _ in agent.run("third", stream=True, session=session):
            pass

        history_providers = [p for p in agent.context_providers if isinstance(p, InMemoryHistoryProvider)]
        assert len(history_providers) == 1

    async def test_injection_with_session_in_streaming_mode(self) -> None:
        """Test that InMemoryHistoryProvider is injected when session is provided in streaming mode."""
        capturing_executor = ConversationHistoryCapturingExecutor(id="stream_inject_test")
        workflow = WorkflowBuilder(start_executor=capturing_executor).build()
        agent = WorkflowAgent(workflow=workflow, name="Stream Inject Agent")
        session = AgentSession()

        async for _ in agent.run("hello", stream=True, session=session):
            pass

        assert any(isinstance(p, InMemoryHistoryProvider) for p in agent.context_providers)

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

            def get_session(self, *, service_session_id: str | ServiceSessionId, **kwargs: Any) -> AgentSession:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
                return AgentSession()

            @overload
            def run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
                *,
                stream: Literal[False] = ...,
                session: AgentSession | None = ...,
                **kwargs: Any,
            ) -> Awaitable[AgentResponse[Any]]: ...
            @overload
            def run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
                *,
                stream: Literal[True],
                session: AgentSession | None = ...,
                **kwargs: Any,
            ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

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
            WorkflowBuilder(start_executor=start_exec, output_from=[start_exec, agent2])
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

            def get_session(self, *, service_session_id: str | ServiceSessionId, **kwargs: Any) -> AgentSession:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
                return AgentSession()

            @overload
            def run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
                *,
                stream: Literal[False] = ...,
                session: AgentSession | None = ...,
                **kwargs: Any,
            ) -> Awaitable[AgentResponse[Any]]: ...
            @overload
            def run(
                self,
                messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
                *,
                stream: Literal[True],
                session: AgentSession | None = ...,
                **kwargs: Any,
            ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

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
        actual_sequence_normalized = [(t, r.value if hasattr(r, "value") else r) for t, r in content_sequence]  # type: ignore[union-attr]

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


class _ToolApprovalMockAgent(SupportsAgentRun):
    """Mock agent whose first run returns a FunctionApprovalRequestContent.

    Subsequent runs (after receiving an approval response in the input messages)
    return a final assistant text response that echoes the approved arguments.

    This mirrors a real agent whose tool invocation requires user approval.
    """

    def __init__(
        self,
        name: str,
        *,
        tool_name: str = "delete_file",
        tool_arguments: dict[str, Any] | None = None,
        approval_request_ids: Sequence[str] | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.name = name
        self.description: str | None = None
        self._tool_name = tool_name
        self._tool_arguments = tool_arguments or {"path": "/tmp/example"}
        # Pre-allocated request ids so the test can verify what the WorkflowAgent forwards.
        self._approval_request_ids: list[str] = list(approval_request_ids) if approval_request_ids else []
        self.run_count = 0
        # Inputs received on the most recent (continuation) run, for assertions.
        self.last_run_messages: list[Message] = []

    def create_session(self, **kwargs: Any) -> AgentSession:
        return AgentSession()

    def get_session(self, *, service_session_id: str | ServiceSessionId, **kwargs: Any) -> AgentSession:  # type: ignore[override]  # pyrefly: ignore[bad-override]  # ty: ignore[invalid-method-override]
        return AgentSession()

    def _next_request_id(self) -> str:
        if self._approval_request_ids:
            return self._approval_request_ids.pop(0)
        return str(uuid.uuid4())

    def _build_approval_request(self) -> Content:
        request_id = self._next_request_id()
        function_call = Content.from_function_call(
            call_id=request_id,
            name=self._tool_name,
            arguments=self._tool_arguments,
        )
        return Content.from_function_approval_request(id=request_id, function_call=function_call)

    @overload
    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = ...,
        *,
        stream: Literal[True],
        session: AgentSession | None = ...,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

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

    def _normalize(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None,
    ) -> list[Message]:
        if messages is None:
            return []
        if isinstance(messages, str):
            return [Message(role="user", contents=[Content.from_text(text=messages)])]
        if isinstance(messages, Message):
            return [messages]
        if isinstance(messages, Content):
            return [Message(role="user", contents=[messages])]
        result: list[Message] = []
        for item in messages:
            if isinstance(item, Message):
                result.append(item)
            elif isinstance(item, Content):
                result.append(Message(role="user", contents=[item]))
            else:
                result.append(Message(role="user", contents=[Content.from_text(text=item)]))
        return result

    def _approval_responses_in(self, messages: list[Message]) -> list[Content]:
        approvals: list[Content] = []
        for msg in messages:
            for content in msg.contents:
                if content.type == "function_approval_response":
                    approvals.append(content)
        return approvals

    async def _run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        normalized = self._normalize(messages)
        self.last_run_messages = normalized
        self.run_count += 1

        approvals = self._approval_responses_in(normalized)
        if approvals:
            # Continuation: reflect approved arguments in the final response text.
            approved_text = "; ".join(
                f"approved={a.approved} id={a.id}"  # type: ignore[attr-defined]
                for a in approvals
            )
            return AgentResponse(messages=[Message("assistant", [Content.from_text(text=f"done ({approved_text})")])])

        # First run: ask for tool approval.
        approval = self._build_approval_request()
        return AgentResponse(messages=[Message("assistant", [approval])])

    def _run_stream(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]:
        normalized = self._normalize(messages)
        self.last_run_messages = normalized
        self.run_count += 1
        approvals = self._approval_responses_in(normalized)

        async def _iter():
            if approvals:
                approved_text = "; ".join(
                    f"approved={a.approved} id={a.id}"  # type: ignore[attr-defined]
                    for a in approvals
                )
                yield AgentResponseUpdate(
                    contents=[Content.from_text(text=f"done ({approved_text})")],
                    role="assistant",
                    author_name=self.name,
                )
                return
            approval = self._build_approval_request()
            yield AgentResponseUpdate(
                contents=[approval],
                role="assistant",
                author_name=self.name,
            )

        return ResponseStream(_iter(), finalizer=AgentResponse.from_updates)


class TestWorkflowAgentToolApproval:
    """Tests for tool-approval requests bubbling through WorkflowAgent.

    Covers the case where a workflow contains an AgentExecutor whose underlying
    agent emits a FunctionApprovalRequestContent (tool needing user approval).
    The WorkflowAgent must:
      * forward the original FunctionApprovalRequestContent unchanged (no
        wrapping inside a synthesized 'request_info' function call), and
      * route a subsequent FunctionApprovalResponseContent back to the
        AgentExecutor so the agent can resume.
    """

    def _find_approval_request(
        self,
        contents: Sequence[Content],
        tool_name: str,
    ) -> Content | None:
        for content in contents:
            if (
                content.type == "function_approval_request"
                and getattr(content.function_call, "name", None) == tool_name  # type: ignore[attr-defined]
            ):
                return content
        return None

    async def test_tool_approval_request_forwarded_unchanged(self) -> None:
        """The agent's FunctionApprovalRequestContent surfaces verbatim (not re-wrapped)."""
        approval_id = "approval-abc-123"
        mock_agent = _ToolApprovalMockAgent(
            name="approval-agent",
            tool_name="delete_file",
            tool_arguments={"path": "/tmp/secret.txt"},
            approval_request_ids=[approval_id],
        )

        @executor
        async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        workflow = WorkflowBuilder(start_executor=start).add_edge(start, mock_agent).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Test Agent")

        result = await agent.run("please delete the file")

        assert isinstance(result, AgentResponse)

        # Locate the approval request emitted by the WorkflowAgent.
        all_contents: list[Content] = [c for m in result.messages for c in m.contents]
        approval = self._find_approval_request(all_contents, tool_name="delete_file")
        assert approval is not None, "WorkflowAgent did not forward the tool approval request"

        # The id and inner function_call must match what the underlying agent produced
        # — i.e. the WorkflowAgent must NOT have re-wrapped it inside a synthesized
        # 'request_info' approval request.
        assert approval.id == approval_id
        function_call = approval.function_call  # type: ignore[attr-defined]
        assert function_call is not None
        assert function_call.name == "delete_file"
        assert function_call.name != WorkflowAgent.REQUEST_INFO_FUNCTION_NAME
        assert function_call.arguments == {"path": "/tmp/secret.txt"}

        # The agent must be paused awaiting the approval response.
        pending = await workflow._runner_context.get_pending_request_info_events()
        assert approval_id in pending

    async def test_tool_approval_request_forwarded_unchanged_streaming(self) -> None:
        """Streaming variant: the approval request is forwarded as-is in updates."""
        approval_id = "approval-stream-1"
        mock_agent = _ToolApprovalMockAgent(
            name="approval-agent-stream",
            tool_name="send_email",
            tool_arguments={"to": "alice@example.com"},
            approval_request_ids=[approval_id],
        )

        @executor
        async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        workflow = WorkflowBuilder(start_executor=start).add_edge(start, mock_agent).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Stream Agent")

        updates: list[AgentResponseUpdate] = []
        async for update in agent.run("hi", stream=True):
            updates.append(update)

        approval_updates = [u for u in updates if any(c.type == "function_approval_request" for c in u.contents)]
        assert approval_updates, "Streaming did not surface a tool approval request"

        approval = self._find_approval_request(approval_updates[-1].contents, tool_name="send_email")
        assert approval is not None
        assert approval.id == approval_id
        function_call = approval.function_call  # type: ignore[attr-defined]
        assert function_call is not None
        assert function_call.name == "send_email"
        assert function_call.name != WorkflowAgent.REQUEST_INFO_FUNCTION_NAME
        assert function_call.arguments == {"to": "alice@example.com"}

    async def test_tool_approval_response_resumes_agent(self) -> None:
        """Sending the approval response back resumes the agent and clears pending requests."""
        approval_id = "approval-resume-1"
        mock_agent = _ToolApprovalMockAgent(
            name="approval-resume-agent",
            tool_name="delete_file",
            tool_arguments={"path": "/tmp/x"},
            approval_request_ids=[approval_id],
        )

        @executor
        async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        workflow = WorkflowBuilder(start_executor=start).add_edge(start, mock_agent).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Resume Agent")

        first_result = await agent.run("delete it")
        approval = self._find_approval_request(
            [c for m in first_result.messages for c in m.contents],
            tool_name="delete_file",
        )
        assert approval is not None
        assert mock_agent.run_count == 1

        # Build the approval response. NOTE: the inner function_call's name is the
        # original tool name ('delete_file'), NOT 'request_info'. This exercises the
        # branch in WorkflowAgent._extract_function_responses that routes raw
        # tool-approval responses straight through using content.id.
        approval_response = approval.to_function_approval_response(approved=True)  # type: ignore[attr-defined]
        response_message = Message(role="user", contents=[approval_response])

        final_result = await agent.run(response_message)
        assert isinstance(final_result, AgentResponse)

        # The mock agent should have been invoked a second time and seen the
        # approval response in its inputs.
        assert mock_agent.run_count == 2
        approvals_seen = [
            c for m in mock_agent.last_run_messages for c in m.contents if c.type == "function_approval_response"
        ]
        assert len(approvals_seen) == 1
        assert approvals_seen[0].id == approval_id  # type: ignore[attr-defined]
        assert approvals_seen[0].approved is True  # type: ignore[attr-defined]

        # The pending approval should now be cleared.
        pending = await workflow._runner_context.get_pending_request_info_events()
        assert approval_id not in pending

        # The final assistant message reflects the resumption.
        final_text = " ".join(m.text or "" for m in final_result.messages)
        assert "done" in final_text
        assert approval_id in final_text

    async def test_tool_approval_response_rejected_resumes_agent(self) -> None:
        """Rejection path: ``approved=False`` is forwarded to the inner agent and clears the pending request.

        The WorkflowAgent must route a rejection response back to the paused
        ``AgentExecutor`` exactly the same way as an approval — only the
        ``approved`` flag differs. The inner agent decides what to do with it.
        """
        approval_id = "approval-reject-1"
        mock_agent = _ToolApprovalMockAgent(
            name="approval-reject-agent",
            tool_name="delete_file",
            tool_arguments={"path": "/tmp/x"},
            approval_request_ids=[approval_id],
        )

        @executor
        async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        workflow = WorkflowBuilder(start_executor=start).add_edge(start, mock_agent).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Reject Agent")

        first_result = await agent.run("delete it")
        approval = self._find_approval_request(
            [c for m in first_result.messages for c in m.contents],
            tool_name="delete_file",
        )
        assert approval is not None
        assert mock_agent.run_count == 1

        # Reject the tool invocation.
        approval_response = approval.to_function_approval_response(approved=False)  # type: ignore[attr-defined]
        response_message = Message(role="user", contents=[approval_response])

        final_result = await agent.run(response_message)
        assert isinstance(final_result, AgentResponse)

        # The inner agent must have been resumed and seen ``approved=False``.
        assert mock_agent.run_count == 2
        approvals_seen = [
            c for m in mock_agent.last_run_messages for c in m.contents if c.type == "function_approval_response"
        ]
        assert len(approvals_seen) == 1
        assert approvals_seen[0].id == approval_id  # type: ignore[attr-defined]
        assert approvals_seen[0].approved is False  # type: ignore[attr-defined]

        # Pending approval cleared regardless of approve/reject.
        pending = await workflow._runner_context.get_pending_request_info_events()
        assert approval_id not in pending

        # The final assistant message reflects the rejection.
        final_text = " ".join(m.text or "" for m in final_result.messages)
        assert "approved=False" in final_text
        assert approval_id in final_text

    async def test_tool_approval_request_id_matches_pending_request(self) -> None:
        """The approval request id surfaced by WorkflowAgent matches the workflow's pending request id.

        This guards the AgentExecutor change that forwards
        request_id=user_input_request.id to ctx.request_info(...), which is what
        allows the response routed back via WorkflowAgent to resolve the pending
        request without an id-mismatch error.
        """
        approval_id = "approval-id-match-1"
        mock_agent = _ToolApprovalMockAgent(
            name="approval-id-match-agent",
            approval_request_ids=[approval_id],
        )

        @executor
        async def start(messages: list[Message], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
            await ctx.send_message(AgentExecutorRequest(messages=messages, should_respond=True))

        workflow = WorkflowBuilder(start_executor=start).add_edge(start, mock_agent).build()
        agent = WorkflowAgent(workflow=workflow, name="Approval Id Agent")

        await agent.run("go")

        pending = await workflow._runner_context.get_pending_request_info_events()
        # The agent's approval id is used as the workflow's pending request id.
        assert list(pending.keys()) == [approval_id]
