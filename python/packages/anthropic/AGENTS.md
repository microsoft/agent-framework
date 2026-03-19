# Anthropic Package (agent-framework-anthropic)

Integration with Anthropic's Claude API.

## Main Classes

- **`AnthropicClient`** - Full-featured chat client for Anthropic Claude models (includes middleware, telemetry, and function invocation support)
- **`RawAnthropicClient`** - Low-level chat client without middleware, telemetry, or function invocation layers. Use this only when you need to compose custom layers manually.
- **`AnthropicChatOptions`** - Options TypedDict for Anthropic-specific parameters

## Client Architecture

`AnthropicClient` composes the standard public layer stack around `RawAnthropicClient`:

```
AnthropicClient
  └─ FunctionInvocationLayer   ← owns the tool/function calling loop
      └─ ChatMiddlewareLayer   ← applies chat middleware per model call
          └─ ChatTelemetryLayer ← per-call telemetry (inside middleware)
              └─ RawAnthropicClient ← raw Anthropic API calls
```

Most users should use `AnthropicClient`. Use `RawAnthropicClient` only if you need to apply a custom subset of layers.

## Usage

```python
from agent_framework.anthropic import AnthropicClient

client = AnthropicClient(model_id="claude-sonnet-4-20250514")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.anthropic import AnthropicClient, RawAnthropicClient
# or directly:
from agent_framework_anthropic import AnthropicClient, RawAnthropicClient
```
