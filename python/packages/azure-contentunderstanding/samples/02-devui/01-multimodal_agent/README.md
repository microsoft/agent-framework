# DevUI Multi-Modal Agent

Interactive web UI for uploading and chatting with documents, images, audio, and video using Azure Content Understanding.

## Setup

1. Set environment variables (or create a `.env` file in `python/`):
   ```bash
   FOUNDRY_PROJECT_ENDPOINT=https://your-project.api.azureml.ms
   AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4.1
   AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.cognitiveservices.azure.com/
   ```

2. Log in with Azure CLI:
   ```bash
   az login
   ```

3. Run with DevUI:
   ```bash
   uv run poe devui --agent packages/azure-contentunderstanding/samples/devui_multimodal_agent
   ```

4. Open the DevUI URL in your browser and start uploading files.

## What You Can Do

- **Upload PDFs** — including scanned/image-based PDFs that LLM vision struggles with
- **Upload images** — handwritten notes, infographics, charts
- **Upload audio** — meeting recordings, call center calls (transcription with speaker ID)
- **Upload video** — product demos, training videos (frame extraction + transcription)
- **Ask questions** across all uploaded documents
- **Check status** — "which documents are ready?" uses the auto-registered `list_documents()` tool
