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

| Sample | Description | Run |
|--------|-------------|-----|
| [Document Q&A](document_qa.py) | Upload a PDF, ask questions, follow-up with cached results | `uv run samples/document_qa.py` |
| [Multi-Modal Chat](multimodal_chat.py) | Multi-file session with PDF + status tracking | `uv run samples/multimodal_chat.py` |
| [Invoice Processing](invoice_processing.py) | Structured field extraction with prebuilt-invoice | `uv run samples/invoice_processing.py` |

## Install (preview)

```bash
pip install --pre agent-framework-azure-ai-contentunderstanding
```
