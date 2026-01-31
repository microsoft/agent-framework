# Copyright (c) Microsoft. All rights reserved.
"""Workflow with Human-in-the-Loop (HITL) using MAF request_info Pattern.

This sample demonstrates how to integrate human approval into a MAF workflow
running on Azure Durable Functions. It uses the MAF `request_info` and
`@response_handler` pattern for structured HITL interactions.

The workflow simulates a content moderation pipeline:
1. User submits content for publication
2. An AI agent analyzes the content for policy compliance
3. A human reviewer is prompted to approve/reject the content
4. Based on approval, content is either published or rejected

Key architectural points:
- Uses MAF's `ctx.request_info()` to pause workflow and request human input
- Uses `@response_handler` decorator to handle the human's response
- AgentFunctionApp automatically provides HITL endpoints for status and response
- Durable Functions provides durability while waiting for human input

Prerequisites:
- Azure OpenAI configured with required environment variables
- Durable Task Scheduler connection string
- Authentication via Azure CLI (az login)
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    Role,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel
from typing_extensions import Never

from agent_framework_azurefunctions import AgentFunctionApp

logger = logging.getLogger(__name__)

# Environment variable names
AZURE_OPENAI_ENDPOINT_ENV = "AZURE_OPENAI_ENDPOINT"
AZURE_OPENAI_DEPLOYMENT_ENV = "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"
AZURE_OPENAI_API_KEY_ENV = "AZURE_OPENAI_API_KEY"

# Agent names
CONTENT_ANALYZER_AGENT_NAME = "ContentAnalyzerAgent"


# ============================================================================
# Data Models
# ============================================================================


class ContentAnalysisResult(BaseModel):
    """Structured output from the content analysis agent."""

    is_appropriate: bool
    risk_level: str  # low, medium, high
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
class HumanApprovalRequest:
    """Request sent to human reviewer for approval.
    
    This is the payload passed to ctx.request_info() and will be
    exposed via the orchestration status for external systems to retrieve.
    """

    content_id: str
    title: str
    body: str
    author: str
    ai_analysis: ContentAnalysisResult
    prompt: str


class HumanApprovalResponse(BaseModel):
    """Response from human reviewer.
    
    This is what the external system must send back via the HITL response endpoint.
    """

    approved: bool
    reviewer_notes: str = ""


@dataclass
class ModerationResult:
    """Final result of the moderation workflow."""

    content_id: str
    status: str  # "approved", "rejected"
    ai_analysis: ContentAnalysisResult | None
    reviewer_notes: str


# ============================================================================
# Agent Instructions
# ============================================================================

CONTENT_ANALYZER_INSTRUCTIONS = """You are a content moderation assistant that analyzes user-submitted content
for policy compliance. Evaluate the content for:

1. Appropriateness - Is the content suitable for a general audience?
2. Risk level - Rate as 'low', 'medium', or 'high' based on potential issues
3. Concerns - List any specific issues found (empty list if none)
4. Recommendation - Provide a brief recommendation for human reviewers

Return a JSON response with:
- is_appropriate: boolean
- risk_level: string ('low', 'medium', 'high')
- concerns: list of strings
- recommendation: string

Be thorough but fair in your analysis."""


# ============================================================================
# Executors
# ============================================================================


@dataclass
class AnalysisWithSubmission:
    """Combines the AI analysis with the original submission for downstream processing."""

    submission: ContentSubmission
    analysis: ContentAnalysisResult


class ContentAnalyzerExecutor(Executor):
    """Parses the AI agent's response and prepares for human review."""

    def __init__(self):
        super().__init__(id="content_analyzer_executor")

    @handler
    async def handle_analysis(
        self,
        response: AgentExecutorResponse,
        ctx: WorkflowContext[AnalysisWithSubmission],
    ) -> None:
        """Parse the AI analysis and forward with submission context."""
        analysis = ContentAnalysisResult.model_validate_json(response.agent_run_response.text)

        # Retrieve the original submission from shared state
        submission: ContentSubmission = await ctx.get_shared_state("current_submission")

        await ctx.send_message(AnalysisWithSubmission(submission=submission, analysis=analysis))


