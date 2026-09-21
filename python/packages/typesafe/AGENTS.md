# TypeSafe AI Package (`agent-framework-typesafe`)

Integration with TypeSafe AI System One models, including Jev.

## Public API

- **`TypeSafeChatClient`** - Adapts TypeSafe's structured decision API to the Agent Framework chat client contract.
- **`TypeSafeChatOptions`** - Adds the required TypeSafe `questions` mapping to common chat options.

## Behavioral Contract

- Calls always return structured `SystemOneResponse` data. This provider does not generate free-form chat text.
- Every call requires at least one TypeSafe `Noul`, `Choice`, or `Score` question.
- Streaming, tools, and non-text message content are not supported.
- `response_format` defaults to `SystemOneResponse`; only subclasses of that response type are accepted.
- An injected `AsyncTypeSafeClient` is caller-owned. A client created by `TypeSafeChatClient` is closed by
  `close()` or the async context manager.

## Import Path

This package is alpha and is not included in `agent-framework-core[all]`.

```python
from agent_framework_typesafe import TypeSafeChatClient, TypeSafeChatOptions
```
