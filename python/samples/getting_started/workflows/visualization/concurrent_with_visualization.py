# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunEvent,
    ChatAgent,
    ChatMessage,
    Executor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowViz,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from typing_extensions import Never

"""
Sample: Concurrent (Fan-out/Fan-in) with Agents + Visualization

What it does:
- Fan-out: dispatch the same prompt to multiple domain agents (research, marketing, legal).
- Fan-in: aggregate their responses into one consolidated output.
- Visualization: generate Mermaid and GraphViz representations via `WorkflowViz` and optionally export SVG.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureOpenAIChatClient` agents.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
- For visualization export: `pip install graphviz>=0.20.0` and install GraphViz binaries.
"""


class DispatchToExperts(Executor):
    """Dispatches the incoming prompt to all expert agent executors (fan-out)."""

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        # Wrap the incoming prompt as a user message for each expert and request a response.
        initial_message = ChatMessage(Role.USER, text=prompt)
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
        # Map responses to text by executor id for a simple, predictable demo.
        by_id: dict[str, str] = {}
        for r in results:
            # AgentExecutorResponse.agent_run_response.text contains concatenated assistant text
            by_id[r.executor_id] = r.agent_run_response.text

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


def create_researcher_agent() -> ChatAgent:
    """Creates a research domain expert agent."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions=(
            "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
            " opportunities, and risks."
        ),
        name="researcher",
    )


def create_marketer_agent() -> ChatAgent:
    """Creates a marketing domain expert agent."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions=(
            "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
            " aligned to the prompt."
        ),
        name="marketer",
    )


def create_legal_agent() -> ChatAgent:
    """Creates a legal domain expert agent."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions=(
            "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
            " based on the prompt."
        ),
        name="legal",
    )


async def main() -> None:
    """Build and run the concurrent workflow with visualization."""

    # 1) Build a simple fan-out/fan-in workflow
    workflow = (
        WorkflowBuilder()
        .register_agent(create_researcher_agent, name="researcher")
        .register_agent(create_marketer_agent, name="marketer")
        .register_agent(create_legal_agent, name="legal")
        .register_executor(lambda: DispatchToExperts(id="dispatcher"), name="dispatcher")
        .register_executor(lambda: AggregateInsights(id="aggregator"), name="aggregator")
        .set_start_executor("dispatcher")
        .add_fan_out_edges("dispatcher", ["researcher", "marketer", "legal"])
        .add_fan_in_edges(["researcher", "marketer", "legal"], "aggregator")
        .build()
    )

    # 1.5) Generate workflow visualization
    print("Generating workflow visualization...")
    viz = WorkflowViz(workflow)
    # Print out the mermaid string.
    print("Mermaid string: \n=======")
    print(viz.to_mermaid())
    print("=======")
    # Print out the DiGraph string.
    print("DiGraph string: \n=======")
    print(viz.to_digraph())
    print("=======")

    # Export the DiGraph visualization as SVG.
    svg_file = viz.export(format="svg")
    print(f"SVG file saved to: {svg_file}")

    # 2) Run with a single prompt
    async for event in workflow.run_stream("We are launching a new budget-friendly electric bike for urban commuters."):
        if isinstance(event, AgentRunEvent):
            # Show which agent ran and what step completed.
            print(event)
        elif isinstance(event, WorkflowOutputEvent):
            print("===== Final Aggregated Output =====")
            print(event.data)


if __name__ == "__main__":
    asyncio.run(main())
