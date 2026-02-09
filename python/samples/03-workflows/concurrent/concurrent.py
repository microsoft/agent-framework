# Copyright (c) Microsoft. All rights reserved.

"""
Concurrent (Fan-out/Fan-in) Workflow Sample

Demonstrates parallel execution by dispatching a prompt to multiple domain
agents simultaneously and aggregating their responses.

What you'll learn:
- Fan-out: dispatch to multiple agents from one executor
- Fan-in: collect and aggregate parallel responses
- Using add_fan_out_edges / add_fan_in_edges

Related samples:
- ../sequential/ — Linear step-by-step workflows
- ../visualization/ — Visualize concurrent workflow execution

Docs: https://learn.microsoft.com/agent-framework/workflows/overview
"""

import asyncio
from dataclasses import dataclass

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatAgent,
    ChatMessage,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from typing_extensions import Never


# <step_definitions>
class DispatchToExperts(Executor):
    """Dispatches the incoming prompt to all expert agent executors for parallel processing (fan-out)."""

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        initial_message = ChatMessage("user", text=prompt)
        await ctx.send_message(AgentExecutorRequest(messages=[initial_message], should_respond=True))


@dataclass
class AggregatedInsights:
    """Typed container for per-domain strings before formatting."""

    research: str
    marketing: str
    legal: str


class AggregateInsights(Executor):
    """Aggregates expert agent responses into a single consolidated result (fan-in)."""

    @handler
    async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
        by_id: dict[str, str] = {}
        for r in results:
            by_id[r.executor_id] = r.agent_response.text

        aggregated = AggregatedInsights(
            research=by_id.get("researcher", ""),
            marketing=by_id.get("marketer", ""),
            legal=by_id.get("legal", ""),
        )

        consolidated = (
            "Consolidated Insights\n"
            "====================\n\n"
            f"Research Findings:\n{aggregated.research}\n\n"
            f"Marketing Angle:\n{aggregated.marketing}\n\n"
            f"Legal/Compliance Notes:\n{aggregated.legal}\n"
        )

        await ctx.yield_output(consolidated)
# </step_definitions>


def create_researcher_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
            " opportunities, and risks."
        ),
        name="researcher",
    )


def create_marketer_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
            " aligned to the prompt."
        ),
        name="marketer",
    )


def create_legal_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
            " based on the prompt."
        ),
        name="legal",
    )


# <workflow_definition>
async def main() -> None:
    workflow = (
        WorkflowBuilder(start_executor="dispatcher")
        .register_agent(create_researcher_agent, name="researcher")
        .register_agent(create_marketer_agent, name="marketer")
        .register_agent(create_legal_agent, name="legal")
        .register_executor(lambda: DispatchToExperts(id="dispatcher"), name="dispatcher")
        .register_executor(lambda: AggregateInsights(id="aggregator"), name="aggregator")
        .add_fan_out_edges("dispatcher", ["researcher", "marketer", "legal"])
        .add_fan_in_edges(["researcher", "marketer", "legal"], "aggregator")
        .build()
    )
# </workflow_definition>

    # <running>
    async for event in workflow.run(
        "We are launching a new budget-friendly electric bike for urban commuters.", stream=True
    ):
        if event.type == "executor_invoked":
            print(f"{event.executor_id} invoked")
        elif event.type == "executor_completed":
            print(f"{event.executor_id} completed")
        elif event.type == "output":
            print("===== Final Aggregated Output =====")
            print(event.data)
    # </running>


if __name__ == "__main__":
    asyncio.run(main())
