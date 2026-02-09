# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Literal

from agent_framework import ChatAgent
from agent_framework.anthropic import AnthropicClient
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

"""TypedDict-based Chat Options

In Agent Framework, ChatClient and ChatAgent are generic over a ChatOptions TypedDict.
You can override which options are available for a given client or agent by providing
your own TypedDict subclass, and we include the most common options for all providers
out of the box.

This sample demonstrates the TypedDict-based approach which provides:
1. IDE autocomplete for available options
2. Type checking to catch errors at development time
3. Provider-specific options by extending base options

The sample shows usage with both OpenAI and Anthropic clients, but the same
approach works for other providers too.

For docs: https://learn.microsoft.com/agent-framework/concepts/chat-options
"""


# =========================================================================
# Anthropic Examples
# =========================================================================

# <anthropic_options>
async def demo_anthropic_chat_client() -> None:
    """Demonstrate Anthropic ChatClient with typed options and validation."""
    print("\n=== Anthropic ChatClient with TypedDict Options ===\n")

    client = AnthropicClient(model_id="claude-sonnet-4-5-20250929")

    response = await client.get_response(
        "What is the capital of France?",
        options={
            "temperature": 0.5,
            "max_tokens": 1000,
            # Anthropic-specific options:
            "thinking": {"type": "enabled", "budget_tokens": 1000},
        },
    )

    print(f"Anthropic Response: {response.text}")
    print(f"Model used: {response.model_id}")
# </anthropic_options>


# <anthropic_agent>
async def demo_anthropic_agent() -> None:
    """Demonstrate ChatAgent with Anthropic client and typed options."""
    print("\n=== ChatAgent with Anthropic and Typed Options ===\n")

    client = AnthropicClient(model_id="claude-sonnet-4-5-20250929")

    agent = ChatAgent(
        chat_client=client,
        name="claude-assistant",
        instructions="You are a helpful assistant powered by Claude. Be concise.",
        default_options={
            "temperature": 0.5,
            "max_tokens": 200,
            "top_k": 40,  # Anthropic-specific option
        },
    )

    response = await agent.run("Explain quantum computing in one sentence.")
    print(f"Agent Response: {response.text}")
# </anthropic_agent>


# =========================================================================
# OpenAI Examples - Reasoning Model Options
# =========================================================================

# <reasoning_options>
class OpenAIReasoningChatOptions(OpenAIChatOptions, total=False):
    """Chat options for OpenAI reasoning models (o1, o3, o4-mini, etc.).

    Reasoning models have different parameter support compared to standard models.
    This TypedDict marks unsupported parameters with ``None`` type.
    """

    # Reasoning-specific parameters
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"]

    # Unsupported parameters for reasoning models (override with None)
    temperature: None
    top_p: None
    frequency_penalty: None
    presence_penalty: None
    logit_bias: None
    logprobs: None
    top_logprobs: None
    stop: None
# </reasoning_options>


# <openai_reasoning>
async def demo_openai_chat_client_reasoning_models() -> None:
    """Demonstrate OpenAI ChatClient with typed options for reasoning models."""
    print("\n=== OpenAI ChatClient with TypedDict Options ===\n")

    client = OpenAIChatClient[OpenAIReasoningChatOptions]()

    response = await client.get_response(
        "What is 2 + 2?",
        options={
            "model_id": "o3",
            "max_tokens": 100,
            "allow_multiple_tool_calls": True,
            "reasoning_effort": "medium",
            # Unsupported options are caught by type checker (uncomment to see):
            # "temperature": 0.7,
        },
    )

    print(f"OpenAI Response: {response.text}")
    print(f"Model used: {response.model_id}")
# </openai_reasoning>


# <openai_agent>
async def demo_openai_agent() -> None:
    """Demonstrate ChatAgent with OpenAI client and typed options."""
    print("\n=== ChatAgent with OpenAI and Typed Options ===\n")

    agent = ChatAgent[OpenAIReasoningChatOptions](
        chat_client=OpenAIChatClient(),
        name="weather-assistant",
        instructions="You are a helpful assistant. Answer concisely.",
        default_options={
            "model_id": "o3",
            "max_tokens": 100,
            "reasoning_effort": "medium",
        },
    )

    # Options passed at runtime override construction options
    response = await agent.run(
        "What is 25 * 47?",
        options={"reasoning_effort": "high"},
    )

    print(f"Agent Response: {response.text}")
# </openai_agent>


async def main() -> None:
    """Run all Typed Options demonstrations."""
    # Anthropic demos (requires ANTHROPIC_API_KEY)
    await demo_anthropic_chat_client()
    await demo_anthropic_agent()

    # OpenAI demos (requires OPENAI_API_KEY)
    await demo_openai_chat_client_reasoning_models()
    await demo_openai_agent()


if __name__ == "__main__":
    asyncio.run(main())
