---
status: Proposed
contact: eavanvalkenburg
date: 2026-01-06
deciders: markwallace-microsoft, dmytrostruk, taochenosu, alliscode, moonbox3
consulted: sergeymenshykh, rbarreto, dmytrostruk, westey-m
informed:
---

# Simplify Python Get Response API into a single method

## Context and Problem Statement

Currently chat clients must implement two separate methods to get responses, one for streaming and one for non-streaming. This adds complexity to the client implementations and increases the maintenance burden. This was likely done because the dotnet version cannot do proper typing with a single method, in Python this is possible and this for instance is also how the OpenAI python client works.

## Implications of this change

### Current Architecture Overview

The current design has **two separate methods** at each layer:

| Layer | Non-streaming | Streaming |
|-------|---------------|-----------|
| **Protocol** | `get_response()` → `ChatResponse` | `get_streaming_response()` → `AsyncIterable[ChatResponseUpdate]` |
| **BaseChatClient** | `get_response()` (public) | `get_streaming_response()` (public) |
| **Implementation** | `_inner_get_response()` (private) | `_inner_get_streaming_response()` (private) |

### Key Usage Areas Identified

#### 1. **ChatAgent** (_agents.py and _agents.py)
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
- OpenAI Assistants Client - it implements `_inner_get_response` by calling `_inner_get_streaming_response`

### Implications of Consolidation

| Aspect | Impact |
|--------|--------|
| **Type Safety** | Overloads work well: `@overload` with `Literal[True]` → `AsyncIterable`, `Literal[False]` → `ChatResponse`. Runtime return type based on `stream` param. |
| **Breaking Change** | **Major breaking change** for anyone implementing custom chat clients. They'd need to update from 2 methods to 1 (or 2 inner methods to 1). |
| **Decorator Complexity** | All 3 decorator systems (function invocation, middleware, observability) would need refactoring to handle both paths in one wrapper. |
| **Code Reduction** | Significant reduction in _tools.py (~200 lines of near-duplicate code) and other decorators. |
| **Samples/Tests** | Many samples call `get_streaming_response()` directly - would need updates. |
| **Protocol Simplification** | `ChatClientProtocol` goes from 2 methods + 1 property to 1 method + 1 property. |

### Suggested Migration Path

1. **Keep public `get_streaming_response` as an alias** for backward compatibility:
   ```python
   def get_streaming_response(self, messages, **kwargs):
       return self.get_response(messages, stream=True, **kwargs)
   ```

2. **Consolidate inner methods first**: Have `_inner_get_response(stream=True/False)` in `BaseChatClient`, allowing subclasses to gradually migrate.

3. **Update decorators** to handle the unified method with conditional streaming logic.

4. **Deprecation warnings** on direct `get_streaming_response()` calls.

### Recommendation

The consolidation makes sense architecturally, but consider:

1. **The overload pattern with `stream: bool`** works well in Python typing:
   ```python
   @overload
   async def get_response(self, messages, *, stream: Literal[True], ...) -> AsyncIterable[ChatResponseUpdate]: ...
   @overload
   async def get_response(self, messages, *, stream: Literal[False] = False, ...) -> ChatResponse: ...
   ```

2. **The decorator complexity** is the biggest concern. The current approach of separate decorators for separate methods is cleaner than conditional logic inside one wrapper.

3. **Backward compatibility** should be maintained with deprecation, not immediate removal.

## Decision Drivers

- Reduce code needed to implement a Chat Client, simplify the public API for chat clients
- Reduce code duplication in decorators and middleware
- Maintain type safety and clarity in method signatures

## Considered Options

1. Status quo: Keep separate methods for streaming and non-streaming
1. Consolidate into a single `get_response` method with a `stream` parameter

## Option 1: Status Quo
- Good: Clear separation of streaming vs non-streaming logic
- Good: Aligned with dotnet design
- Bad: Code duplication in decorators and middleware
- Bad: More complex client implementations

## Option 2: Consolidate into Single Method
- Good: Simplified public API for chat clients
- Good: Reduced code duplication in decorators
- Bad: Increased complexity in decorators and middleware

## Decision Outcome
TBD
