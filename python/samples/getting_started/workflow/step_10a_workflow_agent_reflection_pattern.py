# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from agent_framework import AgentRunResponseUpdate, ChatClientProtocol, ChatMessage, Contents, Role
from agent_framework.openai import OpenAIChatClient
from agent_framework.workflow import AgentRunUpdateEvent, Executor, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel

"""
The following sample demonstrates how to wrap a workflow as an agent using WorkflowAgent.

This sample shows how to:
1. Create a workflow with a reflection pattern (Worker + Reviewer executors)
2. Wrap the workflow as an agent using the .as_agent() method
3. Stream responses from the workflow agent like a regular agent
4. Implement a review-retry mechanism where responses are iteratively improved

The example implements a quality-controlled AI assistant where:
- Worker executor generates responses to user queries
- Reviewer executor evaluates the responses and provides feedback
- If not approved, the Worker incorporates feedback and regenerates the response
- The cycle continues until the response is approved
- Only approved responses are emitted to the external consumer

Key concepts demonstrated:
- WorkflowAgent: Wraps a workflow to make it behave as an agent
- Bidirectional workflow with cycles (Worker ↔ Reviewer)
- AgentRunUpdateEvent: How workflows communicate with external consumers
- Structured output parsing for review feedback
- State management with pending requests tracking
"""


@dataclass
class ReviewRequest:
    request_id: str
    user_messages: list[ChatMessage]
    agent_messages: list[ChatMessage]


@dataclass
class ReviewResponse:
    request_id: str
    feedback: str
    approved: bool


class Reviewer(Executor):
    """An executor that reviews messages and provides feedback."""

    def __init__(self, chat_client: ChatClientProtocol) -> None:
        super().__init__()
        self._chat_client = chat_client

    @handler
    async def review(self, request: ReviewRequest, ctx: WorkflowContext[ReviewResponse]) -> None:
        print(f"🔍 Reviewer: Evaluating response for request {request.request_id[:8]}...")

        # Use the chat client to review the message and use structured output.
        # NOTE: this can be modified to use an evaluation framework.

        class _Response(BaseModel):
            feedback: str
            approved: bool

        # Define the system prompt.
        messages = [
            ChatMessage(
                role=Role.SYSTEM,
                text="You are a reviewer for an AI agent, please provide feedback on the "
                "following exchange between a user and the AI agent, "
                "and indicate if the agent's responses are approved or not.\n"
                "Use the following criteria for your evaluation:\n"
                "- Relevance: Does the response address the user's query?\n"
                "- Accuracy: Is the information provided correct?\n"
                "- Clarity: Is the response easy to understand?\n"
                "- Completeness: Does the response cover all aspects of the query?\n"
                "Be critical in your evaluation and provide constructive feedback.\n"
                "Do not approve until all criteria are met.",
            )
        ]

        # Add user and agent messages to the chat history.
        messages.extend(request.user_messages)

        # Add agent messages to the chat history.
        messages.extend(request.agent_messages)

        # Add add one more instruction for the assistant to follow.
        messages.append(
            ChatMessage(role=Role.USER, text="Please provide a review of the agent's responses to the user.")
        )

        print("🔍 Reviewer: Sending review request to LLM...")
        # Get the response from the chat client.
        response = await self._chat_client.get_response(messages=messages, response_format=_Response)

        # Parse the response.
        parsed = _Response.model_validate_json(response.messages[-1].text)

        print(f"🔍 Reviewer: Review complete - Approved: {parsed.approved}")
        print(f"🔍 Reviewer: Feedback: {parsed.feedback}")

        # Send the review response.
        await ctx.send_message(
            ReviewResponse(request_id=request.request_id, feedback=parsed.feedback, approved=parsed.approved)
        )


