# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    ChatMessage,
    ChatRole,
    FunctionCallContent,
    FunctionResultContent,
)
from agent_framework.openai import OpenAIChatClient
from agent_framework.workflow import (
    Executor,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from step_10a_workflow_agent_reflection_pattern import ReviewRequest, ReviewResponse, Worker


@dataclass
class HumanReviewRequest(RequestInfoMessage):
    agent_request: ReviewRequest | None = None


class ReviewerWithHumanInTheLoop(Executor):
    """An executor that raises to human manager for review when not confident."""

    def __init__(self, worker_id: str, request_info_id: str) -> None:
        super().__init__()
        self._worker_id = worker_id
        self._request_info_id = request_info_id

    @handler
    async def review(self, request: ReviewRequest, ctx: WorkflowContext[ReviewResponse | HumanReviewRequest]) -> None:
        print(f"🔍 Reviewer: Evaluating response for request {request.request_id[:8]}...")

        # NOTE: for simplicity, we always escalate to human manager.
        # See step_10a_workflow_agent_reflection_pattern.py for implementation
        # using an chat client.

        print("🔍 Reviewer: Escalate to human manager")
        # Send to human manager
        await ctx.send_message(
            HumanReviewRequest(agent_request=request),
            target_id=self._request_info_id,
        )

    @handler
    async def accept_human_review(
        self, response: RequestResponse[HumanReviewRequest, ReviewResponse], ctx: WorkflowContext[ReviewResponse]
    ) -> None:
        human_response = response.data
        assert isinstance(human_response, ReviewResponse)
        print(f"🔍 Reviewer: Accepting human review for request {human_response.request_id[:8]}...")
        print(f"🔍 Reviewer: Human feedback: {human_response.feedback}")
        print(f"🔍 Reviewer: Human approved: {human_response.approved}")
        print("🔍 Reviewer: Forwarding human review back to worker...")
        await ctx.send_message(human_response, target_id=self._worker_id)


async def main() -> None:
    print("🚀 Starting Workflow Agent with Human-in-the-Loop Demo")
    print("=" * 50)

    # Create executors.
    print("📝 Creating chat client and executors...")
    mini_chat_client = OpenAIChatClient(ai_model_id="gpt-4.1-nano")
    worker = Worker(chat_client=mini_chat_client)
    request_info_executor = RequestInfoExecutor()
    reviewer = ReviewerWithHumanInTheLoop(worker_id=worker.id, request_info_id=request_info_executor.id)

    print("🏗️  Building workflow with Worker ↔ Reviewer cycle...")
    # Create the workflow agent with an underlying reflection workflow.
    agent = (
        WorkflowBuilder()
        .add_edge(worker, reviewer)  # <--- This edge allows the worker to send requests to the reviewer
        .add_edge(reviewer, worker)  # <--- This edge allows the reviewer to send feedback back to the worker
        .add_edge(
            reviewer, request_info_executor
        )  # <--- This edge allows the reviewer to send human input requests through the request info executor
        .add_edge(
            request_info_executor, reviewer
        )  # <--- This edge allows the human input to be forwarded back to the reviewer
        .set_start_executor(worker)
        .build()
        .as_agent()  # Convert the workflow to an agent.
    )

    print("🎯 Running workflow agent with user query...")
    print("Query: 'Write code for parallel reading 1 million files on disk and write to a sorted output file.'")
    print("-" * 50)

    # NOTE: you can also run the workflow directly, i.e., without the as_agent().
    # Then, you will need to handle RequestInfoEvent and send response to the workflow
    # using send_response().

    # Run the agent.
    response = await agent.run(
        "Write code for parallel reading 1 million Files on disk and write to a sorted output file."
    )
    #
    # Find human review function call.
    # TODO(ekzhu): update this to FunctionApprovalRequestContent
    # monitor: https://github.com/microsoft/agent-framework/issues/285
    human_review_function_call: FunctionCallContent | None = None
    for message in response.messages:
        for content in message.contents:
            if isinstance(content, FunctionCallContent) and content.name == WorkflowAgent.REQUEST_INFO_FUNCTION_NAME:
                human_review_function_call = content

    # Handle human review if needed.
    if human_review_function_call:
        # Use WorkflowAgent.RequestInfoFunctionArgs to parse the request.
        if isinstance(human_review_function_call.arguments, str):
            request = WorkflowAgent.RequestInfoFunctionArgs.model_validate_json(human_review_function_call.arguments)
        else:
            request = WorkflowAgent.RequestInfoFunctionArgs.model_validate(human_review_function_call.arguments)
        # Mock a human approval.
        human_response = ReviewResponse(
            request_id=request.data["agent_request"]["request_id"], feedback="Approved", approved=True
        )
        # Create the function call result to be sent back.
        # TODO(ekzhu): update this to FunctionApprovalResponseContent
        # monitor: https://github.com/microsoft/agent-framework/issues/285
        human_review_function_result = FunctionResultContent(
            call_id=human_review_function_call.call_id,
            result=human_response,
        )
        # Send the human review result back to the agent.
        response = await agent.run(ChatMessage(role=ChatRole.TOOL, contents=[human_review_function_result]))
        print(f"📤 Agent Response: {response.messages[-1].text}")

    print("=" * 50)
    print("✅ Workflow completed!")


if __name__ == "__main__":
    print("🎬 Initializing Workflow as Agent Sample...")
    asyncio.run(main())
