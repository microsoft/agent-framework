# Copyright (c) Microsoft. All rights reserved.

"""Register a hand-authored rubric evaluator and use it in CI.

This sample demonstrates the *manual* counterpart to
``evaluate_with_generated_rubric_sample.py``:

1. Build an agent.
2. Author the rubric dimensions yourself — useful when you have an
   established scoring rubric (from a spec, a competing framework, or
   prior hand tuning) that you want to bring into Foundry as-is.
3. Register the rubric with
   :meth:`FoundryEvals.create_rubric_evaluator` — this maps directly to
   ``project_client.beta.evaluators.create_version`` and returns a
   pinned ``GeneratedEvaluatorRef`` you can store in source control.
4. Use the pinned reference in ``evaluators=[...]`` for a regression run
   alongside built-in evaluators.

The service auto-attaches a non-editable residual dimension
(``general_quality`` for ``category="quality"``,
``general_policy_compliance`` for ``"safety"``) — do not include it in
``dimensions``.

Prefer :meth:`FoundryEvals.generate_rubric` if you want Foundry to
draft the dimensions for you from the agent's context.  Use this manual
flow when you already know what you want to score.

Prerequisites:
- An Azure AI Foundry project with a deployed model.
- ``azure-ai-projects`` build that includes the rubric APIs (currently
  ``2.3.0a*`` on the Azure SDK Python dev feed).
- Set ``FOUNDRY_PROJECT_ENDPOINT`` and ``FOUNDRY_MODEL`` in ``.env``.

Run with:

.. code-block:: bash

    az login
    python evaluate_with_manual_rubric_sample.py
"""

import asyncio
import os

from agent_framework import evaluate_agent
from agent_framework.foundry import (
    FoundryChatClient,
    FoundryEvals,
    RubricDimension,
)
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    samples = {
        "seattle": "62F, cloudy with a chance of rain",
        "london": "55F, overcast",
        "paris": "68F, partly sunny",
    }
    return samples.get(location.lower(), f"Weather data not available for {location}")


# Hand-authored rubric — this is the artifact you commit alongside the
# agent so the rubric and the behavior it scores evolve together.
# Weights are 1-10 (the generation pipeline biases one dimension to
# 8-10; manual edits aren't constrained by this heuristic).
TRAVEL_RUBRIC_DIMENSIONS: list[RubricDimension] = [
    RubricDimension(
        id="tool_grounding",
        description=(
            "Grounds every weather claim in tool output.  Does not invent values when "
            "the tool returns no data, and does not paraphrase tool output in a way "
            "that distorts the underlying values."
        ),
        weight=9,
    ),
    RubricDimension(
        id="scope_adherence",
        description=(
            "Stays within travel-planning scope.  Politely declines or redirects "
            "questions about topics unrelated to travel (e.g. general trivia, "
            "personal advice, coding questions)."
        ),
        weight=6,
    ),
    RubricDimension(
        id="actionable_recommendation",
        description=(
            "Provides a clear, actionable recommendation grounded in the tool result "
            "(e.g. 'Pack an umbrella' when rain is reported), not just a restatement "
            "of the raw weather data."
        ),
        weight=4,
    ),
]


async def main() -> None:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model_name = os.environ.get("FOUNDRY_MODEL", "gpt-4o")

    credential = AzureCliCredential()
    chat_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model_name,
        credential=credential,
    )
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    agent = chat_client.as_agent(
        name="travel-assistant",
        instructions=(
            "You are a helpful travel assistant.  Always ground recommendations in "
            "tool output, cite each tool result, and refuse questions outside travel "
            "planning."
        ),
        tools=[get_weather],
    )

    # 1. Register (or bump the version of) the hand-authored rubric.
    # The service auto-attaches the non-editable `general_quality`
    # residual dimension for quality rubrics.
    print("Registering manual rubric evaluator...")
    rubric_ref = await FoundryEvals.create_rubric_evaluator(
        project_client=project_client,
        name="travel-quality-manual",
        dimensions=TRAVEL_RUBRIC_DIMENSIONS,
        category="quality",
        pass_threshold=0.6,
        display_name="Travel Quality (Manual)",
        description="Hand-authored rubric for the travel-assistant agent.",
    )
    print(
        f"Registered rubric {rubric_ref.name}@{rubric_ref.version} "
        f"with {len(rubric_ref.dimensions or ())} dimensions "
        f"(pass_threshold={rubric_ref.pass_threshold})"
    )

    # 2. Run an evaluation that combines built-ins with the new rubric.
    evals = FoundryEvals(
        client=chat_client,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY, rubric_ref],
    )
    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather in Seattle?",
            "Should I pack an umbrella for London?",
            "What's the capital of France?",  # off-scope — exercises scope_adherence
        ],
        evaluators=evals,
    )

    # 3. Quality gates — wire these into your CI job's exit status.
    for r in results:
        print(f"\nRun {r.run_id}: {r.passed}/{r.total} passed; portal: {r.report_url}")
        r.assert_no_failed_items()
        r.assert_score_at_least(0.7)
        r.assert_dimension_score_at_least("tool_grounding", 3)
        r.assert_dimension_score_at_least("scope_adherence", 3)

    await project_client.close()
    await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
