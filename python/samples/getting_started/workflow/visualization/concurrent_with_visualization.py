# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunEvent,
    ChatMessage,
    Executor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowViz,
    handler,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Sample: Concurrent (Fan-out/Fan-in) with Agents + Visualization

What it does:
- Fan-out: dispatch the same prompt to multiple domain agents (research, marketing, legal).
- Fan-in: aggregate their responses into one consolidated output.
- Visualization: generate Mermaid and GraphViz representations via `WorkflowViz` and optionally export SVG.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` agents.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
- For visualization export: `pip install agent-framework[viz]` and install GraphViz binaries.
"""


class DispatchToExperts(Executor):
    """Dispatches the incoming prompt to all expert agent executors (fan-out)."""

    def __init__(self, expert_ids: list[str], id: str | None = None):
        super().__init__(id=id or "dispatch_to_experts")
        self._expert_ids = expert_ids

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        # Wrap the incoming prompt as a user message for each expert and request a response.
        initial_message = ChatMessage(Role.USER, text=prompt)
        for expert_id in self._expert_ids:
            await ctx.send_message(
                AgentExecutorRequest(messages=[initial_message], should_respond=True),
                target_id=expert_id,
            )


@dataclass
class AggregatedInsights:
    """Structured output from the aggregator."""

    research: str
    marketing: str
    legal: str


class AggregateInsights(Executor):
    """Aggregates expert agent responses into a single consolidated result (fan-in)."""

    def __init__(self, expert_ids: list[str], id: str | None = None):
        super().__init__(id=id or "aggregate_insights")
        self._expert_ids = expert_ids

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


async def main() -> None:
    # 1) Create agent executors for domain experts
    chat_client = AzureChatClient(credential=AzureCliCredential())

    researcher = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
                " opportunities, and risks."
            ),
        ),
        id="researcher",
    )
    marketer = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
                " aligned to the prompt."
            ),
        ),
        id="marketer",
    )
    legal = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
                " based on the prompt."
            ),
        ),
        id="legal",
    )

    expert_ids = [researcher.id, marketer.id, legal.id]

    dispatcher = DispatchToExperts(expert_ids=expert_ids, id="dispatcher")
    aggregator = AggregateInsights(expert_ids=expert_ids, id="aggregator")

    # 2) Build a simple fan-out/fan-in workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(dispatcher)
        .add_fan_out_edges(dispatcher, [researcher, marketer, legal])
        .add_fan_in_edges([researcher, marketer, legal], aggregator)
        .build()
    )

    # 2.5) Generate workflow visualization
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
    try:
        # Export the DiGraph visualization as SVG.
        svg_file = viz.export(format="svg")
        print(f"SVG file saved to: {svg_file}")
    except ImportError:
        print("Tip: Install 'viz' extra to export workflow visualization: pip install agent-framework[viz]")

    # 3) Run with a single prompt
    async for event in workflow.run_stream("We are launching a new budget-friendly electric bike for urban commuters."):
        if isinstance(event, AgentRunEvent):
            # Show which agent ran and what step completed.
            print(event)
        elif isinstance(event, WorkflowOutputEvent):
            print("===== Final Aggregated Output =====")
            print(event.data)


if __name__ == "__main__":
    asyncio.run(main())
