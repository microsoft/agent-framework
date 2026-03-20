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

from agent_framework import (
    Agent,
    LocalEvaluator,
    WorkflowBuilder,
    evaluate_workflow,
    evaluator,
    keyword_check,
)


@evaluator
def is_nonempty(response: str) -> bool:
    """Check the agent produced a non-trivial response."""
    return len(response.strip()) > 5


async def main():
    # Build a simple planner → executor workflow
    planner = Agent(model="gpt-4o-mini", instructions="You plan trips. Output a bullet-point plan.")
    executor_agent = Agent(model="gpt-4o-mini", instructions="You execute travel plans. Book the items listed.")

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
            print(f"  {agent_name}: {sub.passed}/{sub.total}")


if __name__ == "__main__":
    asyncio.run(main())
