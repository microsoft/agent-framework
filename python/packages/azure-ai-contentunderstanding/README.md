# Azure Content Understanding for Microsoft Agent Framework

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Azure Content Understanding (CU) integration for the [Microsoft Agent Framework](https://aka.ms/agent-framework). Provides a context provider that automatically analyzes file attachments (documents, images, audio, video) using Azure Content Understanding and injects structured results into the LLM context.

## Installation

```bash
pip install --pre agent-framework-azure-ai-contentunderstanding
```

> **Note:** This package is in preview. The `--pre` flag is required to install pre-release versions.

## Quick Start

```python
from agent_framework import Agent, AgentSession, Message, Content
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_ai_contentunderstanding import ContentUnderstandingContextProvider
from azure.identity import AzureCliCredential

credential = AzureCliCredential()

cu = ContentUnderstandingContextProvider(
    endpoint="https://my-resource.cognitiveservices.azure.com/",
    credential=credential,
    max_wait=None,  # wait until analysis finishes
)

client = FoundryChatClient(
    project_endpoint="https://your-project.services.ai.azure.com",
    model="gpt-4.1",
    credential=credential,
)

async with cu:
    agent = Agent(
        client=client,
        name="DocumentQA",
        instructions="You are a helpful document analyst.",
        context_providers=[cu],
    )
    session = AgentSession()

    response = await agent.run(
        Message(role="user", contents=[
            Content.from_text("What's on this invoice?"),
            Content.from_data(pdf_bytes, "application/pdf",
                              additional_properties={"filename": "invoice.pdf"}),
        ]),
        session=session,
    )
    print(response.text)
```

## Features

- **Automatic file detection** — Scans input messages for supported file attachments and analyzes them automatically.
- **Multi-document sessions** — Tracks multiple analyzed documents per session with status tracking (`analyzing`/`uploading`/`ready`/`failed`).
- **Background processing** — Configurable timeout with async background fallback for large files or slow analysis.
- **Output filtering** — Passes only relevant sections (markdown, fields) to the LLM, reducing token usage by >90%.
- **Auto-registered tools** — `list_documents()` tool lets the LLM query document status. Full document content is injected into conversation history for follow-up turns.
- **All CU modalities** — Documents, images, audio, and video via prebuilt or custom analyzers.
- **Multi-segment video/audio** — CU splits long video/audio into multiple scene segments. The provider merges markdown across segments and organizes fields per-segment with time ranges. Duration spans the full range. Speaker diarization uses `<Speaker N>` labels (no speaker identification).

## Supported File Types

| Category | Types |
|----------|-------|
| Documents | PDF, DOCX, XLSX, PPTX, HTML, TXT, Markdown |
| Images | JPEG, PNG, TIFF, BMP |
| Audio | WAV, MP3, M4A, FLAC, OGG |
| Video | MP4, MOV, AVI, WebM |

## File Naming

Always provide a `filename` via `additional_properties` when uploading files. The filename serves as the **unique document key** for the session — it determines how documents are tracked, retrieved, and referenced by the LLM.

```python
# Recommended: always provide a filename
Content.from_data(pdf_bytes, "application/pdf",
                  additional_properties={"filename": "invoice.pdf"})

# For URLs: filename from additional_properties takes priority over the URL path
Content.from_uri("https://example.com/files/12345",
                 media_type="application/pdf",
                 additional_properties={"filename": "quarterly_report.pdf"})
```

**Why this matters:**

- Without a filename, binary uploads get a hash-based key (e.g. `doc_a59574c3`) that is hard for users and the LLM to reference.
- For URLs without a file extension (e.g. `https://api.example.com/files/12345`), the provider cannot detect the media type automatically — the file may be silently skipped.
- **Duplicate filenames are rejected** within a session to prevent data integrity issues with vector store entries. Use unique filenames for each document.

## Configuration

```python
from agent_framework_azure_ai_contentunderstanding import (
    ContentUnderstandingContextProvider,
    AnalysisSection,
)

cu = ContentUnderstandingContextProvider(
    endpoint="https://my-resource.cognitiveservices.azure.com/",
    credential=credential,
    analyzer_id="my-custom-analyzer",     # default: auto-detect by media type
    max_wait=10.0,                        # default: 5.0 seconds
    output_sections=[                     # default: MARKDOWN + FIELDS
        AnalysisSection.MARKDOWN,
        AnalysisSection.FIELDS,
        AnalysisSection.FIELD_GROUNDING,
    ],
)
```

## Samples

The `samples/` directory contains runnable examples. Each sample uses [PEP 723](https://peps.python.org/pep-0723/) inline metadata so it can be run directly with `uv run`.

### Required Environment Variables

Set these in your shell or in a `.env` file in the `python/` directory:

```bash
AZURE_AI_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.cognitiveservices.azure.com/
```

You also need to be logged in with `az login` (for `AzureCliCredential`).

### Running Samples

```bash
# From the python/ directory:
uv run packages/azure-ai-contentunderstanding/samples/01-get-started/01_document_qa.py
uv run packages/azure-ai-contentunderstanding/samples/01-get-started/02_multi_turn_session.py
uv run packages/azure-ai-contentunderstanding/samples/01-get-started/03_multimodal_chat.py
```

See [`samples/README.md`](samples/README.md) for the full list of samples.

## Multi-Segment Video/Audio Processing

Azure Content Understanding splits long video and audio files into multiple scene/segment
`contents` entries. For example, a 60-second video may be returned as 3 segments:

| Segment | `startTimeMs` | `endTimeMs` | Content |
|---------|--------------|-------------|---------|
| `contents[0]` | 1000 | 14000 | Scene 1 transcript + summary |
| `contents[1]` | 15000 | 31000 | Scene 2 transcript + summary |
| `contents[2]` | 32000 | 49000 | Scene 3 transcript + summary |

The context provider merges these automatically:
- **Duration**: computed from global `min(startTimeMs)` to `max(endTimeMs)`
- **Markdown**: concatenated across all segments (separated by `---`)
- **Fields**: organized per-segment with time ranges, so each segment's
  extracted fields (e.g. `Summary`) are grouped with its own content
- **Metadata** (kind, resolution): taken from the first segment

### Speaker Identification Limitation

CU performs **speaker diarization** (distinguishing different speakers as `<Speaker 1>`,
`<Speaker 2>`, etc.) but does **not** perform **speaker identification** (mapping speakers
to real names). If your application needs named speakers, provide the mapping in the
agent's instructions or integrate a separate speaker recognition service.

## Links

- [Microsoft Agent Framework](https://aka.ms/agent-framework)
- [Azure Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/)
