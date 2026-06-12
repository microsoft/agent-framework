# Copyright (c) Microsoft. All rights reserved.

"""Evaluate a Foundry agent against a rubric evaluator that was created in Foundry.

Rubric evaluators are LLM-as-judge evaluators with custom scoring dimensions
that you define for your domain. agent-framework consumes pre-existing rubric
evaluators — they are authored in the Foundry portal (or via the dedicated
SDK / REST surface) and referenced here by name and version.

See: https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-evaluators/rubric-evaluators

This sample demonstrates:
1. Connecting to a pre-existing Foundry agent (PromptAgent or HostedAgent).
2. Referencing a pre-existing rubric evaluator by ``name`` and ``version``.
3. Mixing the rubric with built-in Foundry evaluators in one run.
4. Asserting per-dimension thresholds with
   ``EvalResults.assert_dimension_score_at_least(...)`` for CI quality gates.

Starting condition / prerequisites:
- An Azure AI Foundry project with a deployed model.
- A registered Foundry agent (PromptAgent or HostedAgent) in that project.
  This is the agent the rubric is meant to evaluate.
- A rubric evaluator already created in the Foundry portal against that
  agent. Creating rubrics through the portal currently requires picking a
  Foundry agent as the generation context, so this prerequisite is implied
  by having a rubric at all.
- Set the following in .env (see ``.env.example``):
    - ``FOUNDRY_PROJECT_ENDPOINT``
    - ``FOUNDRY_AGENT_NAME`` and ``FOUNDRY_AGENT_VERSION`` for the agent
    - ``FOUNDRY_RUBRIC_NAME`` and ``FOUNDRY_RUBRIC_VERSION`` for the rubric
    - ``FOUNDRY_MODEL`` for the rubric judge model
"""

import asyncio
import os

from agent_framework import EvalNotPassedError, evaluate_agent
from agent_framework.foundry import FoundryAgent, FoundryChatClient, FoundryEvals, GeneratedEvaluatorRef
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv(override=True)


async def main() -> None:
    # 1. Connect to the existing Foundry agent that the rubric was created
    #    against. PromptAgents and HostedAgents are both supported.
    credential = AzureCliCredential()
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    agent = FoundryAgent(
        project_endpoint=project_endpoint,
        agent_name=os.environ["FOUNDRY_AGENT_NAME"],
        agent_version=os.environ.get("FOUNDRY_AGENT_VERSION"),
        credential=credential,
    )

    # 2. Reference the pre-existing rubric evaluator by name + version.
    #    Always pin a version for reproducible CI runs; versionless refs
    #    resolve to "latest" and emit a warning at evaluation time.
    rubric_name = os.environ["FOUNDRY_RUBRIC_NAME"]
    rubric_version = os.environ["FOUNDRY_RUBRIC_VERSION"]
    rubric = GeneratedEvaluatorRef(name=rubric_name, version=rubric_version)

    # 3. Mix the rubric with built-in evaluators in a single FoundryEvals
    #    config. FoundryEvals talks to Foundry over the project endpoint, so
    #    we hand it a FoundryChatClient configured with the same credential.
    eval_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    )
    evals = FoundryEvals(
        client=eval_client,
        evaluators=[
            rubric,
            FoundryEvals.RELEVANCE,
            FoundryEvals.COHERENCE,
        ],
    )

    # =========================================================================
    # Run evaluation
    # =========================================================================
    print("=" * 60)
    print(f"Evaluating '{agent.name}' with rubric '{rubric_name}' (version {rubric_version})")
    print("=" * 60)

    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather like in Seattle?",
            "Should I bring an umbrella to London tomorrow?",
        ],
        evaluators=evals,
    )

    for r in results:
        print(f"Status: {r.status}")
        print(f"Results: {r.passed}/{r.total} passed")
        print(f"Portal: {r.report_url}")
        if r.all_passed:
            print("[PASS] All passed")
        else:
            print(f"[FAIL] {r.failed} failed")

    # =========================================================================
    # Per-dimension quality gate
    # =========================================================================
    # Rubric evaluators emit per-dimension scores (1–5) on top of the overall
    # weighted score. Use assert_dimension_score_at_least to gate CI on a
    # specific dimension — e.g., never ship if a critical dimension drops
    # below 3.
    #
    # The dimension_id must match an id defined on your rubric in Foundry.
    # ``general_quality`` is used here because it's the conventional
    # ``always_applicable: true`` dimension in the Foundry docs' example
    # rubric — swap it for whatever dimension id(s) your rubric actually
    # defines.
    print()
    print("=" * 60)
    print("Per-dimension quality gate")
    print("=" * 60)

    for r in results:
        try:
            r.assert_dimension_score_at_least(
                "general_quality",
                min_score=3.0,
                evaluator=rubric_name,
            )
            print(f"[PASS] {r.provider}: general_quality >= 3 on every item")
        except EvalNotPassedError as exc:
            print(f"[FAIL] {r.provider}: dimension gate tripped: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
