---
status: proposed
contact: eavanvalkenburg
date: 2026-01-20
deciders: eavanvalkenburg, markwallace-microsoft, sphenry, alliscode, johanst, brettcannon
consulted: taochenosu, moonbox3, dmytrostruk, giles17
---

# Python Client and Agent Composition

## Context and Problem Statement

In Python we currently use a set of decorators that can be applied to ChatClients and Agents: function calling, telemetry, and middleware. However, we do not allow users to compose these themselves. For example, a user cannot create a ChatClient that passes tools to an API but doesn't invoke them locally, or only enable telemetry on a chat client but not on the agent.

Up to this point, this has been a sensible decision because it makes getting started very easy. However, as we add more features and more ways to customize behavior, this becomes a limitation.

We have also seen latency issues, and every decorator adds overhead. Being able to compose a client or agent with only the features you need would help with performance, and it would make the tradeoffs explicit. See also the [ChatClientBuilderExtensions in the C# version](https://github.com/dotnet/extensions/tree/main/src/Libraries/Microsoft.Extensions.AI/ChatCompletion) for reference.

## Decision Drivers

- Ease of use for new users
- Flexibility in composing client and agent features
- Maintainability of the codebase
- Performance considerations
- Extensibility for third-party additions

## Approaches for Adding Functionality

We define two primary approaches for adding functionality to ChatClients and Agents:

### Approach 1: Mixin Class (Built-in Functionality)

A **Mixin** is a class that provides additional attributes and method overrides through multiple inheritance. Mixins are used for functionality that should **always be present** and is fundamental to how the class operates.

**Characteristics:**
- Defined as a separate class that is inherited alongside the base class
- Adds attributes to the class (e.g., configuration, state)
- Overrides methods while preserving the method signature and return type
- Uses `super()` to call the next class in the MRO (Method Resolution Order)
- Functionality is always available on all instances of the class
- Cannot be opted out of at runtime (it's part of the class definition)
- Low overhead since it's baked into the class hierarchy

**Example:**
```python
class SampleMixin:
    """Mixin that adds functionality to a chat client."""

    sample_config: Configuration | None = None  # Adds attribute

    async def get_response(self, messages, *, thread: AgentThread, stream: bool = False, options: dict | None = None) -> ChatResponse:

        # prepare
        options.setdefault("sample_option", True)

        # Override method, keeping same signature and return type
        response = await super().get_response(messages=messages, thread=thread, stream=stream, options=options)

        # do something with response

        return response


class OpenAIChatClient(SampleMixin, BaseChatClient):
    """OpenAI client with function invocation support baked in."""
    ...
```

**When to use Mixins:**
- The functionality is essential to how the class operates
- All users will need this functionality
- The functionality needs access to internal class state
- The method signature and return type must remain unchanged
- Order of execution relative to other class methods is important

### Approach 2: Wrapper Class (Optional Functionality)

A **Wrapper** is used for **optional functionality** that users might want to add to a ChatClient or Agent. Wrappers implement the same protocol as the wrapped class and delegate calls while adding behavior.

**Characteristics:**
- Applied at instantiation time by users
- Can be opted in or out of per instance
- Can be composed in different orders
- Each wrapper adds a small overhead
- Suitable for features that are genuinely optional
- Third parties can create their own wrappers

**Example:**
```python
class CachingChatClient:
    """Wrapper that adds caching to any chat client."""

    def __init__(self, inner_client: ChatClientProtocol, cache: Cache):
        self._inner = inner_client
        self._cache = cache

    @property
    def additional_properties(self) -> dict[str, Any]:
        return self._inner.additional_properties

    async def get_response(self, messages, **kwargs) -> ChatResponse:
        # Check cache first
        cache_key = self._compute_cache_key(messages, **kwargs)
        if cached := await self._cache.get(cache_key):
            return cached

        # Delegate to inner client
        response = await self._inner.get_response(messages, **kwargs)

        # Store in cache
        await self._cache.set(cache_key, response)
        return response

    def get_streaming_response(self, messages, **kwargs) -> AsyncIterable[ChatResponseUpdate]:
        # Streaming typically bypasses cache, delegate directly
        return self._inner.get_streaming_response(messages, **kwargs)


# Usage: wrap any client with caching
client = OpenAIChatClient(...)
client = CachingChatClient(client, cache=InMemoryCache())

# Can compose multiple wrappers
client = LoggingChatClient(CachingChatClient(OpenAIChatClient(...), cache), logger)
```

**When to use Wrappers:**
- The functionality is optional and not all users need it
- Users should be able to compose different combinations
- Third-party extensibility is desired
- The overhead of the wrapper is acceptable for the use case
- The functionality needs additional methods on the class, not just overrides, for instance like the [DistributedCachingChatClient](https://github.com/dotnet/extensions/blob/main/src/Libraries/Microsoft.Extensions.AI/ChatCompletion/DistributedCachingChatClient.cs) in dotnet.

## Current State

### ChatClient Decorators

| Decorator | Purpose | Currently Applied To |
|-----------|---------|---------------------|
| `@use_function_invocation` | Enables automatic function/tool calling and result handling | All ChatClient implementations |
| `@use_instrumentation` | Adds OpenTelemetry tracing and metrics for chat operations | All ChatClient implementations |
| `@use_chat_middleware` | Enables middleware pipeline for chat operations | BaseChatClient |

### ChatAgent Decorators

| Decorator | Purpose | Currently Applied To |
|-----------|---------|---------------------|
| `@use_agent_middleware` | Enables middleware pipeline for agent operations | ChatAgent |
| `@use_agent_instrumentation` | Adds OpenTelemetry tracing for agent operations | ChatAgent |

## Decision Outcome

For each decorator, we evaluate whether it should be a **Mixin** (always present) or a **Wrapper** (optional), based on the decision drivers above.

---

### ChatClient Decisions

#### 1. Function Invocation (`@use_function_invocation`)

**Decision: Convert to Mixin**

**Rationale:**
- Function invocation is a core capability that most users expect from a chat client
- We should improve and clarify the configuration via the additional attributes
- The mixin approach allows the functionality to be built into the class hierarchy
- When no tools are provided or config is disabled, the overhead is minimal
- Keeps the same method signatures and return types

---

#### 2. Telemetry/Instrumentation (`@use_instrumentation`)

**Decision: Keep as Mixin, Environment-Controlled**

**Rationale:**
- Telemetry is already opt-in via environment variable (`ENABLE_INSTRUMENTATION`)
- When disabled, the overhead is minimal (a simple boolean check)
- Users shouldn't need to remember to wrap every client with telemetry
- Consistent telemetry across all clients is valuable
- The decorator already checks `OBSERVABILITY_SETTINGS.ENABLED` before doing any work

**Implementation:**
- Rebuild as a mixin class for all ChatClient implementations
- Use `capture_usage` attribute to control whether to capture usage metrics, might be enough to do `_capture_usage` as it is more a agent type that determines this then the user.
- Add otel_provider_name attribute based on a default per client.
- Continue using `ENABLE_INSTRUMENTATION` environment variable to control

---

#### 3. Middleware (`@use_chat_middleware`)

**Decision: Keep as Mixin, Parameter-Driven**

**Rationale:**
- Middleware is already opt-in via the `middleware` parameter on ChatClient
- When no middleware is provided, overhead is minimal
- The infrastructure needs to be present for middleware to work
- Users pass middleware at instantiation or call time

**Implementation:**
- Rebuild as a mixin class for all ChatClient implementations
- Middleware is controlled via `middleware` parameter
- Minimal changes needed to current approach

---

### ChatAgent Decisions

#### 4. Agent Middleware (`@use_agent_middleware`)

**Decision: Keep as Mixin, Parameter-Driven**

**Rationale:**
- Middleware is already opt-in via the `middleware` parameter on ChatAgent
- When no middleware is provided, overhead is minimal
- The infrastructure needs to be present for middleware to work
- Middleware can be agent-level, function-level, or chat-level - all managed together

**Implementation:**
- Rebuild as a mixin class for all Agent implementations that need it
- Middleware is controlled via `middleware` parameter
- Minimal changes needed to current approach

---

#### 5. Agent Instrumentation (`@use_agent_instrumentation`)

**Decision: Keep as Mixin, Environment-Controlled**

**Rationale:**
- Same rationale as ChatClient telemetry
- Consistent observability is valuable
- Opt-in via environment variable
- Minimal overhead when disabled
- The `capture_usage` parameter allows avoiding double-counting with client telemetry

**Implementation:**
- Rebuild as a mixin class for all Agent implementations
- Continue using `ENABLE_INSTRUMENTATION` environment variable to control
- Minimal changes needed to current approach

---

## Summary Table

| Component | Current Decorator | Decision | Control Mechanism |
|-----------|------------------|----------|-------------------|
| ChatClient - Function Invocation | `@use_function_invocation` | Mixin | extra class attributes |
| ChatClient - Telemetry | `@use_instrumentation` | Mixin | Environment variable |
| ChatClient - Middleware | `@use_chat_middleware` | Mixin | Constructor parameter |
| ChatAgent - Middleware | `@use_agent_middleware` | Mixin | Constructor parameter |
| ChatAgent - Telemetry | `@use_agent_instrumentation` | Mixin | Environment variable |

## Future Considerations

- Additional wrappers could be created for:
  - `CachingChatClient` - for response caching
  - `RetryingChatClient` - for automatic retries with backoff
  - `RateLimitingChatClient` - for rate limiting
- Third parties can create their own wrappers following the same pattern
- Middleware can sometimes be used to do something similar, we should document best practices
- A Wrapper protocol could help standardize third-party implementations
