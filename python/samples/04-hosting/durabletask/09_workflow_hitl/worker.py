# Copyright (c) Microsoft. All rights reserved.

"""Worker that hosts a Human-in-the-Loop (HITL) MAF Workflow on a standalone worker.

This sample is the durabletask counterpart to the Azure Functions
``12_workflow_hitl`` sample. It runs an agent-framework ``Workflow`` that pauses
for human approval using MAF's ``ctx.request_info`` / ``@response_handler``
pattern, hosted on a standalone Durable Task worker (no Azure Functions).

``DurableAIAgentWorker.configure_workflow`` auto-registers:

- a durable entity for each agent executor,
- a durable activity for each non-agent executor, and
- the workflow orchestrator (named ``WORKFLOW_ORCHESTRATOR_NAME``).

When the workflow calls ``ctx.request_info``, the orchestrator pauses and records
the open request in its custom status. An external client discovers the request
(``DurableWorkflowClient.get_pending_hitl_requests``) and resumes the workflow by
sending a response (``DurableWorkflowClient.send_hitl_response``).

The workflow is a content-moderation pipeline:
``input_router`` -> ``ContentAnalyzerAgent`` -> ``content_analyzer_executor``
-> ``human_review_executor`` (HITL pause) -> ``publish_executor``.

Prerequisites:
- Set ``FOUNDRY_PROJECT_ENDPOINT`` and ``FOUNDRY_MODEL``.
- Sign in with Azure CLI (``az login``) for ``AzureCliCredential``.
- Start a Durable Task Scheduler (e.g. the DTS emulator on ``localhost:8080``).

Run the worker (this process), then run ``client.py`` in another process.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    Agent,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    Message,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)
from agent_framework.azure import DurableAIAgentWorker
from agent_framework.foundry import FoundryChatClient, FoundryChatOptions
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from dotenv import load_dotenv
from durabletask.azuremanaged.worker import DurableTaskSchedulerWorker
from pydantic import BaseModel, ValidationError
from typing_extensions import Never

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTENT_ANALYZER_AGENT_NAME = "ContentAnalyzerAgent"

CONTENT_ANALYZER_INSTRUCTIONS = (
    "You are a content moderation assistant that analyzes user-submitted content for policy compliance. "
    "Evaluate appropriateness, assign a risk level ('low', 'medium', 'high'), list any concerns, and give a "
    "brief recommendation for human reviewers. Return JSON with fields is_appropriate (bool), risk_level (str), "
    "concerns (list of str), and recommendation (str)."
)


# ============================================================================
# Data Models
# ============================================================================


class ContentAnalysisResult(BaseModel):
    """Structured output from the content analysis agent."""

    is_appropriate: bool
    risk_level: str
    concerns: list[str]
    recommendation: str


@dataclass
class ContentSubmission:
    """Content submitted for moderation."""

    content_id: str
    title: str
    body: str
    author: str


@dataclass
class AnalysisWithSubmission:
    """Combines the AI analysis with the original submission for downstream processing."""

    submission: ContentSubmission
    analysis: ContentAnalysisResult


@dataclass
class HumanApprovalRequest:
    """Request sent to a human reviewer. Surfaced to clients via the orchestration status."""

    content_id: str
    title: str
    body: str
    author: str
    ai_analysis: ContentAnalysisResult
    prompt: str


class HumanApprovalResponse(BaseModel):
    """Response the external client sends back via the HITL response endpoint/method."""

    approved: bool
    reviewer_notes: str = ""


@dataclass
class ModerationResult:
    """Final result of the moderation workflow."""

    content_id: str
    status: str
    reviewer_notes: str


# ============================================================================
# Executors
# ============================================================================


class InputRouterExecutor(Executor):
    """Parses the incoming submission and routes it to the analysis agent."""

    def __init__(self) -> None:
        super().__init__(id="input_router")

    @handler
    async def route_input(self, submission: ContentSubmission, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        ctx.set_state("current_submission", submission)

        message = (
            f"Please analyze the following content for policy compliance:\n\n"
            f"Title: {submission.title}\n"
            f"Author: {submission.author}\n"
            f"Content:\n{submission.body}"
        )
        await ctx.send_message(
            AgentExecutorRequest(messages=[Message(role="user", contents=[message])], should_respond=True)
        )


class ContentAnalyzerExecutor(Executor):
    """Parses the AI agent's response and forwards it with the original submission."""

    def __init__(self) -> None:
        super().__init__(id="content_analyzer_executor")

    @handler
    async def handle_analysis(
        self, response: AgentExecutorResponse, ctx: WorkflowContext[AnalysisWithSubmission]
    ) -> None:
        try:
            analysis = ContentAnalysisResult.model_validate_json(response.agent_response.text)
        except ValidationError:
            analysis = ContentAnalysisResult(
                is_appropriate=False,
                risk_level="high",
                concerns=["Agent execution failed or yielded invalid JSON."],
                recommendation="Manual review required",
            )

        submission: ContentSubmission = ctx.get_state("current_submission")
        await ctx.send_message(AnalysisWithSubmission(submission=submission, analysis=analysis))


