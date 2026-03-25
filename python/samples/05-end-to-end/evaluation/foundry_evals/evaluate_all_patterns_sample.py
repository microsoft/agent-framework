# Copyright (c) Microsoft. All rights reserved.

"""
Agent Evaluation — Complete Guide
==================================

This sample shows every way to evaluate agents and workflows in
Microsoft Agent Framework. Run the sections that match your needs.

                    ┌──────────────────────────────────────┐
                    │         Evaluation Options            │
                    ├──────────────────────────────────────┤
                    │                                      │
                    │  1. Your own function  (no setup)    │
                    │  2. Built-in checks   (no setup)     │
                    │  3. Azure AI Foundry  (cloud)        │
                    │  4. Mix them all      (recommended)  │
                    │                                      │
                    └──────────────────────────────────────┘

Each evaluator plugs into the same two entry points:

    evaluate_agent()     — run agent + evaluate, or evaluate existing responses
    evaluate_workflow()  — evaluate multi-agent workflows with per-agent breakdown
"""

import asyncio
import os

from agent_framework import (
    Agent,
    LocalEvaluator,
    Message,
    Workflow,
    evaluate_agent,
    evaluate_workflow,
    evaluator,
    keyword_check,
    tool_called_check,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_ai import FoundryEvals
from agent_framework_orchestrations import GroupChatBuilder, SequentialBuilder
from azure.ai.projects.aio import AIProjectClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


# ── Tools for our agents ─────────────────────────────────────────────────────


def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return {"seattle": "62°F, cloudy", "london": "55°F, overcast", "paris": "68°F, sunny"}.get(
        location.lower(), f"No data for {location}"
    )


def get_flight_price(origin: str, destination: str) -> str:
    """Get the price of a flight between two cities."""
    return f"Flights from {origin} to {destination}: $450 round-trip"


# ── Output helpers ────────────────────────────────────────────────────────────


def print_workflow_results(results) -> None:
    """Print workflow eval results with clear provider → overall → per-agent hierarchy."""
    for r in results:
        status = "✓" if r.all_passed else "✗"
        print(f"\n  {r.provider}:")
        print(f"    {status} overall: {r.passed}/{r.total} passed")
        if r.report_url:
            print(f"      Portal: {r.report_url}")
        for agent_name, sub in r.sub_results.items():
            agent_status = "✓" if sub.all_passed else "✗"
            print(f"      {agent_status} {agent_name}: {sub.passed}/{sub.total}")
            if sub.report_url:
                print(f"        Portal: {sub.report_url}")


# ── Agent setup ───────────────────────────────────────────────────────────────


def create_agent(project_client, deployment) -> Agent:
    """Create a travel assistant agent."""
    return Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=deployment,
            credential=AzureCliCredential(),
        ),
        name="travel-assistant",
        instructions="You are a helpful travel assistant. Use your tools to answer questions.",
        tools=[get_weather, get_flight_price],
    )


def create_workflow(project_client, deployment) -> Workflow:
    """Create a researcher → planner sequential workflow."""
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=deployment,
        credential=AzureCliCredential(),
    )
    researcher = Agent(
        client=client,
        name="researcher",
        instructions="You are a travel researcher. Use tools to gather weather and flight info.",
        tools=[get_weather, get_flight_price],
        default_options={"store": False},
    )
    planner = Agent(
        client=client,
        name="planner",
        instructions="You are a travel planner. Create a concise recommendation from the research.",
        default_options={"store": False},
    )
    return SequentialBuilder(participants=[researcher, planner]).build()


# ═════════════════════════════════════════════════════════════════════════════
# Section 1: Custom Function Evaluators
# ═════════════════════════════════════════════════════════════════════════════
#
# Write a plain Python function. Name your parameters to get the data you need.
# Return bool, float (≥0.5 = pass), or dict.
#
#   Available parameters:
#     query, response, expected_output, conversation, tool_definitions, context
#

# ── Simple check: just query + response ──────────────────────────────────────


