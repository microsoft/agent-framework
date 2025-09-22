# Copyright (c) Microsoft. All rights reserved.

import asyncio
import time
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    AgentMiddleware,
    AgentRunContext,
    AgentRunResponse,
    FunctionInvocationContext,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Agent-Level and Run-Level Middleware Example

This sample demonstrates the difference between agent-level and run-level middleware:

- Agent-level middleware: Applied to ALL runs of the agent (persistent across runs)
- Run-level middleware: Applied to specific runs only (isolated per run)

The example shows:
1. Agent-level security middleware that validates all requests
2. Agent-level performance monitoring across all runs
3. Run-level context middleware for specific use cases (high priority, debugging)
4. Run-level caching middleware for expensive operations

Execution order: Agent middleware (outermost) -> Run middleware (innermost) -> Agent execution
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


# Agent-level middleware (applied to ALL runs)
class SecurityAgentMiddleware(AgentMiddleware):
    """Agent-level security middleware that validates all requests."""

    async def process(self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]) -> None:
        print("[SecurityMiddleware] Checking security for all requests...")

        # Check for security violations in the last user message
        last_message = context.messages[-1] if context.messages else None
        if last_message and last_message.text:
            query = last_message.text.lower()
            if any(word in query for word in ["password", "secret", "credentials"]):
                print("[SecurityMiddleware] Security violation detected! Blocking request.")
                return  # Don't call next() to prevent execution

        print("[SecurityMiddleware] Security check passed.")
        context.metadata["security_validated"] = True
        await next(context)


async def performance_monitor_middleware(
    context: AgentRunContext,
    next: Callable[[AgentRunContext], Awaitable[None]],
) -> None:
    """Agent-level performance monitoring for all runs."""
    print("[PerformanceMonitor] Starting performance monitoring...")
    start_time = time.time()

    await next(context)

    end_time = time.time()
    duration = end_time - start_time
    print(f"[PerformanceMonitor] Total execution time: {duration:.3f}s")
    context.metadata["execution_time"] = duration


# Run-level middleware (applied to specific runs only)
class HighPriorityMiddleware(AgentMiddleware):
    """Run-level middleware for high priority requests."""

    async def process(self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]) -> None:
        print("[HighPriority] Processing high priority request with expedited handling...")

        # Read metadata set by agent-level middleware
        if context.metadata.get("security_validated"):
            print("[HighPriority] Security validation confirmed from agent middleware")

        # Set high priority flag
        context.metadata["priority"] = "high"
        context.metadata["expedited"] = True

        await next(context)
        print("[HighPriority] High priority processing completed")


async def debugging_middleware(
    context: AgentRunContext,
    next: Callable[[AgentRunContext], Awaitable[None]],
) -> None:
    """Run-level debugging middleware for troubleshooting specific runs."""
    print("[Debug] Debug mode enabled for this run")
    print(f"[Debug] Messages count: {len(context.messages)}")
    print(f"[Debug] Is streaming: {context.is_streaming}")

    # Log existing metadata from agent middleware
    if context.metadata:
        print(f"[Debug] Existing metadata: {context.metadata}")

    context.metadata["debug_enabled"] = True

    await next(context)

    print("[Debug] Debug information collected")


class CachingMiddleware(AgentMiddleware):
    """Run-level caching middleware for expensive operations."""

    def __init__(self) -> None:
        self.cache: dict[str, AgentRunResponse] = {}

    async def process(self, context: AgentRunContext, next: Callable[[AgentRunContext], Awaitable[None]]) -> None:
        # Create a simple cache key from the last message
        last_message = context.messages[-1] if context.messages else None
        cache_key: str = last_message.text if last_message and last_message.text else "no_message"

        if cache_key in self.cache:
            print(f"[Cache] Cache HIT for: '{cache_key[:30]}...'")
            context.result = self.cache[cache_key]  # type: ignore
            return  # Don't call next(), return cached result

        print(f"[Cache] Cache MISS for: '{cache_key[:30]}...'")
        context.metadata["cache_key"] = cache_key

        await next(context)

        # Cache the result if we have one
        if context.result:
            self.cache[cache_key] = context.result  # type: ignore
            print("[Cache] Result cached for future use")


async def function_logging_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """Function middleware that logs all function calls."""
    function_name = context.function.name
    args = context.arguments
    print(f"[FunctionLog] Calling function: {function_name} with args: {args}")

    await next(context)

    print(f"[FunctionLog] Function {function_name} completed")


async def main() -> None:
    """Example demonstrating agent-level and run-level middleware."""
    print("=== Agent-Level and Run-Level Middleware Example ===\n")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather,
            # Agent-level middleware: applied to ALL runs
            middleware=[
                SecurityAgentMiddleware(),
                performance_monitor_middleware,
                function_logging_middleware,
            ],
        ) as agent,
    ):
        print("Agent created with agent-level middleware:")
        print("   - SecurityMiddleware (blocks sensitive requests)")
        print("   - PerformanceMonitor (tracks execution time)")
        print("   - FunctionLogging (logs all function calls)")
        print()

        # Run 1: Normal query with no run-level middleware
        print("=" * 60)
        print("RUN 1: Normal query (agent-level middleware only)")
        print("=" * 60)
        query = "What's the weather like in Paris?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response'}")
        print()

        # Run 2: High priority request with run-level middleware
        print("=" * 60)
        print("RUN 2: High priority request (agent + run-level middleware)")
        print("=" * 60)
        query = "What's the weather in Tokyo? This is urgent!"
        print(f"User: {query}")
        result = await agent.run(
            query,
            middleware=HighPriorityMiddleware(),  # Run-level middleware
        )
        print(f"Agent: {result.text if result.text else 'No response'}")
        print()

        # Run 3: Debug mode with run-level debugging middleware
        print("=" * 60)
        print("RUN 3: Debug mode (agent + run-level debugging)")
        print("=" * 60)
        query = "What's the weather in London?"
        print(f"User: {query}")
        result = await agent.run(
            query,
            middleware=[debugging_middleware],  # Run-level middleware
        )
        print(f"Agent: {result.text if result.text else 'No response'}")
        print()

        # Run 4: Multiple run-level middleware
        print("=" * 60)
        print("RUN 4: Multiple run-level middleware (caching + debug)")
        print("=" * 60)
        caching = CachingMiddleware()
        query = "What's the weather in New York?"
        print(f"User: {query}")
        result = await agent.run(
            query,
            middleware=[caching, debugging_middleware],  # Multiple run-level middleware
        )
        print(f"Agent: {result.text if result.text else 'No response'}")
        print()

        # Run 5: Test cache hit with same query
        print("=" * 60)
        print("RUN 5: Test cache hit (same query as Run 4)")
        print("=" * 60)
        print(f"User: {query}")  # Same query as Run 4
        result = await agent.run(
            query,
            middleware=[caching],  # Same caching middleware instance
        )
        print(f"Agent: {result.text if result.text else 'No response'}")
        print()

        # Run 6: Security violation test
        print("=" * 60)
        print("RUN 6: Security test (should be blocked by agent middleware)")
        print("=" * 60)
        query = "What's the secret weather password for Berlin?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'Request was blocked by security middleware'}")
        print()

        # Run 7: Normal query again (no run-level middleware interference)
        print("=" * 60)
        print("RUN 7: Normal query again (agent-level middleware only)")
        print("=" * 60)
        query = "What's the weather in Sydney?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response'}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
