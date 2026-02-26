---
status: Accepted
contact: eavanvalkenburg
date: 2026-01-06
deciders: markwallace-microsoft, dmytrostruk, taochenosu, alliscode, moonbox3, sphenry
consulted: sergeymenshykh, rbarreto, dmytrostruk, westey-m
informed:
---

# Simplify Python Get Response API into a single method

## Context and Problem Statement

Currently chat clients must implement two separate methods to get responses, one for streaming and one for non-streaming. This adds complexity to the client implementations and increases the maintenance burden. This was likely done because the .NET version cannot do proper typing with a single method, in Python this is possible and this for instance is also how the OpenAI python client works, this would then also make it simpler to work with the Python version because there is only one method to learn about instead of two.

## Implications of this change

### Current Architecture Overview

The current design has **two separate methods** at each layer:

| Layer | Non-streaming | Streaming |
|-------|---------------|-----------|
| **Protocol** | `get_response()` → `ChatResponse` | `get_streaming_response()` → `AsyncIterable[ChatResponseUpdate]` |
| **BaseChatClient** | `get_response()` (public) | `get_streaming_response()` (public) |
| **Implementation** | `_inner_get_response()` (private) | `_inner_get_streaming_response()` (private) |

### Key Usage Areas Identified

#### 1. **ChatAgent** (_agents.py)
- `run()` → calls `self.chat_client.get_response()`
- `run_stream()` → calls `self.chat_client.get_streaming_response()`

These are parallel methods on the agent, so consolidating the client methods would **not break** the agent API. You could keep `agent.run()` and `agent.run_stream()` unchanged while internally calling `get_response(stream=True/False)`.

#### 2. **Function Invocation Decorator** (_tools.py)
This is **the most impacted area**. Currently:
- `_handle_function_calls_response()` decorates `get_response`
- `_handle_function_calls_streaming_response()` decorates `get_streaming_response`
- The `use_function_invocation` class decorator wraps **both methods separately**

**Impact**: The decorator logic is almost identical (~200 lines each) with small differences:
- Non-streaming collects response, returns it
- Streaming yields updates, returns async iterable

With a unified method, you'd need **one decorator** that:
- Checks the `stream` parameter
- Uses `@overload` to determine return type
- Handles both paths with conditional logic
- The new decorator could be applied just on the method, instead of the whole class.

This would **reduce code duplication** but add complexity to a single function.

#### 3. **Observability/Instrumentation** (observability.py)
Same pattern as function invocation:
- `_trace_get_response()` wraps `get_response`
- `_trace_get_streaming_response()` wraps `get_streaming_response`
- `use_instrumentation` decorator applies both

**Impact**: Would need consolidation into a single tracing wrapper.

#### 4. **Chat Middleware** (_middleware.py)
The `use_chat_middleware` decorator also wraps both methods separately with similar logic.

#### 5. **AG-UI Client** (_client.py)
Wraps both methods to unwrap server function calls:
```python
original_get_streaming_response = chat_client.get_streaming_response
original_get_response = chat_client.get_response
```

#### 6. **Provider Implementations** (all subpackages)
All subclasses implement both `_inner_*` methods, except:
- OpenAI Assistants Client (and similar clients, such as Foundry Agents V1) - it implements `_inner_get_response` by calling `_inner_get_streaming_response`

### Implications of Consolidation

| Aspect | Impact |
|--------|--------|
| **Type Safety** | Overloads work well: `@overload` with `Literal[True]` → `AsyncIterable`, `Literal[False]` → `ChatResponse`. Runtime return type based on `stream` param. |
| **Breaking Change** | **Major breaking change** for anyone implementing custom chat clients. They'd need to update from 2 methods to 1 (or 2 inner methods to 1). |
| **Decorator Complexity** | All 3 decorator systems (function invocation, middleware, observability) would need refactoring to handle both paths in one wrapper. |
| **Code Reduction** | Significant reduction in _tools.py (~200 lines of near-duplicate code) and other decorators. |
| **Samples/Tests** | Many samples call `get_streaming_response()` directly - would need updates. |
| **Protocol Simplification** | `ChatClientProtocol` goes from 2 methods + 1 property to 1 method + 1 property. |

### Recommendation

The consolidation makes sense architecturally, but consider:

1. **The overload pattern with `stream: bool`** works well in Python typing:
   ```python
   @overload
   async def get_response(self, messages, *, stream: Literal[True] = True, ...) -> AsyncIterable[ChatResponseUpdate]: ...
   @overload
   async def get_response(self, messages, *, stream: Literal[False] = False, ...) -> ChatResponse: ...
   ```

