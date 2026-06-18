# DevUI Multi-Modal Agent

Interactive web UI for uploading and chatting with documents, images, audio, and video using Azure Content Understanding.

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

4. Open <https://localhost:50520/devui> in a browser and start uploading files.

## What You Can Do

- **Upload PDFs** — including scanned/image-based PDFs that LLM vision struggles with
- **Upload images** — handwritten notes, infographics, charts
- **Upload audio** — meeting recordings, call center calls (transcription with speaker ID)
- **Upload video** — product demos, training videos (frame extraction + transcription)
- **Ask questions** across all uploaded documents
- **Check status** — "which documents are ready?" uses the auto-registered `list_documents()` tool
