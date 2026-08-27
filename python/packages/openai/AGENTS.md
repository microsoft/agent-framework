# AGENTS.md — agent-framework-openai

OpenAI integration package for Agent Framework. Contains OpenAI Responses API and Chat Completions API clients.

## Package Structure

```
agent_framework_openai/
├── __init__.py                 # Public API exports
├── _chat_client.py             # OpenAIChatClient (Responses API) + RawOpenAIChatClient
├── _chat_completion_client.py  # OpenAIChatCompletionClient (Chat Completions API) + RawOpenAIChatCompletionClient
├── _embedding_client.py        # OpenAIEmbeddingClient
├── _exceptions.py              # OpenAI-specific exceptions
└── _shared.py                  # OpenAISettings and shared config helpers
```

## Key Classes

| Class | API | Status |
|---|---|---|
| `OpenAIChatClient` | Responses API | Primary |
| `OpenAIChatCompletionClient` | Chat Completions API | Primary |
| `OpenAIEmbeddingClient` | Embeddings API | Primary |

All clients follow the Raw + Full-Featured pattern (e.g., `RawOpenAIChatClient` + `OpenAIChatClient`).

For Responses API continuation with service-side storage, a prior hosted
`function_approval_request` is server-issued and must not be replayed inline, while the new hosted
`function_approval_response` is serialized as `mcp_approval_response` so the user's approved or rejected decision
reaches the service. Local `FunctionTool` approval controls are resolved in-process and must not be serialized as MCP
items. An approval is hosted when its function call carries a `server_label` in
`function_call.additional_properties`; approvals without that metadata are local. Applications that manually replay
message history must not send that same hosted approval response again on later turns.

The generic OpenAI clients support both OpenAI and Azure OpenAI routing. Precedence is:
explicit Azure inputs (`credential`, `azure_endpoint`, `api_version`) → OpenAI API key
(`OPENAI_API_KEY`) → Azure environment fallback (`AZURE_OPENAI_*`).

## Adapting the Chat Completions client to OpenAI-compatible endpoints

`OpenAIChatCompletionClient` targets the OpenAI Chat Completions wire format and is intentionally
kept free of provider-specific quirks. Many "OpenAI-compatible" providers (OpenRouter, vLLM,
Mistral, DeepSeek, Ollama, …) diverge on the edges — e.g. returning reasoning under
`reasoning` / `reasoning_content` / `reasoning_details`, or `content` as a list of chunks. Rather
than branching in core, the client exposes two optional callables so callers adapt it themselves:

- `response_parser: OpenAIChatResponseContentsParser` — `(message_or_delta, default_contents) -> contents`.
  Post-processes the `Content` items parsed from each response choice. Receives the already-selected
  `ChatCompletionMessage` (non-streaming) or `ChoiceDelta` (streaming) — the client resolves the
  dispatch — so a parser reads provider fields directly (e.g. `getattr(msg, "reasoning", None)`) without
  branching. Use it to surface non-standard fields for display. Applied per choice in both paths.
- `message_preparer: OpenAIChatMessagePreparer` — `(message, default_dicts) -> dicts`. Post-processes
  the outgoing request message dicts built from each framework `Message` (called once per `Message`, for
  every role including `system`/`developer`). Use it to echo provider-specific fields (e.g. vLLM
  `reasoning`) back on later turns for multi-turn continuity. To correlate a surfaced-reasoning `Content`
  with the dict the default serializer emitted for it, tag the `Content` via `additional_properties` in
  the parser and match against `message.contents` rather than raw request-string matching.

Both default to `None` (no-op → byte-identical stock OpenAI behavior) and are constructor args on
`RawOpenAIChatCompletionClient` / `OpenAIChatCompletionClient`. Provider round-trips generally need
**both**: the parser surfaces the field for display, the preparer sends it back. Prefer a dedicated
client (e.g. `agent-framework-mistral`) when an endpoint diverges substantially.

## Dependencies

- `agent-framework-core` — core abstractions
- `openai` — OpenAI Python SDK
