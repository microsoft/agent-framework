# Azure Content Understanding Samples

These samples demonstrate how to use the `agent-framework-azure-ai-contentunderstanding` package to add document, image, audio, and video understanding to your agents.

## Prerequisites

1. Azure CLI logged in: `az login`
2. Environment variables set (or `.env` file in the `python/` directory):
   ```
   AZURE_AI_PROJECT_ENDPOINT=https://your-project.api.azureml.ms
   AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4.1
   AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.cognitiveservices.azure.com/
   ```

## Samples

### 01-get-started — Script samples (easy → advanced)

| # | Sample | Description | Run |
|---|--------|-------------|-----|
| 01 | [Document Q&A](01-get-started/01_document_qa.py) | Upload a PDF, ask questions, follow-up with cached results | `uv run samples/01-get-started/01_document_qa.py` |
| 02 | [Multi-Modal Chat](01-get-started/02_multimodal_chat.py) | Multi-file session with status tracking | `uv run samples/01-get-started/02_multimodal_chat.py` |
| 03 | [Invoice Processing](01-get-started/03_invoice_processing.py) | Structured field extraction with prebuilt-invoice | `uv run samples/01-get-started/03_invoice_processing.py` |
| 04 | [Large Doc + file_search](01-get-started/04_large_doc_file_search.py) | CU extraction + OpenAI vector store RAG | `uv run samples/01-get-started/04_large_doc_file_search.py` |

### 02-devui — Interactive web UI samples

| # | Sample | Description | Run |
|---|--------|-------------|-----|
| 01 | [Multi-Modal Agent](02-devui/01-multimodal_agent/) | Web UI for file upload + CU-powered chat | `devui samples/02-devui/01-multimodal_agent` |
| 02a | [file_search (Azure OpenAI backend)](02-devui/02-file_search_agent/azure_openai_backend/) | DevUI with CU + Azure OpenAI vector store | `devui samples/02-devui/02-file_search_agent/azure_openai_backend` |
| 02b | [file_search (Foundry backend)](02-devui/02-file_search_agent/foundry_backend/) | DevUI with CU + Foundry vector store | `devui samples/02-devui/02-file_search_agent/foundry_backend` |

## Install (preview)

```bash
pip install --pre agent-framework-azure-ai-contentunderstanding
```