class HumanReviewExecutor(Executor):
    """Requests human approval using MAF's request_info pattern.
    
    This executor demonstrates the core HITL pattern:
    1. Receives the AI analysis result
    2. Calls ctx.request_info() to pause and request human input
    3. The @response_handler method processes the human's response
    """

    def __init__(self):
        super().__init__(id="human_review_executor")

    @handler
    async def request_review(
        self,
        data: AnalysisWithSubmission,
        ctx: WorkflowContext,
    ) -> None:
        """Request human review for the content.
        
        This method:
        1. Constructs the approval request with all context
        2. Calls request_info to pause the workflow
        3. The workflow will resume when a response is provided via the HITL endpoint
        """
        submission = data.submission
        analysis = data.analysis

        # Construct the human-readable prompt
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

        # Store analysis in shared state for the response handler
        await ctx.set_shared_state("pending_analysis", data)

        # Request human input - workflow will pause here
        # The response_type specifies what we expect back
        await ctx.request_info(
            request_data=approval_request,
            response_type=HumanApprovalResponse,
        )

    @response_handler
    async def handle_approval_response(
        self,
        original_request: HumanApprovalRequest,
        response: HumanApprovalResponse,
        ctx: WorkflowContext[ModerationResult],
    ) -> None:
        """Process the human reviewer's decision.
        
        This method is called automatically when a response to request_info is received.
        The original_request contains the HumanApprovalRequest we sent.
        The response contains the HumanApprovalResponse from the reviewer.
        """
        logger.info(
            "Human review received for content %s: approved=%s, notes=%s",
            original_request.content_id,
            response.approved,
            response.reviewer_notes,
        )

        # Create the final moderation result
        status = "approved" if response.approved else "rejected"
        result = ModerationResult(
            content_id=original_request.content_id,
            status=status,
            ai_analysis=original_request.ai_analysis,
            reviewer_notes=response.reviewer_notes,
        )

        await ctx.send_message(result)


