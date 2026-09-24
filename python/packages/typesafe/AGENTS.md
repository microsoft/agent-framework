# TypeSafe AI Package (`agent-framework-typesafe`)

Integration with TypeSafe AI System One models, including Jev.

## Public API

- **`TypeSafeChatClient`** - Adds function invocation, middleware, and telemetry to the TypeSafe transport.
- **`RawTypeSafeChatClient`** - Provider transport that can emit constrained function calls but does not execute
  them; it has no function-invocation, middleware, or telemetry layers.
- **`TypeSafeChatOptions`** - Uses `response_format` for the required TypeSafe `Questions` mapping.

## Behavioral Contract

- Calls always return structured `SystemOneResponse` data. This provider does not generate free-form chat text.
- Every call requires `response_format` to contain at least one TypeSafe `Noul`, `Choice`, or `Score` question.
- Streaming and non-text message content are not supported.
- Tool calling defaults to one call per run; callers can opt into sequential round trips with
  `FunctionInvocationConfiguration.max_function_calls`. Closed-set schemas support constants, enums/Literals,
  booleans, and arrays of enums/Literals. Optional supported arguments use a presence question so omitted values
  preserve tool defaults.
- Agent-provided MCP tools work when their discovered function schemas fit the supported subset. Direct raw/client
  calls must receive expanded `FunctionTool` instances.
- A tool is excluded if any declared argument or object/argument/array-item schema constraint is unsupported. Tool,
  property, enum, and cumulative question counts are bounded before question materialization, and constrained arrays
  are rejected.
- The connector forwards `response_format` as the TypeSafe SDK `questions` argument and internally uses
  `SystemOneResponse` as the response model.
- An injected `AsyncTypeSafeClient` is caller-owned. A client created by `TypeSafeChatClient` is closed by
  `close()` or the async context manager.
- Connector-owned clients restore the configured API key at the HTTP transport boundary because TypeSafe SDK 0.7.1
  keeps the prepared authorization header redacted; transport-level tests must verify the outgoing header.
- Settings use `load_settings`; the API key is required only when the connector creates the SDK client.
- Injected SDK clients remain authoritative: ambient model and endpoint settings are not applied to them.

## Import Path

This package is alpha and is not included in `agent-framework-core[all]`.

```python
from agent_framework_typesafe import RawTypeSafeChatClient, TypeSafeChatClient, TypeSafeChatOptions
```
