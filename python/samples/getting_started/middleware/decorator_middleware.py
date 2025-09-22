# Copyright (c) Microsoft. All rights reserved.

import asyncio
import datetime

from agent_framework import (
    agent_middleware,
    function_middleware,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

"""
Decorator Middleware Example

This sample demonstrates how to use @agent_middleware and @function_middleware decorators
to explicitly mark middleware functions without requiring type annotations.

The framework supports the following middleware detection scenarios:

1. Both decorator and parameter type specified:
   - Validates that they match (e.g., @agent_middleware with AgentRunContext)
   - Throws exception if they don't match for safety

2. Only decorator specified:
   - Relies on decorator to determine middleware type
   - No type annotations needed - framework handles context types automatically

3. Only parameter type specified:
   - Uses type annotations (AgentRunContext, FunctionInvocationContext) for detection

4. Neither decorator nor parameter type specified:
   - Throws exception requiring either decorator or type annotation
   - Prevents ambiguous middleware that can't be properly classified

Key benefits of decorator approach:
- No type annotations needed (simpler syntax)
- Explicit middleware type declaration
- Clear intent in code
- Prevents type mismatches
"""


def get_current_time() -> str:
    """Get the current time."""
    return f"Current time is {datetime.datetime.now().strftime('%H:%M:%S')}"


@agent_middleware  # Decorator marks this as agent middleware - no type annotations needed
async def simple_agent_middleware(context, next):  # type: ignore - parameters intentionally untyped to demonstrate decorator functionality
    """Agent middleware that runs before and after agent execution."""
    print("[Agent Middleware] Before agent execution")
    await next(context)
    print("[Agent Middleware] After agent execution")


@function_middleware  # Decorator marks this as function middleware - no type annotations needed
async def simple_function_middleware(context, next):  # type: ignore - parameters intentionally untyped to demonstrate decorator functionality
    """Function middleware that runs before and after function calls."""
    print(f"[Function Middleware] Before calling: {context.function.name}")  # type: ignore
    await next(context)
    print(f"[Function Middleware] After calling: {context.function.name}")  # type: ignore


async def main() -> None:
    """Example demonstrating decorator-based middleware."""
    print("=== Decorator Middleware Example ===")

    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    async with (
        AzureCliCredential() as credential,
        FoundryChatClient(async_credential=credential).create_agent(
            name="TimeAgent",
            instructions="You are a helpful time assistant. Call get_current_time when asked about time.",
            tools=get_current_time,
            middleware=[simple_agent_middleware, simple_function_middleware],
        ) as agent,
    ):
        query = "What time is it?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result.text if result.text else 'No response'}")


if __name__ == "__main__":
    asyncio.run(main())
