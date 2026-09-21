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

Streaming, tools, non-text message content, and generative settings such as
`temperature` are rejected. Agent Framework may warn that this chat client does
not support function invocation; that is expected because TypeSafe System One
models do not expose tool calling.

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
