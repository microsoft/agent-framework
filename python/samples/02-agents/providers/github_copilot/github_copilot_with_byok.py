# Copyright (c) Microsoft. All rights reserved.

"""
GitHub Copilot Agent with BYOK (Bring Your Own Key)

This sample demonstrates how to configure GitHubCopilotAgent to route model requests through
your own endpoint (OpenAI, Azure OpenAI, Anthropic, or an OpenAI-compatible service such as
vLLM/LiteLLM/Ollama) instead of the default GitHub Copilot backend, using the Copilot SDK's
BYOK support.

Set the following environment variables before running:
    BYOK_PROVIDER_TYPE - Provider type ("openai", "azure", "anthropic"). Defaults to "openai".
    BYOK_BASE_URL      - Base URL of your provider endpoint.
    BYOK_API_KEY       - API key for that endpoint.
    BYOK_MODEL_ID      - Model name to request (e.g. "gpt-4o"). Defaults to "gpt-4o".

SECURITY NOTE: BYOK uses static credentials (no automatic token refresh) and usage is tracked
by your provider rather than GitHub. Keep API keys out of source control; load them from
environment variables or a secret store, as shown here.
"""

import asyncio
import os
from typing import Literal, cast

from agent_framework.github import GitHubCopilotAgent, GitHubCopilotOptions
from copilot.session import ProviderConfig


async def main() -> None:
    print("=== GitHub Copilot Agent with BYOK (Bring Your Own Key) ===\n")

    model_id = os.environ.get("BYOK_MODEL_ID", "gpt-4o")
    provider_type = cast(Literal["openai", "azure", "anthropic"], os.environ.get("BYOK_PROVIDER_TYPE", "openai"))

    # ProviderConfig routes the session through a custom endpoint instead of the GitHub
    # Copilot backend. `wire_api="completions"` is the broadly compatible choice; use
    # "responses" for providers that support the OpenAI Responses API.
    provider: ProviderConfig = {
        "type": provider_type,
        "base_url": os.environ["BYOK_BASE_URL"],
        "api_key": os.environ["BYOK_API_KEY"],
        "wire_api": "completions",
        "model_id": model_id,
    }

    # BYOK requires the model to also be set at the session level.
    agent: GitHubCopilotAgent[GitHubCopilotOptions] = GitHubCopilotAgent(
        instructions="You are a helpful assistant.",
        default_options=GitHubCopilotOptions(model=model_id, provider=provider),
    )

    async with agent:
        query = "What are the benefits of using your own API keys with an agent framework?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
