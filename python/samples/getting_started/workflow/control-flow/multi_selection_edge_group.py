# Copyright (c) Microsoft. All rights reserved.

"""Step 06b — Multi-Selection Edge Group sample."""

import asyncio
import os
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowOutputEvent,
    executor,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
Sample: Multi-Selection Edge Group for email triage and response.

The workflow stores an email,
classifies it as NotSpam, Spam, or Uncertain, and then routes to one or more branches.
Non-spam emails are drafted into replies, long ones are also summarized, spam is blocked, and uncertain cases are
flagged. Each path ends with simulated database persistence. The workflow completes when it becomes idle.

Purpose:
Demonstrate how to use a multi-selection edge group to fan out from one executor to multiple possible targets.
Show how to:
- Implement a selection function that chooses one or more downstream branches based on analysis.
- Share state across branches so different executors can read the same email content.
- Validate agent outputs with Pydantic models for robust structured data exchange.
- Merge results from multiple branches (e.g., a summary) back into a typed state.
- Apply conditional persistence logic (short vs long emails).

Prerequisites:
- Familiarity with WorkflowBuilder, executors, edges, and events.
- Understanding of multi-selection edge groups and how their selection function maps to target ids.
- Experience with shared state in workflows for persisting and reusing objects.
"""


EMAIL_STATE_PREFIX = "email:"
CURRENT_EMAIL_ID_KEY = "current_email_id"
LONG_EMAIL_THRESHOLD = 100


class AnalysisResultAgent(BaseModel):
    spam_decision: Literal["NotSpam", "Spam", "Uncertain"]
    reason: str


class EmailResponse(BaseModel):
    response: str


class EmailSummaryModel(BaseModel):
    summary: str


@dataclass
class Email:
    email_id: str
    email_content: str


@dataclass
class AnalysisResult:
    spam_decision: str
    reason: str
    email_length: int
    email_summary: str
    email_id: str


class DatabaseEvent(WorkflowEvent): ...


@executor(id="store_email")
async def store_email(email_text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    new_email = Email(email_id=str(uuid4()), email_content=email_text)
    await ctx.set_shared_state(f"{EMAIL_STATE_PREFIX}{new_email.email_id}", new_email)
    await ctx.set_shared_state(CURRENT_EMAIL_ID_KEY, new_email.email_id)

    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=new_email.email_content)], should_respond=True)
    )


@executor(id="to_analysis_result")
async def to_analysis_result(response: AgentExecutorResponse, ctx: WorkflowContext[AnalysisResult]) -> None:
    parsed = AnalysisResultAgent.model_validate_json(response.agent_run_response.text)
    email_id: str = await ctx.get_shared_state(CURRENT_EMAIL_ID_KEY)
    email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{email_id}")
    await ctx.send_message(
        AnalysisResult(
            spam_decision=parsed.spam_decision,
            reason=parsed.reason,
            email_length=len(email.email_content),
            email_summary="",
            email_id=email_id,
        )
    )


@executor(id="submit_to_email_assistant")
async def submit_to_email_assistant(analysis: AnalysisResult, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    if analysis.spam_decision != "NotSpam":
        raise RuntimeError("This executor should only handle NotSpam messages.")

    email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{analysis.email_id}")
    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=email.email_content)], should_respond=True)
    )


@executor(id="finalize_and_send")
async def finalize_and_send(response: AgentExecutorResponse, ctx: WorkflowContext[Never, str]) -> None:
    parsed = EmailResponse.model_validate_json(response.agent_run_response.text)
    await ctx.yield_output(f"Email sent: {parsed.response}")


@executor(id="summarize_email")
async def summarize_email(analysis: AnalysisResult, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
    # Only called for long NotSpam emails by selection_func
    email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{analysis.email_id}")
    await ctx.send_message(
        AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=email.email_content)], should_respond=True)
    )


@executor(id="merge_summary")
async def merge_summary(response: AgentExecutorResponse, ctx: WorkflowContext[AnalysisResult]) -> None:
    summary = EmailSummaryModel.model_validate_json(response.agent_run_response.text)
    email_id: str = await ctx.get_shared_state(CURRENT_EMAIL_ID_KEY)
    email: Email = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{email_id}")
    # Build an AnalysisResult mirroring to_analysis_result but with summary
    await ctx.send_message(
        AnalysisResult(
            spam_decision="NotSpam",
            reason="",
            email_length=len(email.email_content),
            email_summary=summary.summary,
            email_id=email_id,
        )
    )


@executor(id="handle_spam")
async def handle_spam(analysis: AnalysisResult, ctx: WorkflowContext[Never, str]) -> None:
    if analysis.spam_decision == "Spam":
        await ctx.yield_output(f"Email marked as spam: {analysis.reason}")
    else:
        raise RuntimeError("This executor should only handle Spam messages.")


@executor(id="handle_uncertain")
async def handle_uncertain(analysis: AnalysisResult, ctx: WorkflowContext[Never, str]) -> None:
    if analysis.spam_decision == "Uncertain":
        email: Email | None = await ctx.get_shared_state(f"{EMAIL_STATE_PREFIX}{analysis.email_id}")
        await ctx.yield_output(
            f"Email marked as uncertain: {analysis.reason}. Email content: {getattr(email, 'email_content', '')}"
        )
    else:
        raise RuntimeError("This executor should only handle Uncertain messages.")


@executor(id="database_access")
async def database_access(analysis: AnalysisResult, ctx: WorkflowContext[Never, str]) -> None:
    # Simulate DB writes for email and analysis (and summary if present)
    await asyncio.sleep(0.05)
    await ctx.add_event(DatabaseEvent(f"Email {analysis.email_id} saved to database."))


async def main() -> None:
    # Agents
    chat_client = AzureChatClient(credential=AzureCliCredential())

    email_analysis_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are a spam detection assistant that identifies spam emails. "
                "Always return JSON with fields 'spam_decision' (one of NotSpam, Spam, Uncertain) "
                "and 'reason' (string)."
            ),
            response_format=AnalysisResultAgent,
        ),
        id="email_analysis_agent",
    )

    email_assistant_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You are an email assistant that helps users draft responses to emails with professionalism."
            ),
            response_format=EmailResponse,
        ),
        id="email_assistant_agent",
    )

    email_summary_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=("You are an assistant that helps users summarize emails."),
            response_format=EmailSummaryModel,
        ),
        id="email_summary_agent",
    )

    # Build the workflow
    def select_targets(analysis: AnalysisResult, target_ids: list[str]) -> list[str]:
        # Order: [handle_spam, submit_to_email_assistant, summarize_email, handle_uncertain]
        handle_spam_id, submit_to_email_assistant_id, summarize_email_id, handle_uncertain_id = target_ids
        if analysis.spam_decision == "Spam":
            return [handle_spam_id]
        if analysis.spam_decision == "NotSpam":
            targets = [submit_to_email_assistant_id]
            if analysis.email_length > LONG_EMAIL_THRESHOLD:
                targets.append(summarize_email_id)
            return targets
        return [handle_uncertain_id]

    workflow = (
        WorkflowBuilder()
        .set_start_executor(store_email)
        .add_edge(store_email, email_analysis_agent)
        .add_edge(email_analysis_agent, to_analysis_result)
        .add_multi_selection_edge_group(
            to_analysis_result,
            [handle_spam, submit_to_email_assistant, summarize_email, handle_uncertain],
            selection_func=select_targets,
        )
        .add_edge(submit_to_email_assistant, email_assistant_agent)
        .add_edge(email_assistant_agent, finalize_and_send)
        .add_edge(summarize_email, email_summary_agent)
        .add_edge(email_summary_agent, merge_summary)
        # Save to DB if short (no summary path)
        .add_edge(to_analysis_result, database_access, condition=lambda r: r.email_length <= LONG_EMAIL_THRESHOLD)
        # Save to DB with summary when long
        .add_edge(merge_summary, database_access)
        .build()
    )

    # Read an email sample
    resources_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
        "resources",
        "email.txt",
    )
    if os.path.exists(resources_path):
        with open(resources_path, encoding="utf-8") as f:  # noqa: ASYNC230
            email = f.read()
    else:
        print("Unable to find resource file, using default text.")
        email = "Hello team, here are the updates for this week..."

    # Print outputs and database events from streaming
    async for event in workflow.run_stream(email):
        if isinstance(event, DatabaseEvent):
            print(f"{event}")
        elif isinstance(event, WorkflowOutputEvent):
            print(f"Workflow output: {event.data}")

    """
    Sample Output:

    DatabaseEvent(data=Email 32021432-2d4e-4c54-b04c-f81b4120340c saved to database.)
    Workflow output: Email sent: Hi Alex,

    Thank you for summarizing the action items from this morning's meeting.
    I have noted the three tasks and will begin working on them right away.
    I'll aim to have the updated project timeline ready by Friday and will
    coordinate with the team to schedule the client presentation for next week.
    I'll also review the Q4 budget allocation and share my feedback soon.

    If anything else comes up, please let me know.

    Best regards,
    Sarah
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
