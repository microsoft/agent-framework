# Copyright (c) Microsoft. All rights reserved.
"""DevUI Multi-Modal Agent — file upload + CU-powered analysis.

This agent uses Azure Content Understanding to analyze uploaded files
(PDFs, scanned documents, handwritten images, audio recordings, video)
and answer questions about them through the DevUI web interface.

Unlike the standard azure_responses_agent which sends files directly to the LLM,
this agent uses CU for structured extraction — superior for scanned PDFs,
handwritten content, audio transcription, and video analysis.

Required environment variables:
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME   — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL

Run with DevUI:
  uv run poe devui --agent packages/azure-ai-contentunderstanding/samples/devui_multimodal_agent
"""

import os

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_ai_contentunderstanding import ContentUnderstandingContextProvider

load_dotenv()

# --- Auth ---
# AzureCliCredential works for both Azure OpenAI and CU.
# API keys can be set separately if the services are on different resources.
_credential = AzureCliCredential()
_openai_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
_cu_api_key = os.environ.get("AZURE_CONTENTUNDERSTANDING_API_KEY")
_cu_credential = AzureKeyCredential(_cu_api_key) if _cu_api_key else _credential

cu = ContentUnderstandingContextProvider(
    endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
    credential=_cu_credential,
    max_wait=5.0,
)

if _openai_api_key:
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        api_key=_openai_api_key,
    )
else:
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=_credential,
    )

agent = client.as_agent(
    name="MultiModalDocAgent",
    instructions=(
        "You are a helpful document analysis assistant. "
        "When a user uploads files, they are automatically analyzed using Azure Content Understanding. "
        "Use list_documents() to check which documents are ready, pending, or failed and to see which files are available for answering questions. "
        "Tell the user if any documents are still being analyzed. "
        "You can process PDFs, scanned documents, handwritten images, audio recordings, and video files. "
        "When answering, cite specific content from the documents."
    ),
    context_providers=[cu],
)
