# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-foundry",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/01-get-started/02_multi_turn_session.py

# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from pathlib import Path

from agent_framework import Agent, AgentSession, Content, Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework_azure_ai_contentunderstanding import ContentUnderstandingContextProvider

load_dotenv()

"""
Multi-Turn Session — Cached results across turns

This sample demonstrates multi-turn document Q&A using an AgentSession.
The session persists CU analysis results and conversation history across
turns so the agent can answer follow-up questions about previously
uploaded documents without re-analyzing them.

Key concepts:
  - AgentSession keeps CU state and conversation history across agent.run() calls
  - Turn 1: CU analyzes the PDF and injects full content into context
  - Turn 2: Unrelated question — agent answers from general knowledge
  - Turn 3: Detailed question — agent uses document content from conversation
    history (injected in Turn 1) to answer precisely

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  AZURE_OPENAI_DEPLOYMENT_NAME             — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF_PATH = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"


async def main() -> None:
    credential = AzureCliCredential()

    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        analyzer_id="prebuilt-documentSearch",
        max_wait=None,  # wait until CU analysis finishes (no background deferral)
    )

    client = FoundryChatClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        credential=credential,
    )

    async with cu:
        agent = Agent(
            client=client,
            name="DocumentQA",
            instructions=(
                "You are a helpful document analyst. Use the analyzed document "
                "content and extracted fields to answer questions precisely."
            ),
            context_providers=[cu],
        )

        # Create a persistent session — this keeps CU state across turns
        session = AgentSession()

        # --- Turn 1: Upload PDF ---
        # CU analyzes the PDF and injects full content into context.
        print("--- Turn 1: Upload PDF ---")
        pdf_bytes = SAMPLE_PDF_PATH.read_bytes()
        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text("What is this document about?"),
                    Content.from_data(
                        pdf_bytes,
                        "application/pdf",
                        additional_properties={"filename": SAMPLE_PDF_PATH.name},
                    ),
                ],
            ),
            session=session,  # <-- persist state across turns
        )
        usage = response.usage_details or {}
        print(f"Agent: {response}")
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]\n")

        # --- Turn 2: Unrelated question ---
        # No document needed — agent answers directly with minimal tokens.
        print("--- Turn 2: Unrelated question ---")
        response = await agent.run("What is the capital of France?", session=session)
        usage = response.usage_details or {}
        print(f"Agent: {response}")
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]\n")

        # --- Turn 3: Detailed follow-up ---
        # The agent answers from the full document content that was injected
        # into conversation history in Turn 1. No re-analysis or tool call needed.
        print("--- Turn 3: Detailed follow-up ---")
        response = await agent.run(
            "What is the shipping address on the invoice?",
            session=session,
        )
        usage = response.usage_details or {}
        print(f"Agent: {response}")
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]\n")


if __name__ == "__main__":
    asyncio.run(main())
