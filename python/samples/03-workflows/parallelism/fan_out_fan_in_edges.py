# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from dataclasses import dataclass

from agent_framework import (
    AgentExecutor,  # Wraps a ChatAgent as an Executor for use in workflows
    AgentExecutorRequest,  # The message bundle sent to an AgentExecutor
    AgentExecutorResponse,  # The structured result returned by an AgentExecutor
    AgentResponseUpdate,
    Executor,  # Base class for custom Python executors
    Message,  # Chat message structure
    WorkflowBuilder,  # Fluent builder for wiring the workflow graph
    WorkflowContext,  # Per run context and event bus
    handler,  # Decorator to mark an Executor method as invokable
)
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential  # Uses your az CLI login for credentials
from dotenv import load_dotenv
from typing_extensions import Never

# Load environment variables from .env file
load_dotenv()

"""
Sample: Concurrent fan out and fan in with three domain agents

A dispatcher fans out the same user prompt to research, marketing, and legal AgentExecutor nodes.
An aggregator then fans in their responses and produces a single consolidated report.

Purpose:
Show how to construct a parallel branch pattern in workflows. Demonstrate:
- Fan out by targeting multiple AgentExecutor nodes from one dispatcher.
- Fan in by collecting a list of AgentExecutorResponse objects and reducing them to a single result.

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Familiarity with WorkflowBuilder, executors, edges, events, and streaming runs.
- Azure OpenAI access configured for AzureOpenAIResponsesClient. Log in with Azure CLI and set any required environment variables.
- Comfort reading AgentExecutorResponse.agent_response.text for assistant output aggregation.
"""


class DispatchToExperts(Executor):
    """Dispatches the incoming prompt to all expert agent executors for parallel processing (fan out)."""

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        # Wrap the incoming prompt as a user message for each expert and request a response.
        initial_message = Message("user", text=prompt)
        await ctx.send_message(AgentExecutorRequest(messages=[initial_message], should_respond=True))


@dataclass
class AggregatedInsights:
    """Typed container for the aggregator to hold per domain strings before formatting."""

    research: str
    marketing: str
    legal: str


class AggregateInsights(Executor):
    """Aggregates expert agent responses into a single consolidated result (fan in)."""

    @handler
    async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
        # Map responses to text by executor id for a simple, predictable demo.
        by_id: dict[str, str] = {}
        for r in results:
            # AgentExecutorResponse.agent_response.text is the assistant text produced by the agent.
            by_id[r.executor_id] = r.agent_response.text

        research_text = by_id.get("researcher", "")
        marketing_text = by_id.get("marketer", "")
        legal_text = by_id.get("legal", "")

        aggregated = AggregatedInsights(
            research=research_text,
            marketing=marketing_text,
            legal=legal_text,
        )

        # Provide a readable, consolidated string as the final workflow result.
        consolidated = (
            "Consolidated Insights\n"
            "====================\n\n"
            f"Research Findings:\n{aggregated.research}\n\n"
            f"Marketing Angle:\n{aggregated.marketing}\n\n"
            f"Legal/Compliance Notes:\n{aggregated.legal}\n"
        )

        await ctx.yield_output(consolidated)


def render_live_streams(buffers: dict[str, str], order: list[str], completed: set[str]) -> None:
    """Render concurrent agent streams in separate sections."""
    # Clear terminal and move cursor to top-left for a live dashboard effect.
    print("\033[2J\033[H", end="")
    print("=== Expert Streams (Live) ===")
    print("Concurrent agent updates are shown below as they stream.\n")
    for agent_id in order:
        state = "completed" if agent_id in completed else "streaming"
        print(f"[{agent_id}] ({state})")
        print(buffers.get(agent_id, ""))
        print("-" * 80)
    print("", end="", flush=True)


async def main() -> None:
    # 1) Create executor and agent instances
    dispatcher = DispatchToExperts(id="dispatcher")
    aggregator = AggregateInsights(id="aggregator")

    researcher = AgentExecutor(
        AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ).as_agent(
            instructions=(
                "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
                " opportunities, and risks."
            ),
            name="researcher",
        )
    )
    marketer = AgentExecutor(
        AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ).as_agent(
            instructions=(
                "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
                " aligned to the prompt."
            ),
            name="marketer",
        )
    )
    legal = AgentExecutor(
        AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        ).as_agent(
            instructions=(
                "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
                " based on the prompt."
            ),
            name="legal",
        )
    )

    # 2) Build a simple fan out and fan in workflow
    workflow = (
        WorkflowBuilder(start_executor=dispatcher)
        .add_fan_out_edges(dispatcher, [researcher, marketer, legal])  # Parallel branches
        .add_fan_in_edges([researcher, marketer, legal], aggregator)  # Join at the aggregator
        .build()
    )

    # 3) Run with a single prompt and render live expert streams plus final consolidated output.
    expert_order = ["researcher", "marketer", "legal"]
    expert_buffers: dict[str, str] = {expert_id: "" for expert_id in expert_order}
    completed_experts: set[str] = set()
    final_output: str | None = None

    async for event in workflow.run(
        "We are launching a new budget-friendly electric bike for urban commuters.", stream=True
    ):
        if event.type == "executor_completed" and event.executor_id in expert_buffers:
            completed_experts.add(event.executor_id)
            render_live_streams(expert_buffers, expert_order, completed_experts)
        elif event.type == "output":
            if isinstance(event.data, AgentResponseUpdate):
                executor_id = event.executor_id or ""
                if executor_id in expert_buffers:
                    expert_buffers[executor_id] += event.data.text
                    render_live_streams(expert_buffers, expert_order, completed_experts)
                continue

            if event.executor_id == "aggregator":
                final_output = str(event.data)

    if final_output:
        print("\n=== Final Consolidated Output ===\n")
        print(final_output)


if __name__ == "__main__":
    asyncio.run(main())
