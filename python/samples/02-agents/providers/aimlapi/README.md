# aimlapi.com Examples

This folder contains examples demonstrating how to use models served by
[aimlapi.com](https://aimlapi.com) with the Agent Framework.

## Approach

aimlapi.com is an aggregator that exposes a plain OpenAI Chat Completions endpoint at
`https://api.aimlapi.com/v1`, so it needs no provider-specific client. The samples use
`OpenAIChatCompletionClient` with a base URL override — the route documented in
[`python/packages/openai/AGENTS.md`](../../../../packages/openai/AGENTS.md) for
OpenAI-compatible endpoints that do not diverge from the wire format.

Only `/v1/chat/completions` and `/v1/responses` exist on this endpoint; there is no
`/v1/completions`.

## Prerequisites

1. **Get an API key**: create one at [aimlapi.com/app/keys](https://aimlapi.com/app/keys).
2. **Pick a model**: model ids are namespaced, e.g. `openai/gpt-4o-mini`,
   `anthropic/claude-sonnet-4.6`, `google/gemini-2.5-flash`. The catalog is public and
   needs no key:

   ```bash
   curl 'https://api.aimlapi.com/v1/models?include=all'
   ```

   The response is `{"object": "list", "data": [...]}`; chat models carry
   `"type": "openai/chat-completions"`. A model id may appear either as an `id` or in
   another entry's `aliases`, so check both. `?include=all` adds `capabilities`,
   `modalities`, `pricing` and `providers`, none of which appear in the default response.

> **Note**: `capabilities` is advisory, not authoritative in either direction — some
> models that do not advertise `tools` or `vision` support them, and a few that advertise
> them do not. Verify a model against your own workload before relying on a flag.

## Examples

| File | Description |
|------|-------------|
| [`aimlapi_chat_completion_client_basic.py`](aimlapi_chat_completion_client_basic.py) | Basic agent using `OpenAIChatCompletionClient` against aimlapi.com. Shows both streaming and non-streaming responses. |
| [`aimlapi_chat_completion_client_with_function_tools.py`](aimlapi_chat_completion_client_with_function_tools.py) | Function tool calling across two turns of one session. |

## Environment Variables

- `AIMLAPI_API_KEY`: Your aimlapi.com API key (required)
  - Example: `export AIMLAPI_API_KEY="..."`
- `AIMLAPI_MODEL`: The model id to use (optional, defaults to `openai/gpt-4o-mini`)
  - Example: `export AIMLAPI_MODEL="anthropic/claude-sonnet-4.6"`

The base URL is not configurable from the environment in these samples: it is a module
constant so the attribution headers described below can only ever reach aimlapi.com.

## Attribution headers

Both samples pass four headers via the client's `default_headers` argument:

| Header | Value | Purpose |
|---|---|---|
| `HTTP-Referer` | `https://github.com/microsoft/agent-framework` | Identifies the calling project (OpenRouter convention) |
| `X-Title` | `Microsoft Agent Framework` | Identifies the calling project |
| `X-AIMLAPI-Partner-ID` | `part_agentframework` | Integration attribution |
| `X-AIMLAPI-Source` | `agent/agent-framework` | Channel attribution |

`default_headers` is a first-class constructor argument on `OpenAIChatCompletionClient`,
so this needs no framework changes. The headers are scoped to the client instance, which
is pinned to `https://api.aimlapi.com/v1`, and each client gets a fresh copy of the
dictionary rather than the module constant itself.

## Notes on usage reporting

- On some models `completion_tokens` excludes reasoning tokens, so metering spend from
  `completion_tokens` alone under-reports. Read `usage.total_tokens` where available.
- `max_tokens` does not reliably bound reasoning tokens on every model; a few return well
  past the cap with `finish_reason: "stop"`. Do not treat it as a cost ceiling.
- 79 models publish tiered `pricing.thresholds[]` above a context boundary, which a single
  flat `$/M` figure cannot express.
