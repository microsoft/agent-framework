# TypeSafe AI Package (`agent-framework-typesafe`)

Integration with TypeSafe AI System One models, including Jev.

## Public API

- **`TypeSafeChatClient`** - Adapts TypeSafe's structured decision API to the Agent Framework chat client contract.
- **`TypeSafeChatOptions`** - Uses `response_format` for the required TypeSafe `Questions` mapping.

## Behavioral Contract

- Calls always return structured `SystemOneResponse` data. This provider does not generate free-form chat text.
- Every call requires `response_format` to contain at least one TypeSafe `Noul`, `Choice`, or `Score` question.
- Streaming, tools, and non-text message content are not supported.
- The connector forwards `response_format` as the TypeSafe SDK `questions` argument and internally uses
  `SystemOneResponse` as the response model.
- An injected `AsyncTypeSafeClient` is caller-owned. A client created by `TypeSafeChatClient` is closed by
  `close()` or the async context manager.
- Settings use `load_settings`; the API key is required only when the connector creates the SDK client.

## Import Path

This package is alpha and is not included in `agent-framework-core[all]`.

```python
from agent_framework_typesafe import TypeSafeChatClient, TypeSafeChatOptions
```
