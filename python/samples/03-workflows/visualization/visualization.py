# Copyright (c) Microsoft. All rights reserved.

"""
Workflow Visualization Sample

Demonstrates generating Mermaid and GraphViz visualizations of workflow graphs.
Uses a concurrent fan-out/fan-in workflow to show the visualization output.

What you'll learn:
- Using WorkflowViz to visualize workflow graphs
- Generating Mermaid and DiGraph string representations
- Exporting workflow diagrams as SVG

Related samples:
- ../concurrent/ — Fan-out/fan-in parallel execution (same pattern, with execution)

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
    WorkflowViz,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from typing_extensions import Never


# <step_definitions>
class DispatchToExperts(Executor):
    """Dispatches the incoming prompt to all expert agent executors (fan-out)."""

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        initial_message = ChatMessage("user", text=prompt)
        await ctx.send_message(AgentExecutorRequest(messages=[initial_message], should_respond=True))


@dataclass
class AggregatedInsights:
    """Structured output from the aggregator."""

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
    """Build the concurrent workflow and generate visualizations."""
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
    print("Generating workflow visualization...")
    viz = WorkflowViz(workflow)

    print("Mermaid string: \n=======")
    print(viz.to_mermaid())
    print("=======")

    print("DiGraph string: \n=======")
    print(viz.to_digraph(include_internal_executors=True))
    print("=======")

    svg_file = viz.export(format="svg")
    print(f"SVG file saved to: {svg_file}")
    # </running>


if __name__ == "__main__":
    asyncio.run(main())
