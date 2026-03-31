# Copyright (c) Microsoft. All rights reserved.

"""Evaluate a multi-agent workflow with per-agent breakdown.

Demonstrates workflow evaluation:
1. Build a simple two-agent workflow
2. Run evaluate_workflow() which runs the workflow and evaluates each agent
3. Inspect per-agent results in sub_results

Usage:
    uv run python samples/03-workflows/evaluation/evaluate_workflow.py
"""

import asyncio
import os

from agent_framework import (
    Agent,
    LocalEvaluator,
    WorkflowBuilder,
    evaluate_workflow,
    evaluator,
    keyword_check,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


@evaluator
def is_nonempty(response: str) -> bool:
    """Check the agent produced a non-trivial response."""
    return len(response.strip()) > 5


async def main() -> None:
    # Build a simple planner -> executor workflow
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-4o"),
        credential=AzureCliCredential(),
    )
    planner = Agent(client=client, name="planner", instructions="You plan trips. Output a bullet-point plan.")
    executor_agent = Agent(
        client=client, name="executor", instructions="You execute travel plans. Book the items listed."
    )

    workflow = WorkflowBuilder(start_executor=planner).add_edge(planner, executor_agent).build()

    # Evaluate with per-agent breakdown
    local = LocalEvaluator(is_nonempty, keyword_check("plan", "trip"))

    results = await evaluate_workflow(
        workflow=workflow,
        queries=["Plan a weekend trip to Paris"],
        evaluators=local,
    )

    for r in results:
        print(f"{r.provider}: {r.passed}/{r.total} passed (overall)")
        for agent_name, sub in r.sub_results.items():
            error = f" (error: {sub.error})" if sub.error else ""
            print(f"  {agent_name}: {sub.passed}/{sub.total} {error}")


if __name__ == "__main__":
    asyncio.run(main())