class HumanReviewExecutor(Executor):
    """Requests human approval using MAF's request_info / response_handler pattern."""

    def __init__(self) -> None:
        super().__init__(id="human_review_executor")

    @handler
    async def request_review(self, data: AnalysisWithSubmission, ctx: WorkflowContext) -> None:
        submission = data.submission
        analysis = data.analysis

        prompt = (
            f"Please review the following content for publication:\n\n"
            f"Title: {submission.title}\n"
            f"Author: {submission.author}\n"
            f"Content: {submission.body}\n\n"
            f"AI Analysis:\n"
            f"- Appropriate: {analysis.is_appropriate}\n"
            f"- Risk Level: {analysis.risk_level}\n"
            f"- Concerns: {', '.join(analysis.concerns) if analysis.concerns else 'None'}\n"
            f"- Recommendation: {analysis.recommendation}\n\n"
            f"Please approve or reject this content."
        )
        approval_request = HumanApprovalRequest(
            content_id=submission.content_id,
            title=submission.title,
            body=submission.body,
            author=submission.author,
            ai_analysis=analysis,
            prompt=prompt,
        )

        # Pause the workflow and wait for a human response.
        await ctx.request_info(request_data=approval_request, response_type=HumanApprovalResponse)

    @response_handler
    async def handle_approval_response(
        self,
        original_request: HumanApprovalRequest,
        response: HumanApprovalResponse,
        ctx: WorkflowContext[ModerationResult],
    ) -> None:
        logger.info(
            "Human review received for content %s: approved=%s",
            original_request.content_id,
            response.approved,
        )
        await ctx.send_message(
            ModerationResult(
                content_id=original_request.content_id,
                status="approved" if response.approved else "rejected",
                reviewer_notes=response.reviewer_notes,
            )
        )


class PublishExecutor(Executor):
    """Finalizes publication or rejection of the content."""

    def __init__(self) -> None:
        super().__init__(id="publish_executor")

    @handler
    async def handle_result(self, result: ModerationResult, ctx: WorkflowContext[Never, str]) -> None:
        if result.status == "approved":
            message = (
                f"Content '{result.content_id}' has been APPROVED and published. "
                f"Reviewer notes: {result.reviewer_notes or 'None'}"
            )
        else:
            message = (
                f"Content '{result.content_id}' has been REJECTED. Reviewer notes: {result.reviewer_notes or 'None'}"
            )
        logger.info(message)
        await ctx.yield_output(message)


def _create_chat_client() -> FoundryChatClient:
    """Create an Azure AI Foundry chat client using AzureCliCredential."""
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AsyncAzureCliCredential(),
    )


def create_workflow() -> Workflow:
    """Build the content-moderation workflow with a human-in-the-loop pause."""
    chat_client = _create_chat_client()

    content_analyzer_agent = Agent(
        client=chat_client,
        name=CONTENT_ANALYZER_AGENT_NAME,
        instructions=CONTENT_ANALYZER_INSTRUCTIONS,
        default_options=FoundryChatOptions[Any](response_format=ContentAnalysisResult),
    )

    input_router = InputRouterExecutor()
    content_analyzer_executor = ContentAnalyzerExecutor()
    human_review_executor = HumanReviewExecutor()
    publish_executor = PublishExecutor()

    return (
        WorkflowBuilder(start_executor=input_router)
        .add_edge(input_router, content_analyzer_agent)
        .add_edge(content_analyzer_agent, content_analyzer_executor)
        .add_edge(content_analyzer_executor, human_review_executor)
        .add_edge(human_review_executor, publish_executor)
        .build()
    )


def get_worker(
    taskhub: str | None = None, endpoint: str | None = None, log_handler: logging.Handler | None = None
) -> DurableTaskSchedulerWorker:
    """Create a configured DurableTaskSchedulerWorker."""
    taskhub_name = taskhub or os.getenv("TASKHUB", "default")
    endpoint_url = endpoint or os.getenv("ENDPOINT", "http://localhost:8080")

    credential = None if endpoint_url == "http://localhost:8080" else AzureCliCredential()

    return DurableTaskSchedulerWorker(
        host_address=endpoint_url,
        secure_channel=endpoint_url != "http://localhost:8080",
        taskhub=taskhub_name,
        token_credential=credential,
        log_handler=log_handler,
    )


def setup_worker(worker: DurableTaskSchedulerWorker) -> DurableAIAgentWorker:
    """Register the workflow (agents + activities + orchestrator) on the worker."""
    agent_worker = DurableAIAgentWorker(worker)

    workflow = create_workflow()
    agent_worker.configure_workflow(workflow)
    logger.info("✓ Configured HITL workflow with %d executors", len(workflow.executors))

    return agent_worker


async def main() -> None:
    """Start the worker and block until interrupted."""
    worker = get_worker()
    setup_worker(worker)

    logger.info("Worker is ready and listening for work items. Press Ctrl+C to stop.")
    try:
        worker.start()
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker shutdown initiated")

    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
