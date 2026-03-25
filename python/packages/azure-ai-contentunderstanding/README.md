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
from agent_framework import Agent, Message, Content
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework_azure_ai_contentunderstanding import ContentUnderstandingContextProvider
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()

cu = ContentUnderstandingContextProvider(
    endpoint="https://my-resource.cognitiveservices.azure.com/",
    credential=credential,
)

async with cu, AzureOpenAIResponsesClient(credential=credential) as llm_client:
    agent = Agent(client=llm_client, context_providers=[cu])

    response = await agent.run(Message(role="user", contents=[
        Content.from_text("What's on this invoice?"),
        Content.from_data(pdf_bytes, "application/pdf",
                          additional_properties={"filename": "invoice.pdf"}),
    ]))
    print(response.text)
```

## Features

- **Automatic file detection** — Scans input messages for supported file attachments and analyzes them automatically.
- **Multi-document sessions** — Tracks multiple analyzed documents per session with status tracking (`pending`/`ready`/`failed`).
- **Background processing** — Configurable timeout with async background fallback for large files or slow analysis.
- **Output filtering** — Passes only relevant sections (markdown, fields) to the LLM, reducing token usage by >90%.
- **Auto-registered tools** — `list_documents()` and `get_analyzed_document()` tools let the LLM query status and retrieve cached content on follow-up turns.
- **All CU modalities** — Documents, images, audio, and video via prebuilt or custom analyzers.
- **Multi-segment video/audio merging** — CU splits long video/audio into multiple scene segments. The provider automatically merges all segments: markdown is concatenated, fields are collected per-segment, and duration spans the full range. Speaker names are not identified by CU (only `<Speaker N>` diarization labels).

## Supported File Types

| Category | Types |
|----------|-------|
| Documents | PDF, DOCX, XLSX, PPTX, HTML, TXT, Markdown |
| Images | JPEG, PNG, TIFF, BMP |
| Audio | WAV, MP3, M4A, FLAC, OGG |
| Video | MP4, MOV, AVI, WebM |

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
AZURE_AI_PROJECT_ENDPOINT=https://your-project.api.azureml.ms
AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4.1
AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.cognitiveservices.azure.com/
```

You also need to be logged in with `az login` (for `AzureCliCredential`).

### Running Samples

```bash
# From the python/ directory:
uv run packages/azure-ai-contentunderstanding/samples/document_qa.py
uv run packages/azure-ai-contentunderstanding/samples/invoice_processing.py
uv run packages/azure-ai-contentunderstanding/samples/multimodal_chat.py
```

| Sample | Description |
|--------|-------------|
| [document_qa.py](samples/document_qa.py) | Upload a PDF, ask questions, follow-up with cached results |
| [multimodal_chat.py](samples/multimodal_chat.py) | Multi-file session with status tracking |
| [devui_multimodal_agent/](samples/devui_multimodal_agent/) | Web UI for file upload + CU-powered chat |
| [devui_file_search_agent/](samples/devui_file_search_agent/) | Web UI combining CU + file_search RAG for large documents |
| [large_doc_file_search.py](samples/large_doc_file_search.py) | CU extraction + OpenAI vector store RAG |
| [invoice_processing.py](samples/invoice_processing.py) | Structured field extraction with `prebuilt-invoice` analyzer |

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
- **Fields**: when the same field (e.g. `Summary`) appears in multiple segments,
  values are collected into a list with per-segment indices
- **Metadata** (kind, resolution): taken from the first segment

### Speaker Identification Limitation

CU performs **speaker diarization** (distinguishing different speakers as `<Speaker 1>`,
`<Speaker 2>`, etc.) but does **not** perform **speaker identification** (mapping speakers
to real names). If your application needs named speakers, provide the mapping in the
agent's instructions or integrate a separate speaker recognition service.

## Links

- [Microsoft Agent Framework](https://aka.ms/agent-framework)
- [Azure Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/)
