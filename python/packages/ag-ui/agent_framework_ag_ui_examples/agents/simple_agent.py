# Copyright (c) Microsoft. All rights reserved.

"""Simple agentic chat example (Feature 1: Agentic Chat)."""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

# Create a simple chat agent
agent = ChatAgent(
    name="simple_chat_agent",
    instructions="You are a helpful assistant. Be concise and friendly.",
    chat_client=AzureOpenAIChatClient(),
)