class PublishExecutor(Executor):
    """Handles the final publication or rejection of content."""

    def __init__(self):
        super().__init__(id="publish_executor")

    @handler
    async def handle_result(
        self,
        result: ModerationResult,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        """Finalize the moderation and yield output."""
        if result.status == "approved":
            message = (
                f"✅ Content '{result.content_id}' has been APPROVED and published.\n"
                f"Reviewer notes: {result.reviewer_notes or 'None'}"
            )
        else:
            message = (
                f"❌ Content '{result.content_id}' has been REJECTED.\n"
                f"Reviewer notes: {result.reviewer_notes or 'None'}"
            )

        logger.info(message)
        await ctx.yield_output(message)


# ============================================================================
# Input Router Executor
# ============================================================================


def _build_client_kwargs() -> dict[str, Any]:
    """Build Azure OpenAI client configuration from environment variables."""
    endpoint = os.getenv(AZURE_OPENAI_ENDPOINT_ENV)
    if not endpoint:
        raise RuntimeError(f"{AZURE_OPENAI_ENDPOINT_ENV} environment variable is required.")

    deployment = os.getenv(AZURE_OPENAI_DEPLOYMENT_ENV)
    if not deployment:
        raise RuntimeError(f"{AZURE_OPENAI_DEPLOYMENT_ENV} environment variable is required.")

    client_kwargs: dict[str, Any] = {
        "endpoint": endpoint,
        "deployment_name": deployment,
    }

    api_key = os.getenv(AZURE_OPENAI_API_KEY_ENV)
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = AzureCliCredential()

    return client_kwargs


class InputRouterExecutor(Executor):
    """Routes incoming content submission to the analysis agent."""

    def __init__(self):
        super().__init__(id="input_router")

    @handler
    async def route_input(
        self,
        input_json: str,
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        """Parse input and create agent request."""
        data = json.loads(input_json) if isinstance(input_json, str) else input_json

        submission = ContentSubmission(
            content_id=data.get("content_id", "unknown"),
            title=data.get("title", "Untitled"),
            body=data.get("body", ""),
            author=data.get("author", "Anonymous"),
        )

        # Store submission in shared state for later retrieval
        await ctx.set_shared_state("current_submission", submission)

        # Create the agent request
        message = (
            f"Please analyze the following content for policy compliance:\n\n"
            f"Title: {submission.title}\n"
            f"Author: {submission.author}\n"
            f"Content:\n{submission.body}"
        )

        await ctx.send_message(
            AgentExecutorRequest(
                messages=[ChatMessage(Role.USER, text=message)],
                should_respond=True,
            )
        )


# ============================================================================
# Workflow Creation
# ============================================================================


def _create_workflow() -> Workflow:
    """Create the content moderation workflow with HITL."""
    client_kwargs = _build_client_kwargs()
    chat_client = AzureOpenAIChatClient(**client_kwargs)

    # Create the content analysis agent
    content_analyzer_agent = chat_client.create_agent(
        name=CONTENT_ANALYZER_AGENT_NAME,
        instructions=CONTENT_ANALYZER_INSTRUCTIONS,
        response_format=ContentAnalysisResult,
    )

    # Create executors
    input_router = InputRouterExecutor()
    content_analyzer_executor = ContentAnalyzerExecutor()
    human_review_executor = HumanReviewExecutor()
    publish_executor = PublishExecutor()

    # Build the workflow graph
    # Flow:
    #   input_router -> content_analyzer_agent -> content_analyzer_executor
    #   -> human_review_executor (HITL pause here) -> publish_executor
    workflow = (
        WorkflowBuilder()
        .set_start_executor(input_router)
        .add_edge(input_router, content_analyzer_agent)
        .add_edge(content_analyzer_agent, content_analyzer_executor)
        .add_edge(content_analyzer_executor, human_review_executor)
        .add_edge(human_review_executor, publish_executor)
        .build()
    )

    return workflow


# ============================================================================
# Application Entry Point
# ============================================================================


def launch(durable: bool = True) -> AgentFunctionApp | None:
    """Launch the function app or DevUI.
    
    Args:
        durable: If True, returns AgentFunctionApp for Azure Functions.
                 If False, launches DevUI for local MAF development.
    """
    if durable:
        # Azure Functions mode with Durable Functions
        # The app automatically provides HITL endpoints:
        # - POST /api/workflow/run - Start the workflow
        # - GET /api/workflow/status/{instanceId} - Check status and pending HITL requests
        # - POST /api/workflow/respond/{instanceId}/{requestId} - Send HITL response
        # - GET /api/health - Health check
        workflow = _create_workflow()
        app = AgentFunctionApp(workflow=workflow, enable_health_check=True)
        return app
    else:
        # Pure MAF mode with DevUI for local development
        from pathlib import Path

        from agent_framework.devui import serve
        from dotenv import load_dotenv

        env_path = Path(__file__).parent / ".env"
        load_dotenv(dotenv_path=env_path)

        logger.info("Starting Workflow HITL Sample in MAF mode")
        logger.info("Available at: http://localhost:8096")
        logger.info("\nThis workflow demonstrates:")
        logger.info("- Human-in-the-loop using request_info / @response_handler pattern")
        logger.info("- AI content analysis with structured output")
        logger.info("- Human approval workflow integration")
        logger.info("\nFlow: InputRouter -> ContentAnalyzer Agent -> HumanReview -> Publish")

        workflow = _create_workflow()
        serve(entities=[workflow], port=8096, auto_open=True)

        return None


# Default: Azure Functions mode
# Run with `python function_app.py --maf` for pure MAF mode with DevUI
app = launch(durable=True)


if __name__ == "__main__":
    import sys

    if "--maf" in sys.argv:
        # Run in pure MAF mode with DevUI
        launch(durable=False)
    else:
        print("Usage: python function_app.py --maf")
        print("  --maf    Run in pure MAF mode with DevUI (http://localhost:8096)")
        print("\nFor Azure Functions mode, use: func start")
