# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework_azure_ai import FoundryEvals, evaluate_traces
from azure.ai.projects.aio import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

"""
This sample demonstrates evaluating agent responses that already exist in Foundry.

It shows two patterns:
1. evaluate_traces(response_ids=...) — Evaluate specific Responses API responses by ID.
2. evaluate_traces(agent_id=...) — Evaluate agent behavior from OTel traces in App Insights.

These are the "zero-code-change" evaluation paths — the agent has already run,
and you're evaluating what happened after the fact.

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Response IDs from prior agent runs (for Pattern 1)
- OTel traces exported to App Insights (for Pattern 2)
- Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME in .env
"""


async def main():
    # 1. Set up the Azure AI project client
    project_client = AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )

    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    # =========================================================================
    # Pattern 1: evaluate_traces(response_ids=...) — By response ID
    # =========================================================================
    # If your agent uses the Responses API (e.g., AzureOpenAIResponsesClient),
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
        project_client=project_client,
        model_deployment=deployment,
    )

    print(f"Status: {results.status}")
    print(f"Results: {results.result_counts}")
    print(f"Portal: {results.report_url}")

    # =========================================================================
    # Pattern 2: evaluate_traces(agent_id=...) — From App Insights
    # =========================================================================
    # If your agent emits OTel traces to App Insights (via configure_otel_providers),
    # you can evaluate recent activity without specifying individual response IDs.
    #
    # NOTE: Requires OTel traces exported to the App Insights instance connected
    # to your Foundry project. The exact trace-based data source API is subject
    # to change as Foundry evolves.
    print()
    print("=" * 60)
    print("Pattern 2: evaluate_traces(agent_id=...)")
    print("=" * 60)

    # Evaluate by response IDs (uses response-based data source internally)
    results = await evaluate_traces(
        response_ids=response_ids,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        project_client=project_client,
        model_deployment=deployment,
    )

    print(f"Status: {results.status}")
    print(f"Portal: {results.report_url}")

    # Evaluate by agent ID + time window (when trace-based API is available)
    # results = await evaluate_traces(
    #     agent_id="travel-bot",
    #     evaluators=[FoundryEvals.INTENT_RESOLUTION, FoundryEvals.TASK_ADHERENCE],
    #     project_client=project_client,
    #     model_deployment=deployment,
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
Pattern 2: evaluate_traces(agent_id=...)
============================================================
Status: completed
Portal: https://ai.azure.com/...
"""
