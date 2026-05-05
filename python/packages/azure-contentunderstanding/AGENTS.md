# AGENTS.md — azure-contentunderstanding

## Package Overview

`agent-framework-azure-contentunderstanding` integrates Azure Content Understanding (CU)
into the Agent Framework as a context provider. It automatically analyzes file attachments
(documents, images, audio, video) and injects structured results into the LLM context.

## Public API

| Symbol | Type | Description |
|--------|------|-------------|
| `ContentUnderstandingContextProvider` | class | Main context provider — extends `ContextProvider` |
| `AnalysisSection` | enum | Output section selector (MARKDOWN, FIELDS, etc.) |
| `DocumentStatus` | enum | Document lifecycle state (ANALYZING, UPLOADING, READY, FAILED) |
| `FileSearchBackend` | ABC | Abstract vector store file operations interface |
| `FileSearchConfig` | dataclass | Configuration for CU + vector store RAG mode |

## Architecture

- **`_context_provider.py`** — Main provider implementation. Overrides `before_run()` to detect
  file attachments, call the CU API, manage session state with multi-document tracking,
  and auto-register retrieval tools for follow-up turns.
  - **Analyzer auto-detection** — When `analyzer_id=None` (default), `_resolve_analyzer_id()`
    selects the CU analyzer based on media type prefix: `audio/` → `prebuilt-audioSearch`,
    `video/` → `prebuilt-videoSearch`, everything else → `prebuilt-documentSearch`.
  - **Multi-segment output** — CU splits long video/audio into multiple scene segments
    (each a separate `contents[]` entry with its own `startTimeMs`, `endTimeMs`, `markdown`,
    and `fields`). `_extract_sections()` produces:
    - `segments`: list of per-segment dicts, each with `markdown`, `fields`, `start_time_s`, `end_time_s`
    - `markdown`: concatenated at top level with `---` separators (for file_search uploads)
    - `duration_seconds`: computed from global `min(startTimeMs)` → `max(endTimeMs)`
    - Metadata (`kind`, `resolution`): taken from the first segment
  - **Speaker diarization (not identification)** — CU transcripts label speakers as
    `<Speaker 1>`, `<Speaker 2>`, etc. CU does **not** identify speakers by name.
  - **file_search RAG** — When `FileSearchConfig` is provided, CU-extracted markdown is
    uploaded to an OpenAI vector store and a `file_search` tool is registered on the context
    instead of injecting the full document content. This enables token-efficient retrieval
    for large documents.
- **`_models.py`** — `AnalysisSection` enum, `DocumentStatus` enum, `DocumentEntry` TypedDict,
  `FileSearchConfig` dataclass.
- **`_file_search.py`** — `FileSearchBackend` ABC, `OpenAIFileSearchBackend`,
  `FoundryFileSearchBackend`.

## Key Patterns

- Follows the Azure AI Search context provider pattern (same lifecycle, config style).
- Uses provider-scoped `state` dict for multi-document tracking across turns.
- Auto-registers `list_documents()` tool via `context.extend_tools()`.
- Configurable timeout (`max_wait`) with `asyncio.create_task()` background fallback.
- Strips supported binary attachments from `input_messages` to prevent LLM API errors.
- Explicit `analyzer_id` always overrides auto-detection (user preference wins).
- Vector store resources are cleaned up in `close()` / `__aexit__`.

## Samples

| Sample | Description |
|--------|-------------|
| `01_document_qa.py` | Upload a PDF via URL, ask questions about it |
| `02_multi_turn_session.py` | AgentSession persistence across turns |
| `03_multimodal_chat.py` | PDF + audio + video parallel analysis |
| `04_invoice_processing.py` | Structured field extraction with `prebuilt-invoice` analyzer |
| `05_large_doc_file_search.py` | CU extraction + OpenAI vector store RAG |
| `02-devui/01-multimodal_agent/` | DevUI web UI for CU-powered chat |
| `02-devui/02-file_search_agent/` | DevUI web UI combining CU + file_search RAG |

## Running Tests

```bash
uv run poe test -P azure-contentunderstanding
```
