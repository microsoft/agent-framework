# Copyright (c) Microsoft. All rights reserved.

"""Generate a Foundry rubric evaluator from an agent and use it in CI.

This sample demonstrates the end-to-end adaptive-evals flow:

1. Build an agent.
2. Generate a rubric evaluator from the agent using
   ``FoundryEvals.generate_rubric()`` — produces a pinned
   ``GeneratedEvaluatorRef`` you can store in source control.
3. Use the pinned reference in ``evaluators=[...]`` for a regression
   run alongside built-in evaluators.
4. Assert quality gates with ``assert_score_at_least`` /
   ``assert_dimension_score_at_least`` / ``assert_no_failed_items``.

A companion ``evaluators.yaml`` shows the source-controlled config
pattern for CI.  Load it with :func:`load_evals_config` and pass the
resulting spec through :func:`build_sources` to keep generation
parameters out of code.

Prerequisites:
- An Azure AI Foundry project with a deployed model.
- ``azure-ai-projects`` build that includes the rubric-generation APIs.
- Set ``FOUNDRY_PROJECT_ENDPOINT`` and ``FOUNDRY_MODEL`` in ``.env``.

Run with:

.. code-block:: bash

    az login
    python evaluate_with_generated_rubric_sample.py
"""

import asyncio
import os
import textwrap
from pathlib import Path

from agent_framework import evaluate_agent
from agent_framework.foundry import (
    FoundryChatClient,
    FoundryEvals,
    build_sources,
    load_evals_config,
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


SAMPLE_YAML = textwrap.dedent(
    """\
    evaluators:
      travel-quality:
        type: foundry.generated_rubric
        category: quality
        model: gpt-4o
        display_name: Travel Quality Rubric
        description: Custom rubric tailored to the travel-assistant agent.
        sources:
          - type: agent
            include_instructions: true
            include_tools: true
    """
)


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
            "You are a helpful travel assistant.  Always ground recommendations in tool output, "
            "cite each tool result, and refuse questions outside travel planning."
        ),
        tools=[get_weather],
    )

    # 1. Load the source-controlled evaluator config.
    config_path = Path(__file__).with_name("evaluators.yaml")
    if not config_path.exists():
        config_path.write_text(SAMPLE_YAML, encoding="utf-8")
        print(f"Wrote sample config to {config_path}")
    config = load_evals_config(config_path)
    spec = config["travel-quality"]

    # 2. Generate (or refresh) the rubric evaluator.  In CI you typically run
    # this once and commit the returned name/version pair.
    print("Generating rubric evaluator from agent + spec...")
    sources = build_sources(spec, agent=agent)
    rubric_ref = await FoundryEvals.generate_rubric(
        project_client=project_client,
        name=spec.name,
        sources=sources,
        category=spec.category,
        model=spec.model,
        display_name=spec.display_name,
        description=spec.description,
    )
    print(f"Generated rubric {rubric_ref.name}@{rubric_ref.version} with {len(rubric_ref.dimensions or ())} dimensions")

    # 3. Run an evaluation that combines built-ins with the new rubric.
    evals = FoundryEvals(
        client=chat_client,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY, rubric_ref],
    )
    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather in Seattle?",
            "Should I pack an umbrella for London?",
        ],
        evaluators=evals,
    )

    # 4. Quality gates — wire these into your CI job's exit status.
    for r in results:
        print(f"\nRun {r.run_id}: {r.passed}/{r.total} passed; portal: {r.report_url}")
        r.assert_no_failed_items()
        r.assert_score_at_least(0.8)
        if rubric_ref.dimensions:
            r.assert_dimension_score_at_least(rubric_ref.dimensions[0].id, 3)

    await project_client.close()
    await credential.close()


if __name__ == "__main__":
    asyncio.run(main())
