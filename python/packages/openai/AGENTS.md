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

## Dependencies

- `agent-framework-core` — core abstractions
- `openai` — OpenAI Python SDK
