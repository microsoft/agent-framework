# DevUI File-Search Agent (Azure OpenAI backend)

Interactive web UI for uploading and chatting with documents, images, audio, and video using Azure Content Understanding + Azure OpenAI `file_search` RAG.

This is the **Azure OpenAI Responses** variant. For the Foundry variant, see [the Foundry backend](../FoundryBackend/).

## How It Works

1. **Upload** any supported file (PDF, image, audio, video) via the DevUI chat
2. **CU analyzes** the file — auto-selects the right analyzer per media type
3. **Markdown extracted** by CU is uploaded to an Azure OpenAI vector store
4. **file_search** tool is registered — LLM retrieves top-k relevant chunks
5. **Ask questions** across all uploaded documents with token-efficient RAG

## Setup

1. Set environment variables:

   ```sh
   AZURE_OPENAI_ENDPOINT=https://your-aoai-resource.openai.azure.com/
   AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1
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

4. Open <https://localhost:50522/devui> in a browser and start uploading files.

## Supported File Types

| Type | Formats | CU Analyzer (auto-detected) |
|------|---------|-----------------------------|
| Documents | PDF, DOCX, XLSX, PPTX, HTML, TXT, Markdown | `prebuilt-documentSearch` |
| Images | JPEG, PNG, TIFF, BMP | `prebuilt-documentSearch` |
| Audio | WAV, MP3, FLAC, OGG, M4A | `prebuilt-audioSearch` |
| Video | MP4, MOV, AVI, WebM | `prebuilt-videoSearch` |

## vs. the Multi-Modal Agent

| Feature | Multi-Modal Agent | File-Search |
|---------|---------|-------------------|
| CU extraction | Full content injected | Content indexed in vector store |
| RAG | No | `file_search` retrieves top-k chunks |
| Large docs (100+ pages) | May exceed context window | Token-efficient |
| Multiple large files | Context overflow risk | All indexed, searchable |
| Best for | Small docs, quick inspection | Large docs, multi-file Q&A |

## Cleanup

The vector store is created with a 1-day idle expiration policy, so abandoned DevUI sessions are auto-cleaned by Azure OpenAI. The CU provider's `DisposeAsync` (triggered at app shutdown) deletes the per-file uploads it owned; the vector store itself is left to the auto-expiration policy.
