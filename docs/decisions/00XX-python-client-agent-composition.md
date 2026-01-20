---
status: proposed
contact: eavanvalkenburg
date: 2026-01-12
deciders: eavanvalkenburg, markwallace-microsoft,  sphenry, alliscode, johanst, brettcannon
consulted: taochenosu, moonbox3, dmytrostruk, giles17
---

# Python Client and Agent Composition

## Context and Problem Statement

In Python we currently use a set of decorators that can be applied to ChatClients and Agents, those are for function calling, telemetry and middleware. However we currently do not allow a user to compose these themselves, for example to create a ChatClient that does not do function calling, but does have tools being passed to a API. Or to only have telemetry enabled on a chat client, but not on the agent. Up unto this point, that has been a sensible decision because it makes getting started very easy. However as we add more features, and more ways to customize the behavior of clients and agents, this becomes a limitation.

We have also seen latency issues, and every decorator adds some overhead, so being able to compose a client or agent with only the features you need would help with that as well, and it will at least make this a very explicit tradeoff. Note all the ChatClientBuilderExtensions in the C# version [here](https://github.com/dotnet/extensions/tree/main/src/Libraries/Microsoft.Extensions.AI/ChatCompletion)

## Decision Drivers

- Ease of use for new users
- Flexibility in composing client and agent features
- Maintainability of the codebase
- Performance considerations

## Considered Options

1. Current design with fixed decorators
2. Decorator based composition
3. Builder pattern with fluent API
4. Builder pattern with wrapper-based composition
5. Parameter driven composition

## Options

### Option 1: Current design with fixed decorators
Currently each ChatClient implementation and the ChatAgent class have fixed decorators applied to them. This makes it very easy for new users to get started, but it limits flexibility and can lead to performance overhead.

- Good: getting started is very easy
- Good: code is centralized and maintainable
- Good: consistent behavior across all clients
- Bad: limited flexibility in composing clients and agents
- Bad: potential performance overhead from unnecessary decorators
- Bad: users cannot opt-out of features they don't need
- Bad: becomes increasingly complex as we add more features

### Option 2: Decorator based composition
Allow users to manually apply decorators to compose their clients and agents with desired capabilities.

Example:
```python
from agent_framework import with_telemetry, with_function_calling

client = OpenAIChatClient(...)
client = with_function_calling(client)
client = with_telemetry(client)
```

- Good: familiar Python pattern
- Good: explicit control over which features are enabled
- Good: no new abstractions needed
- Good: users can see the exact composition order
- Good: performance optimization by only including needed decorators
- Bad: verbose and repetitive for common cases
- Bad: order of decorators matters and can be confusing
- Bad: no validation of decorator compatibility or ordering (limited validation could be done, through checking of flags on clients)
- Bad: harder to discover available decorators and their usage

### Option 3: Builder pattern with fluent API
Use a builder class with named methods for each capability. The builder constructs clients through a pipeline pattern.

Example:
```python
client = ChatClientBuilder(OpenAIChatClient(...)) \
    .with_telemetry(logger_factory) \
    .with_function_calling() \
    .with_capability(custom_capability) \
    .build()
```

- Good: clear and discoverable API
- Good: can validate configuration before building
- Good: follows established builder patterns, for instance for Workflows
- Good: easier to understand for new users (method names are self-documenting)
- Good: can provide sensible defaults while allowing customization
- Good: can validate ordering and either raise or adjust as needed
- Bad: all methods must be defined in core builder
- Bad: method explosion as features grow
- Bad: more verbose than current approach for simple cases
- Bad: steeper learning curve compared to current approach
- Bad: requires new builder abstraction
- Note: A generic method like `.with(wrapper)` could be added alongside named methods to enable third-party extensibility (combining advantages of Option 4), allowing both discoverable built-in methods and flexible custom wrappers

### Option 4: Builder pattern with wrapper-based composition
Use a builder class with a generic method (e.g., `use`) that accepts capability decorators. Each capability is implemented as a class decorator.

Example:
```python
client = ChatClientBuilder(OpenAIChatClient(...)) \
    .use(TelemetryWrapper(logger_factory)) \
    .use(FunctionCallingWrapper(...)) \
    .use(custom_wrapper) \
    .build()
```

- Good: very flexible and extensible by third parties
- Good: clear separation between core client and capabilities
- Good: can validate some configuration before building
- Good: supports both simple and complex use cases
- Good: easier to test individual capabilities
- Good: third parties can create their own wrapper classes without modifying core
- Bad: more verbose than current approach for simple cases
- Bad: less discoverable than fluent methods (need to know wrapper class names)
- Bad: steeper learning curve for new users
- Bad: requires new builder abstraction and wrapper classes
- Bad: wrapper objects add another layer of abstraction

### Option 5: Parameter driven composition
Add parameters to the client/agent constructors to control which features are enabled.

Example:
```python
client = OpenAIChatClient(
    ...,
    enable_telemetry=True,
    enable_function_calling=False,
    middleware=[custom_middleware1, custom_middleware2]
)
```

- Good: simple and intuitive API
- Good: easy to understand for new users
- Good: works well for binary enable/disable flags
- Good: configuration can be loaded from files/environment
- Good: still relatively easy to get started
- Bad: can lead to many constructor parameters as features grow
- Bad: less flexible for custom middleware with complex configuration
- Bad: parameter explosion problem (each feature needs its own parameter)
- Bad: depending on the setup, might still have overhead from unused features

## Decision Outcome

Option 2: Decorator based composition

We currently have three decorators on ChatClients: function calling, telemetry and middleware. And two on Agents: telemetry and middleware.

Details:
- ChatClient:
    - Function calling, updated to this new pattern, move FunctionInvocationConfiguration into the decorator arguments
    - Telemetry, updated to this new pattern, keep `capture_usage` parameter
    - Middleware, since that is a parameter on the ChatClient already, build the code paths into the BaseChatClient, remove the decorator.
- Agent:
    - Telemetry, updated to this new pattern, keep `capture_usage` parameter
        - Should this look for and if necessary auto apply telemetry to the underlying client (for ChatAgent)?
        - Look into a single telemetry decorator that can be applied to both ChatClients and Agents?
    - Middleware, since that is a parameter on the ChatAgent already, build the code paths into the ChatAgent, remove the decorator.
