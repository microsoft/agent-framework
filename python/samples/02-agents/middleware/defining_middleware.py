# Copyright (c) Microsoft. All rights reserved.

import asyncio
import datetime
import time
from collections.abc import Awaitable, Callable
from random import randint
from typing import Annotated

from agent_framework import (
    AgentContext,
    AgentMiddleware,
    AgentResponse,
    ChatMessage,
    FunctionInvocationContext,
    FunctionMiddleware,
    agent_middleware,
    function_middleware,
    tool,
)
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential
from pydantic import Field

"""
Defining Middleware — Three Syntax Styles

For docs: https://learn.microsoft.com/agent-framework/agents/middleware/

This sample demonstrates three equivalent ways to define middleware:

1. **Class-based** — Inherit from AgentMiddleware / FunctionMiddleware base classes.
   Best for stateful middleware or complex logic that benefits from OOP.

2. **Function-based** — Plain async functions with type-annotated parameters
   (AgentContext / FunctionInvocationContext). Lightweight and stateless.

3. **Decorator-based** — Use @agent_middleware / @function_middleware decorators.
   No type annotations needed; the decorator declares the middleware type.

Each section below implements the same security + logging middleware pair
so you can compare the three approaches side-by-side.
"""


# ---------------------------------------------------------------------------
# Shared tool used by all three sections
# ---------------------------------------------------------------------------

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


@tool(approval_mode="never_require")
def get_current_time() -> str:
    """Get the current time."""
    return f"Current time is {datetime.datetime.now().strftime('%H:%M:%S')}"


# ===========================================================================
# Section 1 — Class-based middleware
# ===========================================================================

# <class_based>
class SecurityAgentMiddleware(AgentMiddleware):
    """Agent middleware that checks for security violations."""

    async def process(
        self,
        context: AgentContext,
        next: Callable[[AgentContext], Awaitable[None]],
    ) -> None:
        # Check for potential security violations in the query
        # Look at the last user message
        last_message = context.messages[-1] if context.messages else None
        if last_message and last_message.text:
            query = last_message.text
            if "password" in query.lower() or "secret" in query.lower():
                print("[SecurityAgentMiddleware] Security Warning: Detected sensitive information, blocking request.")
                # Override the result with warning message
                context.result = AgentResponse(
                    messages=[ChatMessage("assistant", ["Detected sensitive information, the request is blocked."])]
                )
                # Simply don't call next() to prevent execution
                return

        print("[SecurityAgentMiddleware] Security check passed.")
        await next(context)


class LoggingFunctionMiddleware(FunctionMiddleware):
    """Function middleware that logs function calls."""

    async def process(
        self,
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        function_name = context.function.name
        print(f"[LoggingFunctionMiddleware] About to call function: {function_name}.")

        start_time = time.time()

        await next(context)

        end_time = time.time()
        duration = end_time - start_time

        print(f"[LoggingFunctionMiddleware] Function {function_name} completed in {duration:.5f}s.")
# </class_based>


# ===========================================================================
# Section 2 — Function-based middleware
# ===========================================================================

# <function_based>
async def security_agent_middleware(
    context: AgentContext,
    next: Callable[[AgentContext], Awaitable[None]],
) -> None:
    """Agent middleware that checks for security violations."""
    # Check for potential security violations in the query
    # For this example, we'll check the last user message
    last_message = context.messages[-1] if context.messages else None
    if last_message and last_message.text:
        query = last_message.text
        if "password" in query.lower() or "secret" in query.lower():
            print("[SecurityAgentMiddleware] Security Warning: Detected sensitive information, blocking request.")
            # Simply don't call next() to prevent execution
            return

    print("[SecurityAgentMiddleware] Security check passed.")
    await next(context)


async def logging_function_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """Function middleware that logs function calls."""
    function_name = context.function.name
    print(f"[LoggingFunctionMiddleware] About to call function: {function_name}.")

    start_time = time.time()

    await next(context)

    end_time = time.time()
    duration = end_time - start_time

    print(f"[LoggingFunctionMiddleware] Function {function_name} completed in {duration:.5f}s.")
# </function_based>


# ===========================================================================
# Section 3 — Decorator-based middleware
# ===========================================================================

# <decorator_based>
@agent_middleware  # Decorator marks this as agent middleware - no type annotations needed
async def simple_agent_middleware(context, next):  # type: ignore - parameters intentionally untyped to demonstrate decorator functionality
    """Agent middleware that runs before and after agent execution."""
    print("[Agent MiddlewareTypes] Before agent execution")
    await next(context)
    print("[Agent MiddlewareTypes] After agent execution")


@function_middleware  # Decorator marks this as function middleware - no type annotations needed
async def simple_function_middleware(context, next):  # type: ignore - parameters intentionally untyped to demonstrate decorator functionality
    """Function middleware that runs before and after function calls."""
    print(f"[Function MiddlewareTypes] Before calling: {context.function.name}")  # type: ignore
    await next(context)
    print(f"[Function MiddlewareTypes] After calling: {context.function.name}")  # type: ignore
# </decorator_based>


# ===========================================================================
# Run each approach
# ===========================================================================

# <run_agent>
async def main() -> None:
    """Run all three middleware styles to show they are equivalent."""
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with AzureCliCredential() as credential:
        # --- Class-based ---
        print("=== Class-based MiddlewareTypes Example ===")
        async with AzureAIAgentClient(credential=credential).as_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather,
            middleware=[SecurityAgentMiddleware(), LoggingFunctionMiddleware()],
        ) as agent:
            print("\n--- Normal Query ---")
            query = "What's the weather like in Seattle?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result.text}\n")

            print("--- Security Test ---")
            query = "What's the password for the weather service?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result.text}\n")

        # --- Function-based ---
        print("=== Function-based MiddlewareTypes Example ===")
        async with AzureAIAgentClient(credential=credential).as_agent(
            name="WeatherAgent",
            instructions="You are a helpful weather assistant.",
            tools=get_weather,
            middleware=[security_agent_middleware, logging_function_middleware],
        ) as agent:
            print("\n--- Normal Query ---")
            query = "What's the weather like in Tokyo?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result.text if result.text else 'No response'}\n")

            print("--- Security Test ---")
            query = "What's the secret weather password?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result.text if result.text else 'No response'}\n")

        # --- Decorator-based ---
        print("=== Decorator MiddlewareTypes Example ===")
        async with AzureAIAgentClient(credential=credential).as_agent(
            name="TimeAgent",
            instructions="You are a helpful time assistant. Call get_current_time when asked about time.",
            tools=get_current_time,
            middleware=[simple_agent_middleware, simple_function_middleware],
        ) as agent:
            query = "What time is it?"
            print(f"User: {query}")
            result = await agent.run(query)
            print(f"Agent: {result.text if result.text else 'No response'}")


if __name__ == "__main__":
    asyncio.run(main())
# </run_agent>
