# Copyright (c) Microsoft. All rights reserved.

"""Simple agentic chat example (Feature 1: Agentic Chat)."""

from typing import Any

from agent_framework import Agent, SupportsChatGetResponse


def simple_agent(client: SupportsChatGetResponse[Any]) -> Agent[Any]:
    """Create a simple chat agent.

    Args:
        client: The chat client to use for the agent

    Returns:
        A configured Agent instance
    """
    return Agent[Any](
        name="simple_chat_agent",
        instructions="You are a helpful assistant. Be concise and friendly.",
        client=client,
    )
