# Copyright (c) Microsoft. All rights reserved.
"""Sample agent using Azure OpenAI Responses API for Agent Framework DevUI.

This agent uses the Responses API which supports:
- PDF file uploads
- Image uploads
- Audio inputs
- And other multimodal content

The Chat Completions API (AzureOpenAIChatClient) does NOT support PDF uploads.
Use this agent when you need to process documents or other file types.

Required environment variables:
- AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint
- AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME: Deployment name for Responses API
  (falls back to AZURE_OPENAI_CHAT_DEPLOYMENT_NAME if not set)
- AZURE_OPENAI_API_KEY: Your API key (or use Azure CLI auth)
"""

import logging
import os
from typing import Annotated

from agent_framework import ChatAgent, tool
from agent_framework.azure import AzureOpenAIResponsesClient

logger = logging.getLogger(__name__)

# Get deployment name - try responses-specific env var first, fall back to chat deployment
_deployment_name = os.environ.get(
    "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME",
    os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", ""),
)

# Get endpoint - try responses-specific env var first, fall back to default
_endpoint = os.environ.get(
    "AZURE_OPENAI_RESPONSES_ENDPOINT",
    os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
)


def analyze_content(
    query: Annotated[str, "What to analyze or extract from the uploaded content"],
) -> str:
    """Analyze uploaded content based on the user's query.

    This is a placeholder - the actual analysis is done by the model
    when processing the uploaded files.
    """
    return f"Analyzing content for: {query}"


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def summarize_document(
    length: Annotated[str, "Desired summary length: 'brief', 'medium', or 'detailed'"] = "medium",
) -> str:
    """Generate a summary of the uploaded document."""
    return f"Generating {length} summary of the document..."


@tool(approval_mode="never_require")
def extract_key_points(
    max_points: Annotated[int, "Maximum number of key points to extract"] = 5,
) -> str:
    """Extract key points from the uploaded document."""
    return f"Extracting up to {max_points} key points..."


# Agent using Azure OpenAI Responses API (supports PDF uploads!)
agent = ChatAgent(
    name="AzureResponsesAgent",
    description="An agent that can analyze PDFs, images, and other documents using Azure OpenAI Responses API",
    instructions="""
    You are a helpful document analysis assistant. You can:

    1. Analyze uploaded PDF documents and extract information
    2. Summarize document contents
    3. Answer questions about uploaded files
    4. Extract key points and insights

    When a user uploads a file, carefully analyze its contents and provide
    helpful, accurate information based on what you find.

    For PDFs, you can read and understand the text, tables, and structure.
    For images, you can describe what you see and extract any text.
    """,
    chat_client=AzureOpenAIResponsesClient(
        deployment_name=_deployment_name,
        endpoint=_endpoint,
        api_version="2025-03-01-preview",  # Required for Responses API
    ),
    tools=[summarize_document, extract_key_points],
)


def main():
    """Launch the Azure Responses agent in DevUI."""
    from agent_framework_devui import serve

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    logger.info("=" * 60)
    logger.info("Starting Azure Responses Agent")
    logger.info("=" * 60)
    logger.info("")
    logger.info("This agent uses the Azure OpenAI Responses API which supports:")
    logger.info("  - PDF file uploads")
    logger.info("  - Image uploads")
    logger.info("  - Audio inputs")
    logger.info("")
    logger.info("Try uploading a PDF and asking questions about it!")
    logger.info("")
    logger.info("Required environment variables:")
    logger.info("  - AZURE_OPENAI_ENDPOINT")
    logger.info("  - AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")
    logger.info("  - AZURE_OPENAI_API_KEY (or use Azure CLI auth)")
    logger.info("")

    serve(entities=[agent], port=8090, auto_open=True)


if __name__ == "__main__":
    main()
