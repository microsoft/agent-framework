# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework_github_copilot import GitHubCopilotModelClient
from dotenv import load_dotenv

load_dotenv()

"""
GitHub Copilot Model Client Example

Uses the OpenAI-compatible Copilot inference endpoint
(https://api.githubcopilot.com) with automatic GitHub OAuth.

Auth resolves in this order:
  1. `api_key=` argument (a raw GitHub OAuth token / fine-grained PAT)
  2. COPILOT_GITHUB_TOKEN / GH_TOKEN / GITHUB_TOKEN env vars
  3. `gh auth token` from the GitHub CLI
  4. Interactive OAuth device-code login (when interactive=True, the default)

Optional env vars:
  GITHUB_COPILOT_MODEL  default model id (e.g. "gpt-4o", "claude-sonnet-4")
"""


MODEL = "claude-opus-4.7-1m-internal"


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Non-streaming example.

    Note: The Copilot chat-completions endpoint can return 403 for
    non-streaming requests issued via the OpenAI SDK (the same payload
    succeeds with ``stream=True``). This demo therefore wraps the call so a
    failure is reported and the rest of the sample continues.
    """
    print("=== Non-streaming Response Example ===")

    agent = Agent(
        client=GitHubCopilotModelClient(model=MODEL),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    try:
        result = await agent.run(query)
        print(f"Result: {result}\n")
    except Exception as exc:  # noqa: BLE001 - sample-only diagnostic
        print(f"(non-streaming failed: {exc})\n")


async def streaming_example() -> None:
    print("=== Streaming Response Example ===")

    agent = Agent(
        client=GitHubCopilotModelClient(model=MODEL),
        name="WeatherAgent",
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    query = "What's the weather like in Portland and in Paris?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def list_models_example() -> None:
    print("=== Available Copilot Models ===")
    models = GitHubCopilotModelClient.list_models()
    for item in models[:10]:
        mid = item["id"]
        caps = item.get("capabilities") or {}
        ctx = (caps.get("limits") or {}).get("max_prompt_tokens", "?")
        print(f"  - {mid}  (context: {ctx})")
    if len(models) > 10:
        print(f"  ... and {len(models) - 10} more")
    print()


async def main() -> None:
    print("=== GitHub Copilot Model Client Example ===\n")
    await list_models_example()
    await streaming_example()
    await non_streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
