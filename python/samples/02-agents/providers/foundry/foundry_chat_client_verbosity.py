# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Literal

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryChatOptions
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

Verbosity = Literal["low", "medium", "high"]

load_dotenv()

"""
Foundry Chat Client Verbosity Example

Demonstrates the GPT-5 ``verbosity`` parameter against a Foundry-hosted GPT-5
deployment. ``verbosity`` controls how concise or detailed the model's natural-language
output is and accepts ``"low"``, ``"medium"``, or ``"high"``.

``FoundryChatOptions`` is an alias of ``OpenAIChatOptions`` and uses the Foundry
Responses API endpoint, so ``verbosity`` is a top-level option (parallel to
``reasoning``) and is translated to ``text.verbosity`` when sent to the service.

For authentication, run ``az login`` in a terminal or swap ``AzureCliCredential``
for your preferred credential type. The sample reads ``FOUNDRY_PROJECT_ENDPOINT``
and ``FOUNDRY_MODEL`` from the environment (or a local ``.env``) for the project
endpoint and model deployment name; set ``FOUNDRY_MODEL`` to a GPT-5 deployment
(e.g. ``gpt-5``) to exercise the verbosity option.
"""


PROMPT = "Explain in your own words what photosynthesis is and why it matters."


async def run_with_verbosity(level: Verbosity) -> None:
    """Run the same prompt with a different verbosity setting and print the output length."""
    agent = Agent(
        client=FoundryChatClient[FoundryChatOptions](credential=AzureCliCredential()),
        name=f"Explainer-{level}",
        instructions="You are a friendly science explainer.",
        default_options={"verbosity": level},
    )

    print(f"\033[92m=== verbosity={level!r} ===\033[0m")
    response = await agent.run(PROMPT)
    text = response.text or ""
    print(text)
    print(f"\n[chars: {len(text)}]\n")


async def run_per_call_override() -> None:
    """Show that verbosity can be overridden per ``run`` call via ``options=``."""
    agent = Agent(
        client=FoundryChatClient[FoundryChatOptions](credential=AzureCliCredential()),
        name="Explainer-default",
        instructions="You are a friendly science explainer.",
        default_options={"verbosity": "high"},
    )

    print("\033[92m=== per-call override: verbosity='low' ===\033[0m")
    response = await agent.run(PROMPT, options={"verbosity": "low"})
    text = response.text or ""
    print(text)
    print(f"\n[chars: {len(text)}]\n")


async def main() -> None:
    print("\033[92m=== Foundry Chat Client Verbosity Example ===\033[0m\n")

    levels: tuple[Verbosity, ...] = ("low", "medium", "high")
    for level in levels:
        await run_with_verbosity(level)

    await run_per_call_override()


if __name__ == "__main__":
    asyncio.run(main())
