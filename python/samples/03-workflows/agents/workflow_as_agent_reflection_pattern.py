# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from dataclasses import dataclass
from uuid import uuid4

from agent_framework import (
    AgentResponse,
    Executor,
    Message,
    SupportsChatGetResponse,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file
load_dotenv()

"""
Sample: Workflow as Agent with Reflection and Retry Pattern

Purpose:
This sample demonstrates how to wrap a workflow as an agent using WorkflowAgent.
It uses a reflection pattern where a Worker executor generates responses and a
Reviewer executor evaluates them. If the response is not approved, the Worker
regenerates the output based on feedback until the Reviewer approves it. Only
approved responses are emitted to the external consumer. The workflow completes when idle.

Key Concepts Demonstrated:
- WorkflowAgent: Wraps a workflow to behave like a regular agent.
- Cyclic workflow design (Worker ↔ Reviewer) for iterative improvement.
- Structured output parsing for review feedback using Pydantic.
- State management for pending requests and retry logic.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- OpenAI account configured and accessible for AzureOpenAIResponsesClient.
- Familiarity with WorkflowBuilder, Executor, WorkflowContext, and event handling.
- Understanding of how agent messages are generated, reviewed, and re-submitted.
"""


@dataclass
class ReviewRequest:
    """Structured request passed from Worker to Reviewer for evaluation."""

    request_id: str
    user_messages: list[Message]
    agent_messages: list[Message]


@dataclass
class ReviewResponse:
    """Structured response from Reviewer back to Worker."""

    request_id: str
    feedback: str
    approved: bool


class Reviewer(Executor):
    """Executor that reviews agent responses and provides structured feedback."""

    def __init__(self, id: str, client: SupportsChatGetResponse) -> None:
        super().__init__(id=id)
        self._chat_client = client

    @handler
    async def review(self, request: ReviewRequest, ctx: WorkflowContext[ReviewResponse]) -> None:
        print(f"Reviewer: Evaluating response for request {request.request_id[:8]}...")

        # Define structured schema for the LLM to return.
        class _Response(BaseModel):
            feedback: str
            approved: bool

        # Construct review instructions and context.
        messages = [
            Message(
                role="system",
                text=(
                    "You are a reviewer for an AI agent. Provide feedback on the "
                    "exchange between a user and the agent. Indicate approval only if:\n"
                    "- Relevance: response addresses the query\n"
                    "- Accuracy: information is correct\n"
                    "- Clarity: response is easy to understand\n"
                    "- Completeness: response covers all aspects\n"
                    "Do not approve until all criteria are satisfied."
                ),
            )
        ]
        # Add conversation history.
        messages.extend(request.user_messages)
        messages.extend(request.agent_messages)

        # Add explicit review instruction.
        messages.append(Message("user", ["Please review the agent's responses."]))

        print("Reviewer: Sending review request to LLM...")
        response = await self._chat_client.get_response(messages=messages, options={"response_format": _Response})

        parsed = _Response.model_validate_json(response.messages[-1].text)

        print(f"Reviewer: Review complete - Approved: {parsed.approved}")
        print(f"Reviewer: Feedback: {parsed.feedback}")

        # Send structured review result to Worker.
        await ctx.send_message(
            ReviewResponse(request_id=request.request_id, feedback=parsed.feedback, approved=parsed.approved)
        )


class Worker(Executor):
    """Executor that generates responses and incorporates feedback when necessary."""

    def __init__(self, id: str, client: SupportsChatGetResponse) -> None:
        super().__init__(id=id)
        self._chat_client = client
        self._pending_requests: dict[str, tuple[ReviewRequest, list[Message]]] = {}

    @handler
    async def handle_user_messages(self, user_messages: list[Message], ctx: WorkflowContext[ReviewRequest]) -> None:
        print("Worker: Received user messages, generating response...")

        # Initialize chat with system prompt.
        messages = [Message("system", ["You are a helpful assistant."])]
        messages.extend(user_messages)

        print("Worker: Calling LLM to generate response...")
        response = await self._chat_client.get_response(messages=messages)
        print(f"Worker: Response generated: {response.messages[-1].text}")

        # Add agent messages to context.
        messages.extend(response.messages)

        # Create review request and send to Reviewer.
        request = ReviewRequest(request_id=str(uuid4()), user_messages=user_messages, agent_messages=response.messages)
        print(f"Worker: Sending response for review (ID: {request.request_id[:8]})")
        await ctx.send_message(request)

        # Track request for possible retry.
        self._pending_requests[request.request_id] = (request, messages)

    @handler
    async def handle_review_response(
        self, review: ReviewResponse, ctx: WorkflowContext[ReviewRequest, AgentResponse]
    ) -> None:
        print(f"Worker: Received review for request {review.request_id[:8]} - Approved: {review.approved}")

        if review.request_id not in self._pending_requests:
            raise ValueError(f"Unknown request ID in review: {review.request_id}")

        request, messages = self._pending_requests.pop(review.request_id)

        if review.approved:
            print("Worker: Response approved. Emitting to external consumer...")
            # Emit approved result to external consumer
            await ctx.yield_output(AgentResponse(messages=request.agent_messages))
            return

        print(f"Worker: Response not approved. Feedback: {review.feedback}")
        print("Worker: Regenerating response with feedback...")

        # Incorporate review feedback.
        messages.append(Message("system", [review.feedback]))
        messages.append(Message("system", ["Please incorporate the feedback and regenerate the response."]))
        messages.extend(request.user_messages)

        # Retry with updated prompt.
        response = await self._chat_client.get_response(messages=messages)
        print(f"Worker: New response generated: {response.messages[-1].text}")

        messages.extend(response.messages)

        # Send updated request for re-review.
        new_request = ReviewRequest(
            request_id=review.request_id, user_messages=request.user_messages, agent_messages=response.messages
        )
        await ctx.send_message(new_request)

        # Track new request for further evaluation.
        self._pending_requests[new_request.request_id] = (new_request, messages)


async def main() -> None:
    print("Starting Workflow Agent Demo")
    print("=" * 50)

    print("Building workflow with Worker ↔ Reviewer cycle...")
    worker = Worker(
        id="worker",
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
    )
    reviewer = Reviewer(
        id="reviewer",
        client=AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ),
    )

    agent = (
        WorkflowBuilder(start_executor=worker)
        .add_edge(worker, reviewer)  # Worker sends responses to Reviewer
        .add_edge(reviewer, worker)  # Reviewer provides feedback to Worker
        .build()
        .as_agent()  # Wrap workflow as an agent
    )

    print("Running workflow agent with user query...")
    print("Query: 'Write code for parallel reading 1 million files on disk and write to a sorted output file.'")
    print("-" * 50)

    # Run agent in streaming mode to observe incremental updates.
    response = await agent.run(
        "Write code for parallel reading 1 million files on disk and write to a sorted output file."
    )

    print("-" * 50)
    print("Final Approved Response:")
    print(f"{response.agent_id}: {response.text}")


if __name__ == "__main__":
    print("Initializing Workflow as Agent Sample...")
    asyncio.run(main())
