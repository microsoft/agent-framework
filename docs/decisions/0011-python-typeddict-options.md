---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: eavanvalkenburg
date: 2026-01-08
deciders: eavanvalkenburg, markwallace-microsoft,  sphenry, alliscode, johanst, brettcannon
consulted: taochenosu, moonbox3, dmytrostruk, giles17
---

# Leveraging TypedDict and Generic Options in Python Chat Clients

## Context and Problem Statement

The Agent Framework Python SDK provides multiple chat client implementations for different providers (OpenAI, Anthropic, Azure AI, Bedrock, Ollama, etc.). Each provider has unique configuration options beyond the common parameters defined in `ChatOptions`. Currently, developers using these clients lack type safety and IDE autocompletion for provider-specific options, leading to runtime errors and a poor developer experience.

How can we provide type-safe, discoverable options for each chat client while maintaining a consistent API across all implementations?

## Decision Drivers

- **Type Safety**: Developers should get compile-time/static analysis errors when using invalid options
- **IDE Support**: Full autocompletion and inline documentation for all available options
- **Extensibility**: Users should be able to define custom options that extend provider-specific options
- **Consistency**: All chat clients should follow the same pattern for options handling
- **Provider Flexibility**: Each provider can expose its unique options without affecting the common interface

## Considered Options

- **Option 1: Status Quo - Class `ChatOptions` with `**kwargs`**
- **Option 2: TypedDict with Generic Type Parameters**

### Option 1: Status Quo - Class `ChatOptions` with `**kwargs`

The current approach uses a base `ChatOptions` Class with common parameters, and provider-specific options are passed via `**kwargs` or loosely typed dictionaries.

```python
# Current usage - no type safety for provider-specific options
response = await client.get_response(
    messages=messages,
    temperature=0.7,
    top_k=40,
    random=42, # No validation
)
```

**Pros:**
- Simple implementation
- Maximum flexibility

**Cons:**
- No type checking for provider-specific options
- No IDE autocompletion for available options
- Runtime errors for typos or invalid options
- Documentation must be consulted for each provider

### Option 2: TypedDict with Generic Type Parameters (Chosen)

Each chat client is parameterized with a TypeVar bound to a provider-specific `TypedDict` that extends `ChatOptions`. This enables full type safety and IDE support.

```python
# Provider-specific TypedDict
class AnthropicChatOptions(ChatOptions, total=False):
    """Anthropic-specific chat options."""
    top_k: int
    thinking: ThinkingConfig
    # ... other Anthropic-specific options

# Generic chat client
class AnthropicChatClient(ChatClientBase[TAnthropicChatOptions]):
    ...

client = AnthropicChatClient(...)

# Usage with full type safety
response = await client.get_response(
    messages=messages,
    options={
        "temperature": 0.7,
        "top_k": 40,
        "random": 42,  # fails type checking and IDE would flag this
    }
)

# Users can extend for custom options
class MyAnthropicOptions(AnthropicChatOptions, total=False):
    custom_field: str


client = AnthropicChatClient[MyAnthropicOptions](...)

# Usage of custom options with full type safety
response = await client.get_response(
    messages=messages,
    options={
        "temperature": 0.7,
        "top_k": 40,
        "custom_field": "value",
    }
)

```

**Pros:**
- Full type safety with static analysis
- IDE autocompletion for all options
- Compile-time error detection
- Self-documenting through type hints
- Users can extend options for their specific needs or advances in models

**Cons:**
- More complex implementation
- Some type: ignore comments needed for TypedDict field overrides
- Minor: Requires TypeVar with default (Python 3.13+ or typing_extensions)

> [NOTE!]
> In .NET this is already achieved through overloads on the `GetResponseAsync` method for each provider-specific options class, e.g., `AnthropicChatOptions`, `OpenAIChatOptions`, etc. So this does not apply to .NET.

### Implementation Details

1. **Base Protocol**: `ChatClientProtocol[TOptions]` is generic over options type, with default set to `ChatOptions` (the new TypedDict)
2. **Provider TypedDicts**: Each provider defines its options extending `ChatOptions`
    They can even override fields with type=None to indicate they are not supported.
3. **TypeVar Pattern**: `TProviderOptions = TypeVar("TProviderOptions", bound=TypedDict, default=ProviderChatOptions, contravariant=True)`
4. **Option Translation**: Common options are kept in place,and explicitly documented in the Options class how they are used. (e.g., `user` → `metadata.user_id`) in `_prepare_options` (for Anthropic) to preserve easy use of common options.

## Decision Outcome

Chosen option: **"Option 2: TypedDict with Generic Type Parameters"**, because it provides full type safety, excellent IDE support with autocompletion, and allows users to extend provider-specific options for their use cases. Extended this Generic to ChatAgents in order to also properly type the options used in agent construction and run methods.

See [typed_options.py](../../python/samples/getting_started/chat_client/typed_options.py) for a complete example demonstrating the usage of typed options with custom extensions.
