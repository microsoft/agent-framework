# TypeSafe AI Jev

This sample implements a small Agent Framework `BaseChatClient` adapter for
[TypeSafe AI Jev](https://docs.typesafe.ai/). Jev is a System One decision model:
it evaluates state against explicit typed questions and returns probabilities and
scores. It does not generate ordinary chat text.

## Sample

| File | Description |
| --- | --- |
| [`jev_structured_output.py`](jev_structured_output.py) | Uses Jev directly through `JevChatClient` and through an Agent Framework `Agent`. |

The adapter deliberately requires both of these options on every request:

- `questions`: a non-empty mapping of TypeSafe `Noul`, `Choice`, or `Score` questions.
- `response_format`: `typesafe_sdk.SystemOneResponse` or a subclass.

Streaming, tools, non-text message content, and free-form generation options such
as temperature are rejected because Jev does not support those chat capabilities.

## Setup

Create a TypeSafe API key in the [TypeSafe console](https://console.typesafe.ai/keys)
and add it to `python/.env`:

```dotenv
TYPESAFE_API_KEY=your-key
```

## Run

From the `python/` directory:

```bash
uv run --env-file .env samples/02-agents/providers/typesafe/jev_structured_output.py
```

The PEP 723 metadata in the sample installs the required `agent-framework-core`,
`python-dotenv`, and `typesafe-sdk` packages.

## Expected output

The exact probabilities and scores vary, but the direct client and Agent examples
both print a department choice, its confidence, a frustration score, and an urgency
probability. Agent Framework may also warn that the client does not support function
invocation; this is expected because Jev does not expose tool calling.
