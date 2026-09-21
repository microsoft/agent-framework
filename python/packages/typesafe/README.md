# Agent Framework TypeSafe AI

Use [TypeSafe AI](https://docs.typesafe.ai/) System One models, including Jev,
with Microsoft Agent Framework.

This alpha package adapts TypeSafe's structured decision API to the Agent Framework
chat client contract. Jev evaluates application state against explicit typed
questions and returns probabilities and scores. It does not generate ordinary
chat text.

## Installation

```bash
pip install agent-framework-typesafe --pre
```

## Quick start

Set `TYPESAFE_API_KEY`, then create TypeSafe questions and run them through an
Agent Framework `Agent`:

```python
from agent_framework import Agent
from agent_framework_typesafe import TypeSafeChatClient
from typesafe_sdk import Choice, Noul

client = TypeSafeChatClient()
try:
    agent = Agent(
        client=client,
        name="TicketEvaluator",
        instructions="Evaluate the support request using the configured questions.",
    )
    response = await agent.run(
        "Our checkout has failed for three days and we are losing sales.",
        options={
            "response_format": {
                "department": Choice(
                    instructions="Which team should handle this request?",
                    criteria={"billing": None, "technical": None, "sales": None},
                ),
                "urgent": Noul(instructions="Does this request need urgent attention?"),
            },
        },
    )
    print(response.value)
finally:
    await client.close()
```

For this connector, Agent Framework's `response_format` option is the TypeSafe
`Questions` mapping. The connector forwards it as the SDK's `questions` argument
and internally uses `SystemOneResponse` as the actual response model.

## Supported options

| Option | Description |
| --- | --- |
| `response_format` | Required non-empty TypeSafe `Questions` mapping containing `Noul`, `Choice`, or `Score` questions. |
| `model` | Optional per-call model override. |
| `instructions` | Agent instructions included in the structured state sent to TypeSafe. |

Streaming, non-text message content, and generative settings such as `temperature`
are rejected.

`TypeSafeChatClient` is the recommended client and layers function invocation,
middleware, and telemetry over `RawTypeSafeChatClient`. Use the raw client only
when composing a custom layer stack or intentionally opting out of those framework
layers.

## Function calling

TypeSafe converts tool selection and supported arguments into internal `Choice`
and `Noul` questions, emits an Agent Framework function call, and lets the standard
function-invocation loop execute it. After one tool call, tools are disabled and
the connector makes the terminal TypeSafe request using only the caller's
`response_format` questions.

Supported input-schema shapes:

- Empty/zero-argument object schemas.
- Fixed `const` values.
- `enum` or Python `Literal` arguments.
- Boolean arguments.
- Arrays whose items are `enum` or `Literal` values. These are treated as
  set-like selections in schema order; duplicates and caller-defined ordering are
  not supported.
- Optional versions of those shapes. A separate TypeSafe question decides whether
  to omit the argument so the function's default can apply.

Required free-form strings, numbers, nested objects, general arrays, and required
nullable arguments are not supported. In automatic tool mode, unsupported tools
are excluded with a warning. Required unsupported tools fail the request.

Local tools can use inferred schemas or Pydantic input models:

```python
from typing import Literal

from agent_framework import Agent, FunctionTool
from agent_framework_typesafe import TypeSafeChatClient
from pydantic import BaseModel
from typesafe_sdk import Noul


class WeatherArguments(BaseModel):
    city: Literal["Seattle", "Paris"]
    detailed: bool


weather = FunctionTool(
    name="weather",
    description="Get weather for a supported city.",
    func=lambda city, detailed: f"Weather for {city}; detailed={detailed}",
    input_model=WeatherArguments,
)
agent = Agent(client=TypeSafeChatClient(), tools=[weather])
response = await agent.run(
    "Give me detailed Seattle weather.",
    options={"response_format": {"succeeded": Noul(instructions="Did the tool result indicate success?")}},
)
```

MCP tools are supported through `Agent`, which connects to the server and expands
discovered MCP functions into `FunctionTool` objects before TypeSafe routing:

```python
from agent_framework import Agent, MCPStdioTool
from agent_framework_typesafe import TypeSafeChatClient

mcp = MCPStdioTool(name="my-server", command="my-mcp-server")
agent = Agent(client=TypeSafeChatClient(), tools=[mcp])
```

Only discovered MCP functions whose JSON schemas fit the supported subset are
routable. Use `tool_choice.allowed_tools` to narrow large MCP servers; a request
supports at most 32 routable tools and 128 generated internal questions.

## Configuration and lifecycle

The internally created TypeSafe SDK client reads:

- `TYPESAFE_API_KEY` - required API key.
- `TYPESAFE_DEFAULT_MODEL` - optional default model; the SDK defaults to `jev-latest`.
- `TYPESAFE_BASE_URL` - optional API root override.

Constructor values take precedence over an explicitly selected `.env` file and
process environment variables. Credential requirements are evaluated only after
those sources are resolved. When `async_client` is supplied, the injected client
is authoritative and no API key is required by the connector.

For advanced SDK configuration, inject a configured `AsyncTypeSafeClient`:

```python
from agent_framework_typesafe import TypeSafeChatClient
from typesafe_sdk import AsyncTypeSafeClient

sdk_client = AsyncTypeSafeClient(timeout=60)
client = TypeSafeChatClient(async_client=sdk_client)
```

Injected SDK clients remain caller-owned. Use `close()` or `async with` to close
clients created by `TypeSafeChatClient`.

See the [package sample](samples/README.md) for a runnable direct-client and Agent example.
