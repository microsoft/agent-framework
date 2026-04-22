# Copyright (c) Microsoft. All rights reserved.
"""DevUI Multi-Modal Agent — file upload + CU-powered analysis.

This agent uses Azure Content Understanding to analyze uploaded files
(PDFs, scanned documents, handwritten images, audio recordings, video)
and answer questions about them through the DevUI web interface.

Unlike the standard azure_responses_agent which sends files directly to the LLM,
this agent uses CU for structured extraction — superior for scanned PDFs,
handwritten content, audio transcription, and video analysis.

Required environment variables:
  FOUNDRY_PROJECT_ENDPOINT                 — Azure AI Foundry project endpoint
  FOUNDRY_MODEL                            — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL

Run with DevUI:
  uv run poe devui --agent packages/azure-contentunderstanding/samples/devui_multimodal_agent
"""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework.foundry import ContentUnderstandingContextProvider

load_dotenv()

# --- Auth ---
_credential = AzureCliCredential()
_cu_api_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
_cu_credential = AzureKeyCredential(_cu_api_key) if _cu_api_key else _credential

cu = ContentUnderstandingContextProvider(
    endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
    credential=_cu_credential,
    # max_wait controls how long before_run() waits for CU analysis before
    # deferring to background.  For interactive DevUI use, a short timeout
    # (e.g. 5s) keeps the chat responsive — the agent tells the user the
    # file is still being analyzed and resolves it on the next turn.
    # Use max_wait=None to always wait for analysis to complete.
    max_wait=5.0,
)

client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL"],
    credential=_credential,
)

agent = Agent(
    client=client,
    name="MultiModalDocAgent",
    instructions=(
        "You are a helpful document analysis assistant. "
        "When a user uploads files, they are automatically analyzed using Azure Content Understanding. "
        "Use list_documents() to check which documents are ready, pending, or failed "
        "and to see which files are available for answering questions. "
        "Tell the user if any documents are still being analyzed. "
        "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
        "When answering, cite specific content from the documents."
    ),
    context_providers=[cu],
)
