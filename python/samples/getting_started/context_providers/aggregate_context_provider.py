# Copyright (c) Microsoft. All rights reserved.

"""
This sample demonstrates how to use an AggregateContextProvider to combine multiple context providers.

The AggregateContextProvider is a convenience class that allows you to aggregate multiple
ContextProviders into a single provider. It delegates events to all providers and combines
their context before returning.

You can use this implementation as-is, or implement your own aggregation logic.
"""

import asyncio
import sys
from collections.abc import MutableSequence, Sequence
from contextlib import AsyncExitStack
from types import TracebackType
from typing import TYPE_CHECKING, Any, cast

from agent_framework import ChatAgent, ChatMessage, Context, ContextProvider
from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

if TYPE_CHECKING:
    from agent_framework import ToolProtocol

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


# region AggregateContextProvider


class AggregateContextProvider(ContextProvider):
    """A ContextProvider that contains multiple context providers.

    It delegates events to multiple context providers and aggregates responses from those
    events before returning. This allows you to combine multiple context providers into a
    single provider.

    Examples:
        .. code-block:: python

            from agent_framework import ChatAgent

            # Create multiple context providers
            provider1 = CustomContextProvider1()
            provider2 = CustomContextProvider2()
            provider3 = CustomContextProvider3()

            # Combine them using AggregateContextProvider
            aggregate = AggregateContextProvider([provider1, provider2, provider3])

            # Pass the aggregate to the agent
            agent = ChatAgent(chat_client=client, name="assistant", context_provider=aggregate)

            # You can also add more providers later
            provider4 = CustomContextProvider4()
            aggregate.add(provider4)
    """

    def __init__(self, context_providers: ContextProvider | Sequence[ContextProvider] | None = None) -> None:
        """Initialize the AggregateContextProvider with context providers.

        Args:
            context_providers: The context provider(s) to add.
        """
        if isinstance(context_providers, ContextProvider):
            self.providers = [context_providers]
        else:
            self.providers = cast(list[ContextProvider], context_providers) or []
        self._exit_stack: AsyncExitStack | None = None

    def add(self, context_provider: ContextProvider) -> None:
        """Add a new context provider.

        Args:
            context_provider: The context provider to add.
        """
        self.providers.append(context_provider)

    @override
    async def thread_created(self, thread_id: str | None = None) -> None:
        await asyncio.gather(*[x.thread_created(thread_id) for x in self.providers])

    @override
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        contexts = await asyncio.gather(*[provider.invoking(messages, **kwargs) for provider in self.providers])
        instructions: str = ""
        return_messages: list[ChatMessage] = []
        tools: list["ToolProtocol"] = []
        for ctx in contexts:
            if ctx.instructions:
                instructions += ctx.instructions
            if ctx.messages:
                return_messages.extend(ctx.messages)
            if ctx.tools:
                tools.extend(ctx.tools)
        return Context(instructions=instructions, messages=return_messages, tools=tools)

    @override
    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        await asyncio.gather(*[
            x.invoked(
                request_messages=request_messages,
                response_messages=response_messages,
                invoke_exception=invoke_exception,
                **kwargs,
            )
            for x in self.providers
        ])

    @override
    async def __aenter__(self) -> "Self":
        """Enter the async context manager and set up all providers.

        Returns:
            The AggregateContextProvider instance for chaining.
        """
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        # Enter all context providers
        for provider in self.providers:
            await self._exit_stack.enter_async_context(provider)

        return self

    @override
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and clean up all providers.

        Args:
            exc_type: The exception type if an exception occurred, None otherwise.
            exc_val: The exception value if an exception occurred, None otherwise.
            exc_tb: The exception traceback if an exception occurred, None otherwise.
        """
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            self._exit_stack = None


# endregion


# region Example Context Providers


class TimeContextProvider(ContextProvider):
    """A simple context provider that adds time-related instructions."""

    @override
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        from datetime import datetime

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return Context(instructions=f"The current date and time is: {current_time}. ")


class PersonaContextProvider(ContextProvider):
    """A context provider that adds a persona to the agent."""

    def __init__(self, persona: str):
        self.persona = persona

    @override
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        return Context(instructions=f"Your persona: {self.persona}. ")


class PreferencesContextProvider(ContextProvider):
    """A context provider that adds user preferences."""

    def __init__(self):
        self.preferences: dict[str, str] = {}

    @override
    async def invoking(self, messages: ChatMessage | MutableSequence[ChatMessage], **kwargs: Any) -> Context:
        if not self.preferences:
            return Context()
        prefs_str = ", ".join(f"{k}: {v}" for k, v in self.preferences.items())
        return Context(instructions=f"User preferences: {prefs_str}. ")

    @override
    async def invoked(
        self,
        request_messages: ChatMessage | Sequence[ChatMessage],
        response_messages: ChatMessage | Sequence[ChatMessage] | None = None,
        invoke_exception: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        # Simple example: extract and store preferences from user messages
        # In a real implementation, you might use structured extraction
        msgs = [request_messages] if isinstance(request_messages, ChatMessage) else list(request_messages)

        for msg in msgs:
            content = msg.content if hasattr(msg, "content") else ""
            # Very simple extraction - in production, use LLM-based extraction
            if isinstance(content, str) and "prefer" in content.lower() and ":" in content:
                parts = content.split(":")
                if len(parts) >= 2:
                    key = parts[0].strip().lower().replace("i prefer ", "")
                    value = parts[1].strip()
                    self.preferences[key] = value


# endregion


# region Main


async def main():
    """Demonstrate using AggregateContextProvider to combine multiple providers."""
    async with AzureCliCredential() as credential:
        chat_client = AzureAIClient(credential=credential)

        # Create individual context providers
        time_provider = TimeContextProvider()
        persona_provider = PersonaContextProvider("You are a helpful and friendly AI assistant named Max.")
        preferences_provider = PreferencesContextProvider()

        # Combine them using AggregateContextProvider
        aggregate_provider = AggregateContextProvider([
            time_provider,
            persona_provider,
            preferences_provider,
        ])

        # Create the agent with the aggregate provider
        async with ChatAgent(
            chat_client=chat_client,
            instructions="You are a helpful assistant.",
            context_provider=aggregate_provider,
        ) as agent:
            # Create a new thread for the conversation
            thread = agent.get_new_thread()

            # First message - the agent should include time and persona context
            print("User: Hello! Who are you?")
            result = await agent.run("Hello! Who are you?", thread=thread)
            print(f"Agent: {result}\n")

            # Set a preference
            print("User: I prefer language: formal English")
            result = await agent.run("I prefer language: formal English", thread=thread)
            print(f"Agent: {result}\n")

            # Ask something - the agent should now include the preference
            print("User: Can you tell me a fun fact?")
            result = await agent.run("Can you tell me a fun fact?", thread=thread)
            print(f"Agent: {result}\n")

            # Show what the aggregate provider is tracking
            print(f"\nPreferences tracked: {preferences_provider.preferences}")


if __name__ == "__main__":
    asyncio.run(main())
