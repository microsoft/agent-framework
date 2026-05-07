# DevUI Foundry File Search Agent

Interactive web UI for uploading and chatting with documents, images, audio, and video using Azure Content Understanding + Foundry file_search RAG.

This is the **Foundry** variant. For the Azure OpenAI Responses API variant, see `devui_azure_openai_file_search_agent`.

## How It Works

1. **Upload** any supported file (PDF, image, audio, video) via the DevUI chat
2. **CU analyzes** the file — auto-selects the right analyzer per media type
3. **Markdown extracted** by CU is uploaded to a Foundry vector store
4. **file_search** tool is registered — LLM retrieves top-k relevant chunks
5. **Ask questions** across all uploaded documents with token-efficient RAG

## Setup

1. Set environment variables (or create a `.env` file in `python/`):
   ```bash
   FOUNDRY_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/
   FOUNDRY_MODEL=gpt-4.1
   AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.services.ai.azure.com/
   ```

2. Log in with Azure CLI:
   ```bash
   az login
   ```

3. Run with DevUI:
   ```bash
   devui packages/azure-contentunderstanding/samples/devui_foundry_file_search_agent
   ```

4. Open the DevUI URL in your browser and start uploading files.
