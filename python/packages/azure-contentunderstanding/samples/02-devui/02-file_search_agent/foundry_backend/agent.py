# Copyright (c) Microsoft. All rights reserved.
"""DevUI Multi-Modal Agent — CU extraction + file_search RAG via Azure AI Foundry.

This agent combines Azure Content Understanding with Foundry's file_search
for token-efficient RAG over large or multi-modal documents.

Upload flow:
  1. CU extracts high-quality markdown (handles scanned PDFs, audio, video)
  2. Extracted markdown is uploaded to a Foundry vector store
  3. file_search tool is registered so the LLM retrieves top-k chunks
  4. Uploaded files are cleaned up on server shutdown

This sample uses ``FoundryChatClient`` and ``FoundryFileSearchBackend``.
For the OpenAI Responses API variant, see ``devui_azure_openai_file_search_agent``.

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
  devui packages/azure-contentunderstanding/samples/devui_foundry_file_search_agent
"""

import os

from agent_framework import Agent
from agent_framework.foundry import (
    ContentUnderstandingContextProvider,
    FileSearchConfig,
    FoundryChatClient,
)
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# --- Auth ---
# AzureCliCredential for Foundry. CU API key optional if on a different resource.
_credential = AzureCliCredential()
_cu_api_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
_cu_credential = AzureKeyCredential(_cu_api_key) if _cu_api_key else _credential

# --- Foundry LLM client ---
client = FoundryChatClient(
    project_endpoint=os.environ.get("FOUNDRY_PROJECT_ENDPOINT", ""),
    model=os.environ.get("FOUNDRY_MODEL", ""),
    credential=_credential,
)

# --- Create vector store (sync client to avoid event loop conflicts in DevUI) ---
_token = _credential.get_token("https://ai.azure.com/.default").token
_sync_openai = AzureOpenAI(
    azure_endpoint=os.environ.get("FOUNDRY_PROJECT_ENDPOINT", ""),
    azure_ad_token=_token,
    api_version="2025-04-01-preview",
)
_vector_store = _sync_openai.vector_stores.create(
    name="devui_cu_foundry_file_search",
    expires_after={"anchor": "last_active_at", "days": 1},
)
_sync_openai.close()

_file_search_tool = client.get_file_search_tool(
    vector_store_ids=[_vector_store.id],
    max_num_results=3,  # limit chunks to reduce input token usage
)

# --- CU context provider with file_search ---
# No analyzer_id → auto-selects per media type (documents, audio, video)
cu = ContentUnderstandingContextProvider(
    endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
    credential=_cu_credential,
    # max_wait is the combined budget for CU analysis + vector store upload.
    # For file_search mode, 10s gives enough time for small documents to be
    # analyzed and indexed in one turn.  Larger files (audio, video) will
    # be deferred to background and resolved on the next turn.
    max_wait=10.0,
    file_search=FileSearchConfig.from_foundry(
        client.client,
        vector_store_id=_vector_store.id,
        file_search_tool=_file_search_tool,
    ),
)

agent = Agent(
    client=client,
    name="FoundryFileSearchDocAgent",
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
