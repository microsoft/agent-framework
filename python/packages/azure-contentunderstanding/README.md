# Get Started with Azure Content Understanding in Microsoft Agent Framework

Please install this package via pip:

```bash
pip install agent-framework-azure-contentunderstanding --pre
```

## Azure Content Understanding Integration

### Prerequisites

Before using this package, you need an Azure Content Understanding resource:

1. An active **Azure subscription** ([create one for free](https://azure.microsoft.com/pricing/purchase-options/azure-account))
2. A **Microsoft Foundry resource** created in a [supported region](https://learn.microsoft.com/azure/ai-services/content-understanding/language-region-support)
3. **Default model deployments** configured for your resource (GPT-4.1, GPT-4.1-mini, text-embedding-3-large)

Follow the [prerequisites section](https://learn.microsoft.com/azure/ai-services/content-understanding/quickstart/use-rest-api?tabs=portal%2Cdocument&pivots=programming-language-rest#prerequisites) in the Azure Content Understanding quickstart for setup instructions.

### Introduction

The Azure Content Understanding integration provides a context provider that automatically analyzes file attachments (documents, images, audio, video) using [Azure Content Understanding](https://learn.microsoft.com/azure/ai-services/content-understanding/) and injects structured results into the LLM context.

- **Document & image analysis**: State-of-the-art OCR with markdown extraction, table preservation, and structured field extraction — handles scanned PDFs, handwritten content, and complex layouts
- **Audio & video analysis**: Transcription, speaker diarization, and per-segment summaries
- **Background processing**: Configurable timeout with async background fallback for large files
- **file_search integration**: Optional vector store upload for token-efficient RAG on large documents

> Learn more about Azure Content Understanding capabilities at [https://learn.microsoft.com/azure/ai-services/content-understanding/](https://learn.microsoft.com/azure/ai-services/content-understanding/)

### Basic Usage Example

See the [samples directory](samples/) which demonstrates:

- Single PDF upload and Q&A ([01_document_qa](samples/01-get-started/01_document_qa.py))
- Multi-turn sessions with cached results ([02_multi_turn_session](samples/01-get-started/02_multi_turn_session.py))
- PDF + audio + video parallel analysis ([03_multimodal_chat](samples/01-get-started/03_multimodal_chat.py))
- Structured field extraction with prebuilt-invoice ([04_invoice_processing](samples/01-get-started/04_invoice_processing.py))
- CU extraction + OpenAI vector store RAG ([05_large_doc_file_search](samples/01-get-started/05_large_doc_file_search.py))
- Interactive web UI with DevUI ([02-devui](samples/02-devui/))

```python
import asyncio
from agent_framework import Agent, AgentSession, Message, Content
from agent_framework.foundry import FoundryChatClient
from agent_framework.foundry import ContentUnderstandingContextProvider
from azure.identity import AzureCliCredential

credential = AzureCliCredential()

cu = ContentUnderstandingContextProvider(
    endpoint="https://my-resource.cognitiveservices.azure.com/",
    credential=credential,
    max_wait=None,  # block until CU extraction completes before sending to LLM
)

client = FoundryChatClient(
    project_endpoint="https://your-project.services.ai.azure.com",
    model="gpt-4.1",
    credential=credential,
)

async def main():
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
                Content.from_uri(
                    "https://raw.githubusercontent.com/Azure-Samples/"
                    "azure-ai-content-understanding-assets/main/document/invoice.pdf",
                    media_type="application/pdf",
                    additional_properties={"filename": "invoice.pdf"},
                ),
            ]),
            session=session,
        )
        print(response.text)

asyncio.run(main())
```

### Supported File Types

| Category | Types |
|----------|-------|
| Documents | PDF, DOCX, XLSX, PPTX, HTML, TXT, Markdown |
| Images | JPEG, PNG, TIFF, BMP |
| Audio | WAV, MP3, M4A, FLAC, OGG |
| Video | MP4, MOV, AVI, WebM |

For the complete list of supported file types and size limits, see [Azure Content Understanding service limits](https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits#input-file-limits).

### Environment Variables

The provider supports automatic endpoint resolution from environment variables.
When ``endpoint`` is not passed to the constructor, it is loaded from
``AZURE_CONTENTUNDERSTANDING_ENDPOINT``:

```python
# Endpoint auto-loaded from AZURE_CONTENTUNDERSTANDING_ENDPOINT env var
cu = ContentUnderstandingContextProvider(credential=credential)
```

Set these in your shell or in a `.env` file:

```bash
AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.cognitiveservices.azure.com/
AZURE_AI_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
```

You also need to be logged in with `az login` (for `AzureCliCredential`).

### Next steps

- Explore the [samples directory](samples/) for complete code examples
- Read the [Azure Content Understanding documentation](https://learn.microsoft.com/azure/ai-services/content-understanding/) for detailed service information
- Learn more about the [Microsoft Agent Framework](https://aka.ms/agent-framework)
