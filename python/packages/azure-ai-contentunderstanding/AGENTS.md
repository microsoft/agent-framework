# AGENTS.md — azure-ai-contentunderstanding

## Package Overview

`agent-framework-azure-ai-contentunderstanding` integrates Azure Content Understanding (CU)
into the Agent Framework as a context provider. It automatically analyzes file attachments
(documents, images, audio, video) and injects structured results into the LLM context.

## Public API

| Symbol | Type | Description |
|--------|------|-------------|
| `ContentUnderstandingContextProvider` | class | Main context provider — extends `BaseContextProvider` |
| `AnalysisSection` | enum | Output section selector (MARKDOWN, FIELDS, etc.) |
| `ContentLimits` | dataclass | Configurable file size/page/duration limits |

## Architecture

- **`_context_provider.py`** — Main provider implementation. Overrides `before_run()` to detect
  file attachments, call the CU API, manage session state with multi-document tracking,
  and auto-register retrieval tools for follow-up turns.
- **`_models.py`** — `AnalysisSection` enum, `ContentLimits` dataclass, `DocumentEntry` TypedDict.

## Key Patterns

- Follows the Azure AI Search context provider pattern (same lifecycle, config style).
- Uses provider-scoped `state` dict for multi-document tracking across turns.
- Auto-registers `list_documents()` and `get_analyzed_document()` tools via `context.extend_tools()`.
- Configurable timeout (`max_wait`) with `asyncio.create_task()` background fallback.
- Strips supported binary attachments from `input_messages` to prevent LLM API errors.

## Running Tests

```bash
uv run poe test -P azure-ai-contentunderstanding
```