@evaluator
def is_helpful(response: str) -> bool:
    """Response should be more than a one-liner."""
    return len(response.split()) > 10


@evaluator
def no_apologies(query: str, response: str) -> bool:
    """Agent shouldn't start with 'I'm sorry' or 'I apologize'."""
    lower = response.lower().strip()
    return not lower.startswith("i'm sorry") and not lower.startswith("i apologize")


# ── Scored check: return a float ─────────────────────────────────────────────


@evaluator
def relevance_keyword_overlap(query: str, response: str) -> float:
    """Score based on how many query words appear in the response."""
    query_words = set(query.lower().split()) - {"the", "a", "in", "to", "is", "what", "how"}
    response_lower = response.lower()
    if not query_words:
        return 1.0
    return sum(1 for w in query_words if w in response_lower) / len(query_words)


# ── Ground truth check: compare against expected output ──────────────────────


@evaluator
def mentions_expected_city(response: str, expected_output: str) -> bool:
    """Response should mention the expected city."""
    return expected_output.lower() in response.lower()


# ── Full context check: inspect conversation and tools ───────────────────────


@evaluator
def used_available_tools(conversation: list, tools: list) -> dict:
    """Check that the agent actually called at least one of its tools."""
    available = {t.name for t in (tools or []) if hasattr(t, "name")}
    called = set()
    for msg in conversation:
        for c in getattr(msg, "contents", []) or []:
            if getattr(c, "type", None) == "function_call" and getattr(c, "name", None):
                called.add(c.name)
    used = called & available
    return {
        "passed": len(used) > 0,
        "reason": f"Used {sorted(used)}" if used else f"No tools called (available: {sorted(available)})",
    }


async def demo_evaluators(project_client, deployment) -> None:
    """Evaluate an agent with custom function evaluators."""
    print()
    print("═" * 60)
    print("  1. Custom Function Evaluators")
    print("═" * 60)

    agent = create_agent(project_client, deployment)

    local = LocalEvaluator(
        is_helpful,
        no_apologies,
        relevance_keyword_overlap,
        used_available_tools,
    )

    results = await evaluate_agent(
        agent=agent,
        queries=["What's the weather in Seattle?", "How much is a flight to Paris?"],
        evaluators=local,
    )

    for r in results:
        print(f"\n  {r.provider}: {r.passed}/{r.total} passed")
        for check, counts in r.per_evaluator.items():
            status = "✓" if counts["failed"] == 0 else "✗"
            print(f"    {status} {check}: {counts['passed']}/{counts['passed'] + counts['failed']}")


# ═════════════════════════════════════════════════════════════════════════════
# Section 2: Built-in Local Checks
# ═════════════════════════════════════════════════════════════════════════════
#
# Pre-built checks for common patterns — no function needed.
#


async def demo_builtin_checks(project_client, deployment) -> None:
    """Evaluate with built-in keyword and tool checks."""
    print()
    print("═" * 60)
    print("  2. Built-in Local Checks")
    print("═" * 60)

    agent = create_agent(project_client, deployment)

    local = LocalEvaluator(
        keyword_check("weather", "seattle"),  # response must contain these words
        tool_called_check("get_weather"),  # agent must have called this tool
    )

    results = await evaluate_agent(
        agent=agent,
        queries=["What's the weather in Seattle?"],
        evaluators=local,
    )

    for r in results:
        status = "✓" if r.all_passed else "✗"
        print(f"\n  {status} {r.provider}: {r.passed}/{r.total} passed")
        for check, counts in r.per_evaluator.items():
            print(f"    {check}: {counts}")


# ═════════════════════════════════════════════════════════════════════════════
# Section 3: Azure AI Foundry Evaluators
# ═════════════════════════════════════════════════════════════════════════════
#
# Cloud-powered AI quality assessment. Evaluates relevance, coherence,
# task adherence, tool usage, and more.
#


