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
| `FileSearchConfig` | dataclass | Configuration for CU + OpenAI vector store RAG mode |

## Architecture

- **`_context_provider.py`** — Main provider implementation. Overrides `before_run()` to detect
  file attachments, call the CU API, manage session state with multi-document tracking,
  and auto-register retrieval tools for follow-up turns.
  - **Lazy initialization** — `_ensure_initialized()` creates the CU client on first `before_run()`
    call, so the provider works with frameworks (e.g. DevUI) that don't call `__aenter__`.
  - **Analyzer auto-detection** — When `analyzer_id=None` (default), `_resolve_analyzer_id()`
    selects the CU analyzer based on media type prefix: `audio/` → `prebuilt-audioSearch`,
    `video/` → `prebuilt-videoSearch`, everything else → `prebuilt-documentSearch`.
  - **Multi-segment merging** — CU splits long video/audio into multiple scene segments
    (each a separate `contents[]` entry with its own `startTimeMs`, `endTimeMs`, `markdown`,
    and `fields`). `_extract_sections()` merges all segments:
    - Duration: global `min(startTimeMs)` → `max(endTimeMs)`
    - Markdown: concatenated with `---` separators
    - Fields: same-named fields across segments are collected into a list with per-segment
      `segment` index; single-occurrence fields remain as a plain dict (backward-compatible)
    - Metadata (kind, resolution): taken from the first segment
  - **Speaker diarization (not identification)** — CU transcripts label speakers as
    `<Speaker 1>`, `<Speaker 2>`, etc. CU does **not** identify speakers by name.
  - **file_search RAG** — When `FileSearchConfig` is provided, CU-extracted markdown is
    uploaded to an OpenAI vector store and a `file_search` tool is registered on the context
    instead of injecting the full document content. This enables token-efficient retrieval
    for large documents. Supports both auto-created ephemeral vector stores (default) and
    user-provided pre-existing stores via `FileSearchConfig.vector_store_id`. Auto-created
    stores are deleted on `close()`; user-provided stores are left intact (caller owns lifecycle).
- **`_models.py`** — `AnalysisSection` enum, `ContentLimits` dataclass, `DocumentEntry` TypedDict,
  `FileSearchConfig` dataclass.

## Key Patterns

- Follows the Azure AI Search context provider pattern (same lifecycle, config style).
- Uses provider-scoped `state` dict for multi-document tracking across turns.
- Auto-registers `list_documents()` and `get_analyzed_document()` tools via `context.extend_tools()`.
- Configurable timeout (`max_wait`) with `asyncio.create_task()` background fallback.
- Strips supported binary attachments from `input_messages` to prevent LLM API errors.
- Explicit `analyzer_id` always overrides auto-detection (user preference wins).
- Vector store resources are cleaned up in `close()` / `__aexit__` (only auto-created stores are deleted; user-provided stores are preserved).

## Samples

| Sample | Description |
|--------|-------------|
| `devui_multimodal_agent/` | DevUI web UI for CU-powered chat with auto-detect analyzer |
| `devui_file_search_agent/` | DevUI web UI combining CU + file_search RAG |
| `document_qa.py` | Upload a PDF, ask questions, follow-up with cached results |
| `multimodal_chat.py` | Multi-file session with background processing |
| `large_doc_file_search.py` | CU extraction + OpenAI vector store RAG |
| `invoice_processing.py` | Structured field extraction with `prebuilt-invoice` analyzer |

## Running Tests

```bash
uv run poe test -P azure-ai-contentunderstanding
```
