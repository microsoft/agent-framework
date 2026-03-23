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

| # | Sample | Description | Run |
|---|--------|-------------|-----|
| S1 | [Document Q&A](document_qa.py) | Upload a PDF, ask questions, follow-up with cached results | `uv run samples/document_qa.py` |
| S2 | [Multi-Modal Chat](multimodal_chat.py) | Multi-file session with status tracking | `uv run samples/multimodal_chat.py` |
| S3 | [DevUI Multi-Modal](devui_multimodal_agent/) | Web UI for file upload + CU-powered chat | `uv run poe devui --agent samples/devui_multimodal_agent` |
| S4 | [Large Doc + file_search](large_doc_file_search.py) | CU extraction + OpenAI vector store RAG | `uv run samples/large_doc_file_search.py` |
| S5 | [Invoice Processing](invoice_processing.py) | Structured field extraction with prebuilt-invoice | `uv run samples/invoice_processing.py` |

## Install (preview)

```bash
pip install --pre agent-framework-azure-ai-contentunderstanding
```
