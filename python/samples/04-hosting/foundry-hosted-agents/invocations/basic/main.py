# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from typing import Any

from agent_framework import Agent, InMemoryHistoryProvider
from agent_framework.foundry import FoundryChatClient, FoundryChatOptions
from agent_framework_foundry_hosting import AgentTurn, InvocationsHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from starlette.requests import Request

"""Host an Invocations agent with an application JSON parser and persisted MAF history."""

load_dotenv()

ALLOWED_OPTIONS = {"temperature", "max_tokens"}


# 1. Map the application's JSON payload to typed MAF inputs and explicit run options.
async def parse_input(request: Request) -> AgentTurn:
    """Map application-specific JSON to a validated agent turn."""
    payload: Any = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("prompt"), str):
        raise ValueError("prompt must be a string.")
    options = payload.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("options must be an object.")
    # 2. Allow only caller-controlled generation settings; keep storage developer-owned.
    unknown = set(options) - ALLOWED_OPTIONS
    if unknown:
        raise ValueError(f"Unsupported options: {', '.join(sorted(unknown))}.")
    stream = payload.get("stream", False)
    if not isinstance(stream, bool):
        raise ValueError("stream must be a boolean.")
    return AgentTurn(messages=payload["prompt"], options=options, stream=stream)


# 3. Persist the agent's own conversation history without provider-managed storage.
def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent[FoundryChatOptions](
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        context_providers=[InMemoryHistoryProvider()],
        default_options={"store": False},
    )

    server = InvocationsHostServer(
        agent,
        parse_input=parse_input,
    )
    server.run()


if __name__ == "__main__":
    main()

# Expected non-streaming response: {"response": "<agent reply>"}
# Streaming emits event: delta frames, then event: done after the MAF session is saved.
