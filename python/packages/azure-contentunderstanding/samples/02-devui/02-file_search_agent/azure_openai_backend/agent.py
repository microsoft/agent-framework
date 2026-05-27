# Copyright (c) Microsoft. All rights reserved.
"""DevUI Multi-Modal Agent — CU extraction + file_search RAG.

This agent combines Azure Content Understanding with OpenAI file_search
for token-efficient RAG over large or multi-modal documents.

Upload flow:
  1. CU extracts high-quality markdown (handles scanned PDFs, audio, video)
  2. Extracted markdown is auto-uploaded to an OpenAI vector store
  3. file_search tool is registered so the LLM retrieves top-k chunks
  4. Vector store is configured to auto-expire after inactivity

This is ideal for large documents (100+ pages), long audio recordings,
or multiple files in the same conversation where full-context injection
would exceed the LLM's context window.

Analyzer auto-detection:
  When no analyzer_id is specified, the provider auto-selects the
  appropriate CU analyzer based on media type:
    - Documents/images → prebuilt-documentSearch
    - Audio            → prebuilt-audioSearch
    - Video            → prebuilt-videoSearch

Required environment variables:
  FOUNDRY_PROJECT_ENDPOINT                 — Azure AI Foundry project endpoint
  FOUNDRY_MODEL                            — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL

Run with DevUI:
  devui packages/azure-contentunderstanding/samples/devui_azure_openai_file_search_agent
"""

import os

from agent_framework import Agent
from agent_framework.foundry import (
    ContentUnderstandingContextProvider,
    FileSearchConfig,
    FoundryChatClient,
)
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

# --- Auth ---
_credential = AzureCliCredential()
_cu_api_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
_cu_credential = AzureKeyCredential(_cu_api_key) if _cu_api_key else _credential

_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

# --- LLM client + sync vector store setup ---
# DevUI loads agent modules synchronously at startup while an event loop is already
# running, so we cannot use async APIs here. A sync AIProjectClient is used for
# one-time vector store creation; runtime file uploads use client.client (async).
client = FoundryChatClient(
    project_endpoint=_endpoint,
    model=os.environ["FOUNDRY_MODEL"],
    credential=_credential,
)

_sync_project = AIProjectClient(endpoint=_endpoint, credential=_credential)  # type: ignore[arg-type]
_sync_openai = _sync_project.get_openai_client()
_vector_store = _sync_openai.vector_stores.create(
    name="devui_cu_file_search",
    expires_after={"anchor": "last_active_at", "days": 1},
)
_sync_openai.close()

_file_search_tool = client.get_file_search_tool(
    vector_store_ids=[_vector_store.id],
    max_num_results=3,  # limit chunks to reduce input token usage
)

# --- CU context provider with file_search ---
# client.client is the async OpenAI client used for runtime file uploads.
# No analyzer_id → auto-selects per media type (documents, audio, video)
cu = ContentUnderstandingContextProvider(
    endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
    credential=_cu_credential,
    file_search=FileSearchConfig.from_foundry(
        client.client,  # reuse the LLM client's internal AsyncAzureOpenAI for file uploads
        vector_store_id=_vector_store.id,
        file_search_tool=_file_search_tool,
    ),
)

agent = Agent(
    client=client,
    name="FileSearchDocAgent",
    instructions=(
        "You are a helpful document analysis assistant with RAG capabilities. "
        "When a user uploads files, they are automatically analyzed using Azure Content Understanding "
        "and indexed in a vector store for efficient retrieval. "
        "Analysis takes time (seconds for documents, longer for audio/video) — if a document "
        "is still pending, let the user know and suggest they ask again shortly. "
        "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
        "Multiple files can be uploaded and queried in the same conversation. "
        "When answering, cite specific content from the documents."
    ),
    context_providers=[cu],
)