async def demo_foundry_agent(project_client, deployment) -> None:
    """Evaluate a single agent with Foundry."""
    print()
    print("═" * 60)
    print("  3a. Foundry — Single Agent")
    print("═" * 60)

    agent = create_agent(project_client, deployment)
    evals = FoundryEvals(project_client=project_client, model_deployment=deployment)

    # evaluate_agent: run + evaluate in one call
    results = await evaluate_agent(
        agent=agent,
        queries=["What's the weather in Seattle?", "Find flights from London to Paris"],
        evaluators=evals,
    )

    for r in results:
        print(f"\n  {r.provider}: {r.passed}/{r.total} passed")
        print(f"  Portal: {r.report_url}")


async def demo_foundry_response(project_client, deployment) -> None:
    """Evaluate a response you already have."""
    print()
    print("═" * 60)
    print("  3b. Foundry — Existing Response")
    print("═" * 60)

    agent = create_agent(project_client, deployment)

    # Run the agent yourself
    response = await agent.run([Message("user", ["What's the weather in Seattle?"])])
    print(f"  Agent said: {response.text[:80]}...")

    # Then evaluate the response (without re-running the agent)
    quality_evals = FoundryEvals(
        project_client=project_client,
        model_deployment=deployment,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
    )
    results = await evaluate_agent(
        agent=agent,
        responses=response,
        queries=["What's the weather in Seattle?"],
        evaluators=quality_evals,
    )

    for r in results:
        print(f"\n  {r.provider}: {r.passed}/{r.total} passed")


async def demo_foundry_workflow(project_client, deployment) -> None:
    """Evaluate a multi-agent workflow with per-agent breakdown."""
    print()
    print("═" * 60)
    print("  3c. Foundry — Multi-Agent Workflow")
    print("═" * 60)

    workflow = create_workflow(project_client, deployment)
    evals = FoundryEvals(project_client=project_client, model_deployment=deployment)

    # Run + evaluate with multiple queries
    results = await evaluate_workflow(
        workflow=workflow,
        queries=["Plan a trip from Seattle to Paris"],
        evaluators=evals,
    )

    print_workflow_results(results)


async def demo_foundry_select(project_client, deployment) -> None:
    """Choose specific Foundry evaluators."""
    print()
    print("═" * 60)
    print("  3d. Foundry — Selecting Evaluators")
    print("═" * 60)

    agent = create_agent(project_client, deployment)

    # Pick exactly which evaluators to run
    evals = FoundryEvals(
        project_client=project_client,
        model_deployment=deployment,
        evaluators=[
            FoundryEvals.RELEVANCE,
            FoundryEvals.TASK_ADHERENCE,
            FoundryEvals.TOOL_CALL_ACCURACY,
        ],
    )
    results = await evaluate_agent(
        agent=agent,
        queries=["What's the weather in Seattle?"],
        evaluators=evals,
    )

    for r in results:
        print(f"\n  {r.provider}: {r.passed}/{r.total} passed")
        for ev_name, counts in r.per_evaluator.items():
            print(f"    {ev_name}: {counts}")


# ═════════════════════════════════════════════════════════════════════════════
# Section 4: Mix Everything Together
# ═════════════════════════════════════════════════════════════════════════════
#
# Pass a list of evaluators — local functions, built-in checks, and Foundry
# all run together. You get one EvalResults per provider.
#


async def demo_mixed(project_client, deployment) -> None:
    """Combine custom functions, built-in checks, and Foundry in one call."""
    print()
    print("═" * 60)
    print("  4. Mixed Evaluation (recommended)")
    print("═" * 60)

    agent = create_agent(project_client, deployment)

    # Local: custom functions + built-in checks
    local = LocalEvaluator(
        is_helpful,
        no_apologies,
        keyword_check("weather"),
        tool_called_check("get_weather"),
    )

    # Cloud: Foundry AI quality assessment
    foundry = FoundryEvals(project_client=project_client, model_deployment=deployment)

    # One call, multiple providers
    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather in Seattle?",
            "How much is a flight from London to Paris?",
        ],
        evaluators=[local, foundry],
    )

    print()
    for r in results:
        status = "✓" if r.all_passed else "✗"
        print(f"  {status} {r.provider}: {r.passed}/{r.total} passed")
        for ev_name, counts in r.per_evaluator.items():
            p, f = counts["passed"], counts["failed"]
            print(f"      {ev_name}: {p}/{p + f}")
        if r.report_url:
            print(f"      Portal: {r.report_url}")

    # CI assertion — fails the test if anything didn't pass
    for r in results:
        r.assert_passed()
    print("\n  ✓ All evaluations passed!")


