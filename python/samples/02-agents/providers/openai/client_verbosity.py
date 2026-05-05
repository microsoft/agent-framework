# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Literal

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions
from dotenv import load_dotenv

Verbosity = Literal["low", "medium", "high"]

load_dotenv()

"""
OpenAI Chat Client Verbosity Example

Demonstrates the GPT-5 ``verbosity`` parameter on the Responses API. ``verbosity``
controls how concise or detailed the model's natural-language output is and accepts
``"low"``, ``"medium"``, or ``"high"``.

The framework exposes ``verbosity`` as a top-level option on ``OpenAIChatOptions``
(parallel to ``reasoning``) and translates it to ``text.verbosity`` when calling the
Responses API.
"""


PROMPT = "Explain in your own words what photosynthesis is and why it matters."


async def run_with_verbosity(level: Verbosity) -> None:
    """Run the same prompt with a different verbosity setting and print the output length."""
    agent = Agent(
        client=OpenAIChatClient[OpenAIChatOptions](model="gpt-5"),
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
    """Show that verbosity can be overridden per ``run`` call."""
    agent = Agent(
        client=OpenAIChatClient[OpenAIChatOptions](model="gpt-5"),
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
    print("\033[92m=== OpenAI Chat Client Verbosity Example ===\033[0m\n")

    levels: tuple[Verbosity, ...] = ("low", "medium", "high")
    for level in levels:
        await run_with_verbosity(level)

    await run_per_call_override()


if __name__ == "__main__":
    asyncio.run(main())
