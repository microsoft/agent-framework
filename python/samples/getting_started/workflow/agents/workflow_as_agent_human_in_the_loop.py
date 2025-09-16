# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    ChatMessage,
    FunctionCallContent,
    FunctionResultContent,
    Role,
)
from agent_framework.openai import OpenAIChatClient
from agent_framework import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)

from samples.getting_started.workflow.agents.workflow_as_agent_reflection_pattern import (
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
to a human via RequestInfoExecutor, receives the human response, and then
forwards that response back to the Worker.

Prerequisites:
- OpenAI account configured and accessible for OpenAIChatClient.
- Familiarity with WorkflowBuilder, Executor, and WorkflowContext from agent_framework.
- Understanding of request-response message handling (RequestInfoMessage, RequestResponse).
- (Optional) Review of reflection and escalation patterns, such as those in
  workflow_as_agent_reflection.py.
"""


@dataclass
class HumanReviewRequest(RequestInfoMessage):
    """A request message type for escalation to a human reviewer."""

    agent_request: ReviewRequest | None = None


class ReviewerWithHumanInTheLoop(Executor):
    """Executor that always escalates reviews to a human manager."""

    def __init__(self, worker_id: str, request_info_id: str) -> None:
        super().__init__()
        self._worker_id = worker_id
        self._request_info_id = request_info_id

    @handler
    async def review(self, request: ReviewRequest, ctx: WorkflowContext[ReviewResponse | HumanReviewRequest]) -> None:
        # In this simplified example, we always escalate to a human manager.
        # See workflow_as_agent_reflection.py for an implementation
        # using an automated agent to make the review decision.
        print(f"Reviewer: Evaluating response for request {request.request_id[:8]}...")
        print("Reviewer: Escalating to human manager...")

        # Forward the request to a human manager by sending a HumanReviewRequest.
        await ctx.send_message(
            HumanReviewRequest(agent_request=request),
            target_id=self._request_info_id,
        )

    @handler
    async def accept_human_review(
        self, response: RequestResponse[HumanReviewRequest, ReviewResponse], ctx: WorkflowContext[ReviewResponse]
    ) -> None:
        # Accept the human review response and forward it back to the Worker.
        human_response = response.data
        assert isinstance(human_response, ReviewResponse)
        print(f"Reviewer: Accepting human review for request {human_response.request_id[:8]}...")
        print(f"Reviewer: Human feedback: {human_response.feedback}")
        print(f"Reviewer: Human approved: {human_response.approved}")
        print("Reviewer: Forwarding human review back to worker...")
        await ctx.send_message(human_response, target_id=self._worker_id)


async def main() -> None:
    print("Starting Workflow Agent with Human-in-the-Loop Demo")
    print("=" * 50)

    # Create executors for the workflow.
    print("Creating chat client and executors...")
    mini_chat_client = OpenAIChatClient(ai_model_id="gpt-4.1-nano")
    worker = Worker(chat_client=mini_chat_client)
    request_info_executor = RequestInfoExecutor()
    reviewer = ReviewerWithHumanInTheLoop(worker_id=worker.id, request_info_id=request_info_executor.id)

    print("Building workflow with Worker ↔ Reviewer cycle...")
    # Build a workflow with bidirectional communication between Worker and Reviewer,
    # and escalation paths for human review.
    agent = (
        WorkflowBuilder()
        .add_edge(worker, reviewer)  # Worker sends requests to Reviewer
        .add_edge(reviewer, worker)  # Reviewer sends feedback to Worker
        .add_edge(reviewer, request_info_executor)  # Reviewer requests human input
        .add_edge(request_info_executor, reviewer)  # Human input forwarded back to Reviewer
        .set_start_executor(worker)
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
        if isinstance(human_review_function_call.arguments, str):
            request = WorkflowAgent.RequestInfoFunctionArgs.model_validate_json(human_review_function_call.arguments)
        else:
            request = WorkflowAgent.RequestInfoFunctionArgs.model_validate(human_review_function_call.arguments)

        # Mock a human response approval for demonstration purposes.
        human_response = ReviewResponse(
            request_id=request.data["agent_request"]["request_id"], feedback="Approved", approved=True
        )

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