2. **The decorator complexity** is the biggest concern. The current approach of separate decorators for separate methods is cleaner than conditional logic inside one wrapper.

## Decision Drivers

- Reduce code needed to implement a Chat Client, simplify the public API for chat clients
- Reduce code duplication in decorators and middleware
- Maintain type safety and clarity in method signatures

## Considered Options

1. Status quo: Keep separate methods for streaming and non-streaming
2. Consolidate into a single `get_response` method with a `stream` parameter
3. Option 2 plus merging `agent.run` and `agent.run_stream` into a single method with a `stream` parameter as well

## Option 1: Status Quo
- Good: Clear separation of streaming vs non-streaming logic
- Good: Aligned with .NET design, although it is already `run` for Python and `RunAsync` for .NET
- Bad: Code duplication in decorators and middleware
- Bad: More complex client implementations

## Option 2: Consolidate into Single Method
- Good: Simplified public API for chat clients
- Good: Reduced code duplication in decorators
- Good: Smaller API footprint for users to get familiar with
- Good: People using OpenAI directly already expect this pattern
- Bad: Increased complexity in decorators and middleware
- Bad: Less alignment with .NET design (`get_response(stream=True)` vs `GetStreamingResponseAsync`)

## Option 3: Consolidate + Merge Agent and Workflow Methods
- Good: Further simplifies agent and workflow implementation
- Good: Single method for all chat interactions
- Good: Smaller API footprint for users to get familiar with
- Good: People using OpenAI directly already expect this pattern
- Good: Workflows internally already use a single method (_run_workflow_with_tracing), so would eliminate public API duplication as well, with hardly any code changes
- Bad: More breaking changes for agent users
- Bad: Increased complexity in agent implementation
- Bad: More extensive misalignment with .NET design (`run(stream=True)` vs `RunStreamingAsync` in addition to `get_response` change)

## Misc

Smaller questions to consider:
- Should default be `stream=False` or `stream=True`? (Current is False)
    - Default to `False` makes it simpler for new users, as non-streaming is easier to handle.
    - Default to `False` aligns with existing behavior.
    - Streaming tends to be faster, so defaulting to `True` could improve performance for common use cases.
    - Should this differ between ChatClient, Agent and Workflows? (e.g., Agent and Workflow defaults to streaming, ChatClient to non-streaming)

## Decision Outcome

Chosen Option: **Option 3: Consolidate + Merge Agent and Workflow Methods**

Since this is the most pythonic option and it reduces the API surface and code duplication the most, we will go with this option.
We will keep the default of `stream=False` for all methods to maintain backward compatibility and simplicity for new users.

# Appendix
## Code Samples for Consolidated Method

### Python - Option 3: Direct ChatClient + Agent with Single Method

```python
# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from pydantic import Field


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    # Example 1: Direct ChatClient usage with single method
    client = OpenAIChatClient()
    message = "What's the weather in Amsterdam and in Paris?"

    # Non-streaming usage
    print(f"User: {message}")
    response = await client.get_response(message, tools=get_weather)
    print(f"Assistant: {response.text}")

    # Streaming usage - same method, different parameter
    print(f"\nUser: {message}")
    print("Assistant: ", end="")
    async for chunk in client.get_response(message, tools=get_weather, stream=True):
        if chunk.text:
            print(chunk.text, end="")
    print("")

    # Example 2: Agent usage with single method
    agent = ChatAgent(
        chat_client=client,
        tools=get_weather,
        name="WeatherAgent",
        instructions="You are a weather assistant.",
    )
    thread = agent.get_new_thread()

    # Non-streaming agent
    print(f"\nUser: {message}")
    result = await agent.run(message, thread=thread) # default would be stream=False
    print(f"{agent.name}: {result.text}")

    # Streaming agent - same method, different parameter
    print(f"\nUser: {message}")
    print(f"{agent.name}: ", end="")
    async for update in agent.run(message, thread=thread, stream=True):
        if update.text:
            print(update.text, end="")
    print("")


if __name__ == "__main__":
    asyncio.run(main())
```

### .NET - Current pattern for comparison

```csharp
// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
    .GetChatClient(deploymentName)
    .CreateAIAgent(
        instructions: "You are good at telling jokes about pirates.",
        name: "PirateJoker");

// Non-streaming: Returns a string directly
Console.WriteLine("=== Non-streaming ===");
string result = await agent.RunAsync("Tell me a joke about a pirate.");
Console.WriteLine(result);

// Streaming: Returns IAsyncEnumerable<AgentUpdate>
Console.WriteLine("\n=== Streaming ===");
await foreach (AgentUpdate update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.Write(update);
}
Console.WriteLine();

```
