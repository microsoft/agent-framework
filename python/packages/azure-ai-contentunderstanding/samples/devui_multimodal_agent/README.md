# DevUI Multi-Modal Agent

Interactive web UI for uploading and chatting with documents, images, audio, and video using Azure Content Understanding.

## Setup

1. Set environment variables (or create a `.env` file in `python/`):
   ```bash
   AZURE_AI_PROJECT_ENDPOINT=https://your-project.api.azureml.ms
   AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4.1
   AZURE_CONTENTUNDERSTANDING_ENDPOINT=https://your-cu-resource.cognitiveservices.azure.com/
   ```

2. Log in with Azure CLI:
   ```bash
   az login
   ```

3. Run with DevUI:
   ```bash
   uv run poe devui --agent packages/azure-ai-contentunderstanding/samples/devui_multimodal_agent
   ```

4. Open the DevUI URL in your browser and start uploading files.

## What You Can Do

- **Upload PDFs** — including scanned/image-based PDFs that LLM vision struggles with
- **Upload images** — handwritten notes, infographics, charts
- **Upload audio** — meeting recordings, call center calls (transcription with speaker ID)
- **Upload video** — product demos, training videos (frame extraction + transcription)
- **Ask questions** across all uploaded documents
- **Check status** — "which documents are ready?" uses the auto-registered `list_documents()` tool

  Follow-up → file_search retrieves top-k chunks → LLM answers

CU adds value even for formats file_search supports (PDF): CU-extracted markdown
produces better vector store chunks than raw PDF parsing (85% vs 75% accuracy in testing).
CU also enables formats file_search cannot handle: scanned PDFs, audio, video.

NOTE: This sample requires the OpenAI Responses API for file_search.
It is provider-specific (not available with Anthropic/Ollama).

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[3] / "samples" / "shared" / "sample_assets" / "sample.pdf"


async def main() -> None:
    credential = AzureCliCredential()

    # Step 1: Use CU to extract high-quality markdown from the document
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",
        max_wait=60.0,  # generous timeout for large documents
    )

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    )

    if SAMPLE_PDF_PATH.exists():
        pdf_bytes = SAMPLE_PDF_PATH.read_bytes()
        filename = SAMPLE_PDF_PATH.name
    else:
        print(f"Note: {SAMPLE_PDF_PATH} not found. Using minimal test data.")
        pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        filename = "large_document.pdf"

    # Step 2: Extract markdown via CU (first pass — full content injection)
    print("--- Step 1: CU Extraction ---")
    async with cu:
        from unittest.mock import MagicMock

        from agent_framework._sessions import AgentSession, SessionContext

        msg = Message(
            role="user",
            contents=[
                Content.from_text("Extract content from this document."),
                Content.from_data(pdf_bytes, "application/pdf", additional_properties={"filename": filename}),
            ],
        )
        context = SessionContext(input_messages=[msg])
        state: dict = {}
        session = AgentSession()

        await cu.before_run(agent=MagicMock(), session=session, context=context, state=state)

        docs = state.get("documents", {})
        if not docs:
            print("No documents were analyzed.")
            return

        doc_entry = next(iter(docs.values()))
        if doc_entry["status"] != "ready":
            print(f"Document not ready: {doc_entry['status']}")
            return

        markdown = doc_entry["result"].get("markdown", "")
        print(f"Extracted {len(markdown)} chars of markdown from '{filename}'")

    # Step 3: Upload CU-extracted markdown to OpenAI vector store
    print("\n--- Step 2: Upload to Vector Store ---")
    from openai import AzureOpenAI

    openai_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        api_version="2025-03-01-preview",
        azure_ad_token_provider=credential.get_token("https://cognitiveservices.azure.com/.default").token
        if not os.environ.get("AZURE_OPENAI_API_KEY")
        else None,
    )

    # Save markdown to a temp file and upload
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(markdown)
        temp_path = f.name

    try:
        file = openai_client.files.create(file=open(temp_path, "rb"), purpose="assistants")
        print(f"Uploaded file: {file.id}")

        vector_store = openai_client.vector_stores.create(name="cu_extracted_docs")
        openai_client.vector_stores.files.create(vector_store_id=vector_store.id, file_id=file.id)
        print(f"Vector store: {vector_store.id}")

        # Step 4: Use file_search for RAG retrieval on follow-up questions
        print("\n--- Step 3: RAG Q&A with file_search ---")
        agent = client.as_agent(
            name="LargeDocAgent",
            instructions=(
                "You are a document analyst. Use the file_search tool to find "
                "relevant sections from the document and answer precisely."
            ),
            tools=[{"type": "file_search", "vector_store_ids": [vector_store.id]}],
        )

        response = await agent.run("What are the key points in this document?")
        print(f"Agent: {response}\n")

        response = await agent.run("What numbers or metrics are mentioned?")
        print(f"Agent: {response}\n")

    finally:
        # Cleanup
        os.unlink(temp_path)
        try:
            openai_client.vector_stores.delete(vector_store.id)
            openai_client.files.delete(file.id)
        except Exception:
            pass
        print("Cleaned up vector store and files.")


if __name__ == "__main__":
    asyncio.run(main())
