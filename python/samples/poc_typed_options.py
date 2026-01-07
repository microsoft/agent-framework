# Copyright (c) Microsoft. All rights reserved.

"""POC: TypedDict-based Chat Options with Unpack.

This sample demonstrates the TypedDict-based approach for chat client and agent options,
which provides:
1. IDE autocomplete for available options
2. Type checking to catch errors at development time
3. Runtime validation to raise errors for unsupported options

The sample shows usage with both OpenAI and Anthropic clients, demonstrating
how provider-specific options work for ChatClient and ChatAgent.
"""

import asyncio

from agent_framework import ChatAgent
from agent_framework.anthropic import AnthropicChatOptions, AnthropicClient
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions


async def demo_openai_chat_client() -> None:
    """Demonstrate OpenAI ChatClient with typed options."""
    print("\n=== OpenAI ChatClient with TypedDict Options ===\n")

    # Create OpenAI client
    client = OpenAIChatClient[OpenAIChatOptions](model_id="gpt-4o-mini")

    # With TypedDict-based options, you get full IDE autocomplete!
    # Try typing `client.get_response("Hello", ` and see the suggestions
    response = await client.get_response(
        "What is 2 + 2?",
        options={
            "temperature": 0.7,
            "max_tokens": 100,
            "allow_multiple_tool_calls": True,
            # OpenAI-specific options work:
            "logprobs": True,
            # "reasoning_effort": "medium",
            # "random": 234,  # <-- Uncomment to see type checking catch this error
        },
        # reasoning_effort="high",  # <-- Uncomment for reasoning model specific option
    )

    print(f"OpenAI Response: {response.text}")
    print(f"Model used: {response.model_id}")


async def demo_anthropic_chat_client() -> None:
    """Demonstrate Anthropic ChatClient with typed options and validation."""
    print("\n=== Anthropic ChatClient with TypedDict Options ===\n")

    # Create Anthropic client
    client = AnthropicClient(model_id="claude-sonnet-4-5-20250929")

    # Standard options work great:
    response = await client.get_response(
        "What is the capital of France?",
        options={
            "temperature": 0.5,
            "max_tokens": 100,
            # Anthropic-specific options:
            # "top_k": 40,  # <-- Uncomment for Anthropic-specific option
        },
    )

    print(f"Anthropic Response: {response.text}")
    print(f"Model used: {response.model_id}")


async def demo_anthropic_validation_error() -> None:
    """Demonstrate how Anthropic raises errors for unsupported options."""
    print("\n=== Anthropic Validation Error Demo ===\n")

    client = AnthropicClient[AnthropicChatOptions](model_id="claude-sonnet-4-5-20250929")

    try:
        # This will raise a ValueError because Anthropic doesn't support logprobs!
        # Extra kwargs are passed through and validated at runtime
        await client.get_response(
            "Hello",
            options={
                "temperature": 0.7,
                "logprobs": True,  # Not supported by Anthropic!
            },
        )
    except ValueError as e:
        print(f"Caught expected error: {e}")
        print("✓ The TypedDict validator correctly caught the unsupported option!")


async def demo_openai_agent() -> None:
    """Demonstrate ChatAgent with OpenAI client and typed options."""
    print("\n=== ChatAgent with OpenAI and Typed Options ===\n")

    # Create a typed agent - IDE will autocomplete options!
    agent = ChatAgent(
        chat_client=OpenAIChatClient[OpenAIChatOptions](model_id="gpt-4o-mini"),
        name="weather-assistant",
        instructions="You are a helpful assistant. Answer concisely.",
        # Options can be set at construction time
        default_options={
            "temperature": 0.7,
            "max_tokens": 200,
            "logprobs": True,  # OpenAI-specific, uncomment to try
            # "random": 3847,  # <-- Uncomment to see type checking catch this error
        },
    )

    # Or pass options at runtime - they override construction options
    response = await agent.run(
        "What is 25 * 47?",
        options={
            "temperature": 0.0,  # Override for this specific call
            # "reasoning_effort": "high",  # For reasoning models
        },
    )

    print(f"Agent Response: {response.text}")


async def demo_anthropic_agent() -> None:
    """Demonstrate ChatAgent with Anthropic client and typed options."""
    print("\n=== ChatAgent with Anthropic and Typed Options ===\n")

    client = AnthropicClient(model_id="claude-sonnet-4-5-20250929")

    # Create a typed agent for Anthropic - IDE knows Anthropic-specific options!
    agent = ChatAgent[AnthropicChatOptions](
        chat_client=client,
        name="claude-assistant",
        instructions="You are a helpful assistant powered by Claude. Be concise.",
        default_options={
            "temperature": 0.5,
            "max_tokens": 200,
            # "top_k": 40,  # Anthropic-specific option, uncomment to try
        },
    )

    # Run the agent
    response = await agent.run("Explain quantum computing in one sentence.")

    print(f"Agent Response: {response.text}")


async def demo_streaming_with_typed_options() -> None:
    """Demonstrate streaming responses with typed options."""
    print("\n=== Streaming with TypedDict Options ===\n")

    client = OpenAIChatClient(model_id="gpt-4o-mini")

    print("Streaming response: ", end="", flush=True)
    async for update in client.get_streaming_response(
        "Count from 1 to 5, one number per line.",
        options={
            "temperature": 0.3,
            "max_tokens": 50,
        },
    ):
        if update.text:
            print(update.text, end="", flush=True)
    print()  # Newline after streaming


async def main() -> None:
    """Run all POC demonstrations."""
    print("=" * 60)
    print("POC: TypedDict-based Chat Options with Unpack")
    print("=" * 60)

    # Uncomment the demos you want to run (requires API keys set up):

    # OpenAI demos (requires OPENAI_API_KEY)
    # await demo_openai_chat_client()
    # await demo_openai_agent()  # New! ChatAgent with typed options
    # await demo_streaming_with_typed_options()

    # # Anthropic demos (requires ANTHROPIC_API_KEY)
    # await demo_anthropic_chat_client()
    # await demo_anthropic_agent()  # New! ChatAgent with typed options
    await demo_anthropic_validation_error()

    print("\n" + "=" * 60)
    print("POC Complete!")
    print("=" * 60)
    print("""
Key Benefits of TypedDict-based Options:

1. IDE Autocomplete: When you type `client.get_response("msg", options={`,
   your IDE shows all available options with their types.

2. Type Checking: Tools like pyright/mypy can catch type errors
   at development time, before you run the code.

3. Provider-Specific Options: Each provider's client knows its
   specific options (e.g., OpenAI has `logprobs`, Anthropic has `top_k`).

4. ChatAgent Support: Create typed agents like `ChatAgent[OpenAIChatOptions]`
   and get IDE autocomplete for `agent.run("msg", options={...})`.

5. Runtime Validation: If you pass an unsupported option to a provider,
   it raises a clear error message instead of silently ignoring it.

6. Documentation: TypedDict definitions serve as living documentation
   for what options each provider supports.

Try uncommenting the demo functions above to see it in action!
""")


if __name__ == "__main__":
    asyncio.run(main())
