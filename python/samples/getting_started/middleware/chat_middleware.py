# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    ChatContext,
    ChatMessage,
    ChatMiddleware,
    ChatResponse,
    Role,
    chat_middleware,
)
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Chat Middleware Example

This sample demonstrates how to use chat middleware to observe and override
inputs sent to AI models. Chat middleware intercepts chat requests before they reach
the underlying AI service, allowing you to:

1. Observe and log input messages
2. Modify input messages before sending to AI
3. Override the entire response

The example covers:
- Class-based chat middleware inheriting from ChatMiddleware
- Function-based chat middleware with @chat_middleware decorator
- Middleware registration at agent level (applies to all runs)
- Middleware registration at run level (applies to specific run only)
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


class InputObserverMiddleware(ChatMiddleware):
    """Class-based middleware that observes and modifies input messages."""

    def __init__(self, replacement: str | None = None):
        """Initialize with a replacement for user messages."""
        self.replacement = replacement

    async def process(
        self,
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],
    ) -> None:
        """Observe and modify input messages before they are sent to AI."""
        print("[InputObserverMiddleware] Observing input messages:")

        for i, message in enumerate(context.messages):
            content = message.text if message.text else str(message.contents)
            print(f"  Message {i + 1} ({message.role.value}): {content}")

        print(f"[InputObserverMiddleware] Total messages: {len(context.messages)}")

        # Modify user messages by creating new messages with enhanced text
        modified_messages: list[ChatMessage] = []
        modified_count = 0

        for message in context.messages:
            if message.role == Role.USER and message.text:
                original_text = message.text
                updated_text = original_text

                if self.replacement:
                    updated_text = self.replacement
                    print(f"[InputObserverMiddleware] Updated: '{original_text}' -> '{updated_text}'")

                modified_message = ChatMessage(role=message.role, text=updated_text)
                modified_messages.append(modified_message)
                modified_count += 1
            else:
                modified_messages.append(message)

        # Replace messages in context
        context.messages[:] = modified_messages

        # Continue to next middleware or AI execution
        await next(context)

        # Observe that processing is complete
        print("[InputObserverMiddleware] Processing completed")


@chat_middleware
async def security_and_override_middleware(
    context: ChatContext,
    next: Callable[[ChatContext], Awaitable[None]],
) -> None:
    """Function-based middleware that implements security filtering and response override."""
    print("[SecurityMiddleware] Processing input...")

    # Security check - block sensitive information
    blocked_terms = ["password", "secret", "api_key", "token"]

    for message in context.messages:
        if message.text:
            message_lower = message.text.lower()
            for term in blocked_terms:
                if term in message_lower:
                    print(f"[SecurityMiddleware] BLOCKED: Found '{term}' in message")

                    # Override the response instead of calling AI
                    context.result = ChatResponse(
                        messages=[
                            ChatMessage(
                                role=Role.ASSISTANT,
                                text="I cannot process requests containing sensitive information. "
                                "Please rephrase your question without including passwords, secrets, or other "
                                "sensitive data.",
                            )
                        ]
                    )

                    # Set terminate flag to stop execution
                    context.terminate = True
                    return

    # Continue to next middleware or AI execution
    await next(context)


async def class_based_chat_middleware() -> None:
    """Demonstrate class-based middleware at agent level."""
    print("\n" + "=" * 60)
    print("Class-based Chat Middleware (Agent Level)")
    print("=" * 60)

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="EnhancedChatAgent",
            instructions="You are a helpful AI assistant.",
            # Register class-based middleware at agent level (applies to all runs)
            middleware=InputObserverMiddleware(),
            tools=get_weather,
        ) as agent,
    ):
        query = "What's the weather in Seattle?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Final Response: {result.text if result.text else 'No response'}")


async def function_based_chat_middleware() -> None:
    """Demonstrate function-based middleware at agent level."""
    print("\n" + "=" * 60)
    print("Function-based Chat Middleware (Agent Level)")
    print("=" * 60)

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="FunctionMiddlewareAgent",
            instructions="You are a helpful AI assistant.",
            # Register function-based middleware at agent level
            middleware=security_and_override_middleware,
        ) as agent,
    ):
        # Scenario with normal query
        print("\n--- Scenario 1: Normal Query ---")
        query = "Hello, how are you?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Final Response: {result.text if result.text else 'No response'}")

        # Scenario with security violation
        print("\n--- Scenario 2: Security Violation ---")
        query = "What is my password for this account?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Final Response: {result.text if result.text else 'No response'}")


async def run_level_middleware() -> None:
    """Demonstrate middleware registration at run level."""
    print("\n" + "=" * 60)
    print("Run-level Chat Middleware")
    print("=" * 60)

    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential).create_agent(
            name="RunLevelAgent",
            instructions="You are a helpful AI assistant.",
            tools=get_weather,
            # No middleware at agent level
        ) as agent,
    ):
        # Scenario 1: Run without any middleware
        print("\n--- Scenario 1: No Middleware ---")
        query = "What's the weather in Tokyo?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Response: {result.text if result.text else 'No response'}")

        # Scenario 2: Run with specific middleware for this call only (both enhancement and security)
        print("\n--- Scenario 2: With Run-level Middleware ---")
        print(f"User: {query}")
        result = await agent.run(
            query,
            middleware=[
                InputObserverMiddleware(replacement="What's the weather in Madrid?"),
                security_and_override_middleware,
            ],
        )
        print(f"Response: {result.text if result.text else 'No response'}")

        # Scenario 3: Security test with run-level middleware
        print("\n--- Scenario 3: Security Test with Run-level Middleware ---")
        query = "Can you help me with my secret API key?"
        print(f"User: {query}")
        result = await agent.run(
            query,
            middleware=security_and_override_middleware,
        )
        print(f"Response: {result.text if result.text else 'No response'}")


async def main() -> None:
    """Run all chat middleware examples."""
    print("Chat Middleware Examples")
    print("========================")

    await class_based_chat_middleware()
    await function_based_chat_middleware()
    await run_level_middleware()


if __name__ == "__main__":
    asyncio.run(main())
