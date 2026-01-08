# Copyright (c) Microsoft. All rights reserved.

"""Simple agentic chat example (Feature 1: Agentic Chat)."""

from typing import Any

from agent_framework import ChatAgent, ChatClientProtocol


def simple_agent(chat_client: ChatClientProtocol[Any]) -> ChatAgent[Any]:
    """Create a simple chat agent.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A configured ChatAgent instance
    """
    return ChatAgent[Any](
        name="simple_chat_agent",
        instructions="You are a helpful assistant. Be concise and friendly.",
        chat_client=chat_client,
    )
