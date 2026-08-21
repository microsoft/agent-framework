# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-foundry-hosting",
#     "agent-framework-purview",
#     "agent-framework-tools",
#     "agent-framework-monty",
#     "mcp",
#     "httpx",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Local and optional hosted Foundry evals for the production-ready claw.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT       — Microsoft Foundry project endpoint URL; also gates Foundry evals
    FOUNDRY_MODEL                  — Model deployment name for local eval runs (defaults to gpt-5.4)
    TOOLBOX_MCP_SERVER_URL         — Optional Foundry Toolbox MCP endpoint URL
    PURVIEW_CLIENT_APP_ID          — Optional app/client ID; enables Purview
    ENABLE_INSTRUMENTATION         — Controls Agent Framework instrumentation
    ENABLE_SENSITIVE_DATA          — Enables sensitive telemetry capture when true
    ENABLE_CONSOLE_EXPORTERS       — Enables console OpenTelemetry exporters when true
    OTEL_EXPORTER_OTLP_ENDPOINT    — Optional OTLP collector endpoint

Run:
    uv run --prerelease=allow python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready/evals.py
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from agent import build_claw_agent
from agent_framework import Agent, AgentResponse, LocalEvaluator, evaluate_agent, evaluator
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from agent_framework.observability import configure_otel_providers
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

FINANCE_EVAL_QUERIES = [
    "What's the capital of France? If this is off-topic, briefly redirect me to finance topics.",
    "Use the stock price tool to value MSFT numerically. Include price, trailing EPS, and P/E.",
    "Read portfolio.csv and summarize the portfolio tickers and approximate total position value.",
]


@evaluator(name="off_topic_refusal_lenient")
def off_topic_refusal_lenient(query: str, response: str) -> dict[str, object]:
    """Leniently check that off-topic questions are redirected toward finance."""
    if "capital of france" not in query.lower():
        return {"passed": True, "reason": "Not the off-topic eval item."}

    text = response.lower()
    markers = ["finance", "invest", "portfolio", "stock", "off-topic", "can't help", "not able"]
    passed = any(marker in text for marker in markers)
    return {"passed": passed, "reason": "Off-topic response redirects to finance." if passed else response[:160]}


@evaluator(name="numeric_valuation_answer")
def numeric_valuation_answer(query: str, response: str) -> dict[str, object]:
    """Check that valuation answers contain numeric content."""
    if "msft" not in query.lower():
        return {"passed": True, "reason": "Not the valuation eval item."}

    numbers = re.findall(r"\d+(?:\.\d+)?", response)
    passed = len(numbers) >= 2 and any(term in response.lower() for term in ("p/e", "pe", "price", "eps"))
    return {"passed": passed, "reason": f"Found {len(numbers)} numeric tokens."}


@evaluator(name="portfolio_grounding_runs_cleanly")
def portfolio_grounding_runs_cleanly(query: str, response: str) -> dict[str, object]:
    """Check that portfolio answers are grounded in the sample portfolio file."""
    if "portfolio.csv" not in query.lower():
        return {"passed": True, "reason": "Not the portfolio eval item."}

    text = response.lower()
    tickers = ["msft", "aapl", "nvda", "spy"]
    found = [ticker for ticker in tickers if ticker in text]
    passed = len(found) >= 2 and "error" not in text and "traceback" not in text
    return {"passed": passed, "reason": f"Found portfolio tickers: {found}."}


async def _run_queries(agent: Agent[Any], queries: list[str]) -> list[AgentResponse[Any]]:
    """Run each query on its own fresh session and collect the responses.

    The claw harness agent includes ``ToolApprovalMiddleware``, which requires an
    ``AgentSession``. ``evaluate_agent`` does not create one when it runs queries itself, so we run
    the agent here (one session per query) and hand the responses to ``evaluate_agent`` via
    ``responses=``. Skill scripts are auto-approved for this run (see ``main``), so a skill that
    runs a script completes instead of pausing on an approval request.
    """
    responses: list[AgentResponse[Any]] = []
    for query in queries:
        session = agent.create_session()
        responses.append(await agent.run(query, session=session))
    return responses


async def main() -> None:
    """Run local claw evals, then Foundry-hosted evals when configured."""
    load_dotenv()
    configure_otel_providers()

    credential = AzureCliCredential()
    # store=False keeps chat history client-side (managed by the harness InMemoryHistoryProvider)
    # instead of server-side on the Foundry service.
    agent = await build_claw_agent(
        credential=credential,
        default_options={"store": False},
        # The valuation skill's instructions tell the agent to run ``scripts/valuation_metrics.py``,
        # and ``run_skill_script`` requires approval by default — an unattended eval run would stop
        # at an approval request and score that instead of a real answer. This is eval-only:
        # ``place_trade``, the shell, and file writes keep their normal approval behavior.
        auto_approve_skill_scripts=True,
    )
    async with agent:
        local = LocalEvaluator(
            off_topic_refusal_lenient,
            numeric_valuation_answer,
            portfolio_grounding_runs_cleanly,
        )

        # Run the agent once (one session per query) and reuse the responses for every evaluator.
        responses = await _run_queries(agent, FINANCE_EVAL_QUERIES)

        results = await evaluate_agent(agent=agent, queries=FINANCE_EVAL_QUERIES, responses=responses, evaluators=local)
        print(f"Local evals: {results[0].passed}/{results[0].total} passed")
        for item in results[0].items:
            print(f"  [{item.status}] {(item.input_text or '')[:70]}")

        if not os.environ.get("FOUNDRY_PROJECT_ENDPOINT"):
            print("Foundry evals skipped. Set FOUNDRY_PROJECT_ENDPOINT to enable them.")
            return

        foundry = FoundryEvals(
            # Supply a credentialed client; otherwise FoundryEvals builds a FoundryChatClient with
            # no credential and fails. Endpoint and model resolve from FOUNDRY_PROJECT_ENDPOINT /
            # FOUNDRY_MODEL, matching the agent's own client.
            client=FoundryChatClient(credential=credential),
            evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        )
        hosted_results = await evaluate_agent(
            agent=agent,
            queries=FINANCE_EVAL_QUERIES,
            responses=responses,
            evaluators=foundry,
            eval_name="claw-step04-production-ready",
        )
        print(f"Foundry evals: {hosted_results[0].passed}/{hosted_results[0].total} passed")
        if hosted_results[0].report_url:
            print(f"Foundry report: {hosted_results[0].report_url}")


if __name__ == "__main__":
    asyncio.run(main())
