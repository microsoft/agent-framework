# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

# Ensure local getting_started package can be imported when running as a script.
_SAMPLES_ROOT = Path(__file__).resolve().parents[3]
if str(_SAMPLES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SAMPLES_ROOT))

from agent_framework import (  # noqa: E402
    ChatMessage,
    Executor,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
    tool,
)
from getting_started.workflows.agents.workflow_as_agent_reflection_pattern import (  # noqa: E402
    ReviewRequest,
    ReviewResponse,
    Worker,
)

"""
Sample: Workflow Agent with Human-in-the-Loop

Purpose:
This sample demonstrates how to build a workflow agent that escalates uncertain
decisions to a human manager. A Worker generates results, while a Reviewer
evaluates them. When the Reviewer is not confident, it escalates the decision
to a human, receives the human response, and then forwards that response back
to the Worker. The workflow completes when idle.

Prerequisites:
- OpenAI account configured and accessible for OpenAIChatClient.
- Familiarity with WorkflowBuilder, Executor, and WorkflowContext from agent_framework.
- Understanding of request-response message handling in executors.
- (Optional) Review of reflection and escalation patterns, such as those in
  workflow_as_agent_reflection.py.
"""


@dataclass
class HumanReviewRequest:
    """A request message type for escalation to a human reviewer."""

    agent_request: ReviewRequest | None = None


class ReviewerWithHumanInTheLoop(Executor):
    """Executor that always escalates reviews to a human manager."""

    def __init__(self, worker_id: str, reviewer_id: str | None = None) -> None:
        unique_id = reviewer_id or f"{worker_id}-reviewer"
        super().__init__(id=unique_id)
        self._worker_id = worker_id

    @handler
    async def review(self, request: ReviewRequest, ctx: WorkflowContext) -> None:
        # In this simplified example, we always escalate to a human manager.
        # See workflow_as_agent_reflection.py for an implementation
        # using an automated agent to make the review decision.
        print(f"Reviewer: Evaluating response for request {request.request_id[:8]}...")
        print("Reviewer: Escalating to human manager...")

        # Forward the request to a human manager by sending a HumanReviewRequest.
        await ctx.request_info(request_data=HumanReviewRequest(agent_request=request), response_type=ReviewResponse)

    @response_handler
    async def accept_human_review(
        self,
        original_request: HumanReviewRequest,
        response: ReviewResponse,
        ctx: WorkflowContext[ReviewResponse],
    ) -> None:
        # Accept the human review response and forward it back to the Worker.
        print(f"Reviewer: Accepting human review for request {response.request_id[:8]}...")
        print(f"Reviewer: Human feedback: {response.feedback}")
        print(f"Reviewer: Human approved: {response.approved}")
        print("Reviewer: Forwarding human review back to worker...")
        await ctx.send_message(response, target_id=self._worker_id)


async def main() -> None:
    print("Starting Workflow Agent with Human-in-the-Loop Demo")
    print("=" * 50)

    print("Building workflow with Worker-Reviewer cycle...")
    # Build a workflow with bidirectional communication between Worker and Reviewer,
    # and escalation paths for human review.
    agent = (
        WorkflowBuilder()
        .register_executor(
            lambda: Worker(
                id="sub-worker",
                chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
            ),
            name="worker",
        )
        .register_executor(
            lambda: ReviewerWithHumanInTheLoop(worker_id="sub-worker"),
            name="reviewer",
        )
        .add_edge("worker", "reviewer")  # Worker sends requests to Reviewer
        .add_edge("reviewer", "worker")  # Reviewer sends feedback to Worker
        .set_start_executor("worker")
        .build()
        .as_agent()  # Convert workflow into an agent interface
    )

    print("Running workflow agent with user query...")
    print("Query: 'Write code for parallel reading 1 million files on disk and write to a sorted output file.'")
    print("-" * 50)

    # Run the agent with an initial query.
    response = await agent.run(
        "Write code for parallel reading 1 million Files on disk and write to a sorted output file."
    )

    # Locate the human review function call in the response messages.
    human_review_function_call: FunctionCallContent | None = None
    for message in response.messages:
        for content in message.contents:
            if isinstance(content, FunctionCallContent) and content.name == WorkflowAgent.REQUEST_INFO_FUNCTION_NAME:
                human_review_function_call = content

    # Handle the human review if required.
    if human_review_function_call:
        # Parse the human review request arguments.
        human_request_args = human_review_function_call.arguments
        if isinstance(human_request_args, str):
            request: WorkflowAgent.RequestInfoFunctionArgs = WorkflowAgent.RequestInfoFunctionArgs.from_json(
                human_request_args
            )
        elif isinstance(human_request_args, Mapping):
            request = WorkflowAgent.RequestInfoFunctionArgs.from_dict(dict(human_request_args))
        else:
            raise TypeError("Unexpected argument type for human review function call.")

        request_payload: Any = request.data
        if not isinstance(request_payload, HumanReviewRequest):
            raise ValueError("Human review request payload must be a HumanReviewRequest.")

        agent_request = request_payload.agent_request
        if agent_request is None:
            raise ValueError("Human review request must include agent_request.")

        request_id = agent_request.request_id
        # Mock a human response approval for demonstration purposes.
        human_response = ReviewResponse(request_id=request_id, feedback="Approved", approved=True)

        # Create the function call result object to send back to the agent.
        human_review_function_result = FunctionResultContent(
            call_id=human_review_function_call.call_id,
            result=human_response,
        )
        # Send the human review result back to the agent.
        response = await agent.run(ChatMessage(role=Role.TOOL, contents=[human_review_function_result]))
        print(f"📤 Agent Response: {response.messages[-1].text}")

    print("=" * 50)
    print("Workflow completed!")


if __name__ == "__main__":
    print("Initializing Workflow as Agent Sample...")
    asyncio.run(main())
