# Azure Content Understanding Samples

These samples demonstrate how to use the `agent-framework-azure-contentunderstanding` package to add document, image, audio, and video understanding to your agents.

## Prerequisites

1. Azure CLI logged in: `az login`
2. Environment variables set (or `.env` file in the `python/` directory):
   ```
   FOUNDRY_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com
   FOUNDRY_MODEL=gpt-4.1
   AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.cognitiveservices.azure.com/
   ```

## Samples

### Script samples (easy → advanced)

| # | Sample | Description | Run |
|---|--------|-------------|-----|
| 01 | [Document Q&A](01_document_qa.py) | Upload a PDF, ask questions with CU-powered extraction | `uv run samples/02-agents/context_providers/azure_content_understanding/01_document_qa.py` |
| 02 | [Multi-Turn Session](02_multi_turn_session.py) | AgentSession persistence across turns | `uv run samples/02-agents/context_providers/azure_content_understanding/02_multi_turn_session.py` |
| 03 | [Multi-Modal Chat](03_multimodal_chat.py) | PDF + audio + video parallel analysis | `uv run samples/02-agents/context_providers/azure_content_understanding/03_multimodal_chat.py` |
| 04 | [Invoice Processing](04_invoice_processing.py) | Structured field extraction with prebuilt-invoice | `uv run samples/02-agents/context_providers/azure_content_understanding/04_invoice_processing.py` |
| 05 | [Large Doc + file_search](05_large_doc_file_search.py) | CU extraction + OpenAI vector store RAG | `uv run samples/02-agents/context_providers/azure_content_understanding/05_large_doc_file_search.py` |

### Interactive web UI samples

See the [DevUI sample index](../../devui/README.md) for the Azure Content Understanding agents.

## Install (preview)

```bash
pip install --pre agent-framework-azure-contentunderstanding
```