class Worker(Executor):
    """An executor that performs tasks for the user."""

    def __init__(self, chat_client: ChatClientProtocol) -> None:
        super().__init__()
        self._chat_client = chat_client
        self._pending_requests: dict[str, tuple[ReviewRequest, list[ChatMessage]]] = {}

    @handler
    async def handle_user_messages(self, user_messages: list[ChatMessage], ctx: WorkflowContext[ReviewRequest]) -> None:
        print("🔧 Worker: Received user messages, generating response...")

        # Handle user messages and prepare a review request for the reviewer.
        # Define the system prompt.
        messages = [ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant.")]

        # Add user messages.
        messages.extend(user_messages)

        print("🔧 Worker: Calling LLM to generate response...")
        # Get the response from the chat client.
        response = await self._chat_client.get_response(messages=messages)
        print(f"🔧 Worker: Response generated: {response.messages[-1].text}")

        # Add agent messages.
        messages.extend(response.messages)

        # Create the review request.
        request = ReviewRequest(request_id=str(uuid4()), user_messages=user_messages, agent_messages=response.messages)

        print(f"🔧 Worker: Generated response, sending to reviewer (ID: {request.request_id[:8]})")
        # Send the review request.
        await ctx.send_message(request)

        # Add to pending requests.
        self._pending_requests[request.request_id] = (request, messages)

    @handler
    async def handle_review_response(self, review: ReviewResponse, ctx: WorkflowContext[ReviewRequest]) -> None:
        print(f"🔧 Worker: Received review for request {review.request_id[:8]} - Approved: {review.approved}")

        # Handle the review response. Depending on the approval status,
        # either emit the approved response as AgentRunUpdateEvent, or
        # retry given the feedback.
        if review.request_id not in self._pending_requests:
            raise ValueError(f"Received review response for unknown request ID: {review.request_id}")
        # Remove the request from pending requests.
        request, messages = self._pending_requests.pop(review.request_id)

        if review.approved:
            print("✅ Worker: Response approved! Emitting to external consumer...")
            # If approved, emit the agent run response update to the workflow's
            # external consumer.
            contents: list[Contents] = []
            for message in request.agent_messages:
                contents.extend(message.contents)
            # Emitting an AgentRunUpdateEvent in a workflow wrapped by a WorkflowAgent
            # will send the AgentRunResponseUpdate to the WorkflowAgent's
            # event stream.
            await ctx.add_event(
                AgentRunUpdateEvent(self.id, data=AgentRunResponseUpdate(contents=contents, role=Role.ASSISTANT))
            )
            return

        print(f"❌ Worker: Response not approved. Feedback: {review.feedback}")
        print("🔧 Worker: Incorporating feedback and regenerating response...")

        # Construct new messages with feedback.
        messages.append(ChatMessage(role=Role.SYSTEM, text=review.feedback))

        # Add additional instruction to address the feedback.
        messages.append(
            ChatMessage(
                role=Role.SYSTEM,
                text="Please incorporate the feedback above, and provide a response to user's next message.",
            )
        )
        messages.extend(request.user_messages)

        # Get the new response from the chat client.
        response = await self._chat_client.get_response(messages=messages)
        print(f"🔧 Worker: New response generated after feedback: {response.messages[-1].text}")

        # Process the response.
        messages.extend(response.messages)

        print(f"🔧 Worker: Generated improved response, sending for re-review (ID: {review.request_id[:8]})")
        # Send an updated review request.
        new_request = ReviewRequest(
            request_id=review.request_id, user_messages=request.user_messages, agent_messages=response.messages
        )
        await ctx.send_message(new_request)

        # Add to pending requests.
        self._pending_requests[new_request.request_id] = (new_request, messages)


async def main() -> None:
    print("🚀 Starting Workflow Agent Demo")
    print("=" * 50)

    # Create executors.
    print("📝 Creating chat client and executors...")
    mini_chat_client = OpenAIChatClient(ai_model_id="gpt-4.1-nano")
    chat_client = OpenAIChatClient(ai_model_id="gpt-4.1")
    reviewer = Reviewer(chat_client=chat_client)
    worker = Worker(chat_client=mini_chat_client)

    print("🏗️  Building workflow with Worker ↔ Reviewer cycle...")
    # Create the workflow agent with an underlying reflection workflow.
    agent = (
        WorkflowBuilder()
        .add_edge(worker, reviewer)  # <--- This edge allows the worker to send requests to the reviewer
        .add_edge(reviewer, worker)  # <--- This edge allows the reviewer to send feedback back to the worker
        .set_start_executor(worker)
        .build()
        .as_agent()  # Convert the workflow to an agent.
    )

    print("🎯 Running workflow agent with user query...")
    print("Query: 'Write code for parallel reading 1 million files on disk and write to a sorted output file.'")
    print("-" * 50)

    # Run the agent and stream events.
    async for event in agent.run_stream(
        "Write code for parallel reading 1 million files on disk and write to a sorted output file."
    ):
        print(f"📤 Agent Response: {event}")

    print("=" * 50)
    print("✅ Workflow completed!")


if __name__ == "__main__":
    print("🎬 Initializing Workflow as Agent Sample...")
    asyncio.run(main())
