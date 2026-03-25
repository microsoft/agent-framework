# Copyright (c) Microsoft. All rights reserved.
"""DevUI Multi-Modal Agent — CU extraction + file_search RAG.

This agent combines Azure Content Understanding with OpenAI file_search
for token-efficient RAG over large or multi-modal documents.

Upload flow:
  1. CU extracts high-quality markdown (handles scanned PDFs, audio, video)
  2. Extracted markdown is auto-uploaded to an OpenAI vector store
  3. file_search tool is registered so the LLM retrieves top-k chunks
  4. Vector store is cleaned up on server shutdown

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
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL

Run with DevUI:
  devui packages/azure-ai-contentunderstanding/samples/devui_file_search_agent
"""

import os
from typing import Any

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

from agent_framework_azure_ai_contentunderstanding import (
    ContentUnderstandingContextProvider,
    FileSearchConfig,
)

load_dotenv()

# --- Auth ---
_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
_credential = AzureCliCredential() if not _api_key else None
_cu_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
_cu_credential: AzureKeyCredential | AzureCliCredential = (
    AzureKeyCredential(_cu_key) if _cu_key else _credential  # type: ignore[assignment]
)

# --- Async OpenAI client for vector store operations ---
_openai_kwargs: dict[str, Any] = {
    "azure_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    "api_version": "2025-03-01-preview",
}
if _api_key:
    _openai_kwargs["api_key"] = _api_key
else:
    _token = _credential.get_token("https://cognitiveservices.azure.com/.default").token  # type: ignore[union-attr]
    _openai_kwargs["azure_ad_token"] = _token
_openai_client = AsyncAzureOpenAI(**_openai_kwargs)

# --- CU context provider with file_search ---
# No analyzer_id → auto-selects per media type (documents, audio, video)
cu = ContentUnderstandingContextProvider(
    endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
    credential=_cu_credential,
    max_wait=10.0,
    file_search=FileSearchConfig(
        openai_client=_openai_client,
    ),
)

# --- LLM client ---
_client_kwargs: dict[str, Any] = {
    "project_endpoint": os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    "deployment_name": os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
}
if _api_key:
    _client_kwargs["api_key"] = _api_key
else:
    _client_kwargs["credential"] = _credential
client = AzureOpenAIResponsesClient(**_client_kwargs)

agent = client.as_agent(
    name="FileSearchDocAgent",
    instructions=(
        "You are a helpful document analysis assistant with RAG capabilities. "
        "When a user uploads files, they are automatically analyzed using Azure Content Understanding "
        "and indexed in a vector store for efficient retrieval. "
        "Use file_search to find relevant sections from uploaded documents. "
        "Use list_documents() to check which documents are ready, pending, or failed. "
        "Use get_analyzed_document() to retrieve the full content of a specific document. "
        "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
        "Multiple files can be uploaded and queried in the same conversation. "
        "When answering, cite specific content from the documents."
    ),
    context_providers=[cu],
)
