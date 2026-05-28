# Step 08 — DevUI File-Search Agent (Foundry backend)

Interactive web UI for uploading and chatting with documents, images, audio, and video using Azure Content Understanding + Foundry `file_search` RAG.

This is the **Foundry** variant. For the Azure OpenAI Responses API variant, see [Step 07](../AgentWithContentUnderstanding_Step07_DevUI_FileSearchAzureOpenAI/).

## How It Works

1. **Upload** any supported file (PDF, image, audio, video) via the DevUI chat
2. **CU analyzes** the file — auto-selects the right analyzer per media type
3. **Markdown extracted** by CU is uploaded to a Foundry vector store
4. **file_search** tool is registered — LLM retrieves top-k relevant chunks
5. **Ask questions** across all uploaded documents with token-efficient RAG

## Setup

1. Set environment variables:

   ```sh
   AZURE_AI_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/
   AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
   AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.services.ai.azure.com/
   ```

2. Log in with Azure CLI (the sample uses `DefaultAzureCredential`):

   ```sh
   az login
   ```

3. Run the sample:

   ```sh
   dotnet run
   ```

4. Open <https://localhost:50524/devui> in a browser and start uploading files.

## Cleanup

A Foundry vector store is created at startup and deleted on `Ctrl+C` (via `IHostApplicationLifetime.ApplicationStopping`). The CU provider's `DisposeAsync` (triggered at app shutdown) deletes the per-file uploads it owned.