# ═════════════════════════════════════════════════════════════════════════════
# Section 5: Workflow + Mixed Evaluation
# ═════════════════════════════════════════════════════════════════════════════


async def demo_workflow_mixed(project_client, deployment) -> None:
    """Evaluate a workflow with both local and Foundry evaluators."""
    print()
    print("═" * 60)
    print("  5. Workflow + Mixed Evaluation")
    print("═" * 60)

    workflow = create_workflow(project_client, deployment)

    local = LocalEvaluator(is_helpful, no_apologies)
    foundry = FoundryEvals(project_client=project_client, model_deployment=deployment)

    results = await evaluate_workflow(
        workflow=workflow,
        queries=["Plan a trip from Seattle to Paris"],
        evaluators=[local, foundry],
    )

    print_workflow_results(results)


# ═════════════════════════════════════════════════════════════════════════════
# Section 6: Iterative Workflows (agents run multiple times)
# ═════════════════════════════════════════════════════════════════════════════
#
# When an agent runs multiple times in a single workflow execution (e.g., in
# a group chat or feedback loop), each invocation becomes a separate eval item.
# Results are grouped by agent, so you see e.g. "writer: 3/3 passed".
#


def create_iterative_workflow(project_client, deployment) -> Workflow:
    """Create a group chat where a writer and reviewer iterate.

    The writer drafts a response, the reviewer critiques it, and the
    writer revises — running 2 rounds so each agent is invoked twice.
    """
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=deployment,
        credential=AzureCliCredential(),
    )
    writer = Agent(
        client=client,
        name="writer",
        instructions=(
            "You are a travel copywriter. Write or revise a short, "
            "compelling travel description based on the conversation."
        ),
        default_options={"store": False},
    )
    reviewer = Agent(
        client=client,
        name="reviewer",
        instructions=("You are an editor. Critique the writer's draft and suggest specific improvements. Be concise."),
        default_options={"store": False},
    )

    # Group chat with round-robin selection: writer → reviewer → writer → reviewer
    # Each agent runs twice per query.
    def round_robin(state):
        names = list(state.participants.keys())
        return names[state.current_round % len(names)]

    return GroupChatBuilder(
        participants=[writer, reviewer],
        termination_condition=lambda conversation: len(conversation) >= 5,
        selection_func=round_robin,
    ).build()


async def demo_iterative_workflow(project_client, deployment) -> None:
    """Evaluate a workflow where agents run multiple times."""
    print()
    print("═" * 60)
    print("  6. Iterative Workflow (multi-run agents)")
    print("═" * 60)

    workflow = create_iterative_workflow(project_client, deployment)

    local = LocalEvaluator(is_helpful, no_apologies)

    results = await evaluate_workflow(
        workflow=workflow,
        queries=["Write a travel description for Kyoto in autumn"],
        evaluators=local,
    )

    print_workflow_results(results)


# ═════════════════════════════════════════════════════════════════════════════
# Run it
# ═════════════════════════════════════════════════════════════════════════════


async def main() -> None:
    project_client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=AzureCliCredential(),
    )
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    # Run each section — comment out what you don't need
    # await demo_evaluators(project_client, deployment)
    # await demo_builtin_checks(project_client, deployment)
    # await demo_foundry_agent(project_client, deployment)
    # await demo_foundry_response(project_client, deployment)
    # await demo_foundry_workflow(project_client, deployment)
    # await demo_foundry_select(project_client, deployment)
    # await demo_mixed(project_client, deployment)
    await demo_workflow_mixed(project_client, deployment)
    await demo_iterative_workflow(project_client, deployment)


if __name__ == "__main__":
    asyncio.run(main())
