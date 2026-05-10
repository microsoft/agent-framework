# DevUI File Search Agent

Interactive web UI for uploading and chatting with documents, images, audio, and video using Azure Content Understanding + OpenAI file_search RAG.

## How It Works

1. **Upload** any supported file (PDF, image, audio, video) via the DevUI chat
2. **CU analyzes** the file — auto-selects the right analyzer per media type
3. **Markdown extracted** by CU is uploaded to an OpenAI vector store
4. **file_search** tool is registered — LLM retrieves top-k relevant chunks
5. **Ask questions** across all uploaded documents with token-efficient RAG

## Setup

1. Set environment variables (or create a `.env` file in `python/`):
   ```bash
   FOUNDRY_PROJECT_ENDPOINT=https://your-project.services.ai.azure.com/
   AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4.1
   AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.services.ai.azure.com/
   ```

2. Log in with Azure CLI:
   ```bash
   az login
   ```

3. Run with DevUI:
   ```bash
   devui packages/azure-contentunderstanding/samples/devui_azure_openai_file_search_agent
   ```

4. Open the DevUI URL in your browser and start uploading files.

## Supported File Types

| Type | Formats | CU Analyzer (auto-detected) |
|------|---------|----------------------------|
| Documents | PDF, DOCX, XLSX, PPTX, HTML, TXT, Markdown | `prebuilt-documentSearch` |
| Images | JPEG, PNG, TIFF, BMP | `prebuilt-documentSearch` |
| Audio | WAV, MP3, FLAC, OGG, M4A | `prebuilt-audioSearch` |
| Video | MP4, MOV, AVI, WebM | `prebuilt-videoSearch` |

## vs. devui_multimodal_agent

| Feature | multimodal_agent | file_search_agent |
|---------|-----------------|-------------------|
| CU extraction | ✅ Full content injected | ✅ Content indexed in vector store |
| RAG | ❌ | ✅ file_search retrieves top-k chunks |
| Large docs (100+ pages) | ⚠️ May exceed context window | ✅ Token-efficient |
| Multiple large files | ⚠️ Context overflow risk | ✅ All indexed, searchable |
| Best for | Small docs, quick inspection | Large docs, multi-file Q&A |
