# Copyright (c) Microsoft. All rights reserved.

"""Evaluate agent responses that already exist in Foundry (zero-code-change).

This sample demonstrates two patterns:
1. evaluate_traces(response_ids=...) — Evaluate specific Responses API responses by ID.
2. evaluate_traces(agent_id=...) — Evaluate agent behavior from OTel traces in App Insights.

These are the "zero-code-change" evaluation paths — the agent has already run,
and you're evaluating what happened after the fact.

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Response IDs from prior agent runs (for Pattern 1)
- OTel traces exported to App Insights (for Pattern 2)
- Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL in .env
"""

import asyncio
import os

from agent_framework.foundry import FoundryChatClient, FoundryEvals, evaluate_traces
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    # 1. Set up the chat client
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-4o"),
        credential=AzureCliCredential(),
    )

    # =========================================================================
    # Pattern 1: evaluate_traces(response_ids=...) — By response ID
    # =========================================================================
    # If your agent uses the Responses API (e.g., FoundryChatClient),
    # each run produces a response_id. Pass those IDs to evaluate_traces()
    # and Foundry retrieves the full conversation for evaluation.
    print("=" * 60)
    print("Pattern 1: evaluate_traces(response_ids=...)")
    print("=" * 60)

    # Replace these with actual response IDs from your agent runs
    response_ids = [
        "resp_abc123",
        "resp_def456",
    ]

    results = await evaluate_traces(
        response_ids=response_ids,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.GROUNDEDNESS, FoundryEvals.TOOL_CALL_ACCURACY],
        client=chat_client,
    )

    print(f"Status: {results.status}")
    print(f"Results: {results.result_counts}")
    print(f"Portal: {results.report_url}")

    # =========================================================================
    # Pattern 2: evaluate_traces(response_ids=...) — Batch response evaluation
    # =========================================================================
    # Evaluate multiple prior responses by their IDs.  This uses the same
    # response-based data source under the covers but lets you batch them.
    #
    # A future trace-based pattern (agent_id + lookback_hours) is shown
    # commented out below — it requires OTel traces exported to App Insights.
    print()
    print("=" * 60)
    print("Pattern 2: evaluate_traces(response_ids=...)")
    print("=" * 60)

    # Evaluate by response IDs (uses response-based data source internally)
    results = await evaluate_traces(
        response_ids=response_ids,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        client=chat_client,
    )

    print(f"Status: {results.status}")
    print(f"Portal: {results.report_url}")

    # Evaluate by agent ID + time window (when trace-based API is available)
    # results = await evaluate_traces(
    #     agent_id="travel-bot",
    #     evaluators=[FoundryEvals.INTENT_RESOLUTION, FoundryEvals.TASK_ADHERENCE],
    #     client=chat_client,
    #     lookback_hours=24,
    # )


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (with actual Azure AI Foundry project and valid response IDs):

============================================================
Pattern 1: evaluate_traces(response_ids=...)
============================================================
Status: completed
Results: {'passed': 2, 'failed': 0, 'errored': 0}
Portal: https://ai.azure.com/...

============================================================
Pattern 2: evaluate_traces(response_ids=...)
============================================================
Status: completed
Portal: https://ai.azure.com/...
"""
