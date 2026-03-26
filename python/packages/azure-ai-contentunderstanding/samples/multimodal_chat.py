# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-core",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/multimodal_chat.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Content, Message
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_ai_contentunderstanding import ContentUnderstandingContextProvider

load_dotenv()

"""
Multi-Modal Chat — PDF + audio + video in the same session

This sample demonstrates CU's unique multi-modal value: process PDFs,
audio recordings, and video files in the same conversation with
background processing and status awareness.

When a large file (audio/video) exceeds the analysis timeout, the agent
informs the user and automatically picks up the result on subsequent turns.

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_DIR = Path(__file__).resolve().parents[3] / "samples" / "shared" / "sample_assets"


async def main() -> None:
    # Support both API key and credential-based auth
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    credential = AzureCliCredential() if not api_key else None
    cu_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
    cu_credential = AzureKeyCredential(cu_key) if cu_key else credential

    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=cu_credential,
        max_wait=5.0,  # 5 seconds — audio/video will defer to background
    )

    client_kwargs = {
        "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        "deployment_name": os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
    }
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        client_kwargs["credential"] = credential
    client = AzureOpenAIResponsesClient(**client_kwargs)

    async with cu:
        agent = client.as_agent(
            name="MultiModalAgent",
            instructions=(
                "You are a helpful assistant that can analyze documents, audio, "
                "and video files. Use list_documents() to check which files are "
                "ready. If a file is still being analyzed, let the user know. "
                "Use get_analyzed_document() to retrieve content when needed."
            ),
            context_providers=[cu],
        )

        # --- Turn 1: Upload a PDF ---
        print("--- Turn 1: Upload PDF ---")

        pdf_path = SAMPLE_DIR / "sample.pdf"
        if pdf_path.exists():
            pdf_bytes = pdf_path.read_bytes()
        else:
            print(f"Note: {pdf_path} not found. Using minimal test data.")
            pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"

        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text("What is this document about?"),
                    Content.from_data(
                        pdf_bytes,
                        "application/pdf",
                        # Always provide filename — used as the document key in list_documents()
                        # and get_analyzed_document(). Without it, a hash-based key is generated.
                        additional_properties={"filename": "report.pdf"},
                    ),
                ],
            )
        )
        print(f"Agent: {response}\n")

        # --- Turn 2: Ask about all uploaded documents ---
        print("--- Turn 2: Check document status ---")
        response = await agent.run("What documents have been uploaded so far? What is their status?")
        print(f"Agent: {response}\n")

        # --- Turn 3: Follow-up question on the PDF ---
        print("--- Turn 3: Follow-up ---")
        response = await agent.run("What are the key numbers or metrics in the document?")
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())
