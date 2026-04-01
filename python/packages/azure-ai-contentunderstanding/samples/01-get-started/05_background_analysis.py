# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-ai-contentunderstanding",
#     "agent-framework-foundry",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-ai-contentunderstanding/samples/01-get-started/05_background_analysis.py

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
Background Analysis — Non-blocking file processing with status tracking

This sample demonstrates the background analysis workflow: when CU analysis
takes longer than max_wait, the provider defers it to a background task and
the agent informs the user. On the next turn, the provider checks if the
background task has completed and surfaces the result.

This is useful for large files (audio/video) where CU analysis can take
30-60+ seconds. The agent remains responsive while files are being processed.

Key concepts:
  - max_wait=1.0 forces background deferral (analysis takes longer than 1s)
  - The provider tracks document status: analyzing → ready
  - list_documents() tool shows current status of all tracked documents
  - On subsequent turns, completed background tasks are automatically resolved

TIP: For an interactive version with file upload UI, see the DevUI samples
     in 02-devui/01-multimodal_agent/

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  FOUNDRY_MODEL             — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

SAMPLE_PDF = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"


async def main() -> None:
    # 1. Set up credentials and CU context provider with short timeout
    credential = AzureCliCredential()

    # Set max_wait=1.0 to force background deferral.
    # Any CU analysis taking longer than 1 second will be deferred to a
    # background task. The agent is told the file is "being analyzed" and
    # can respond immediately. The result is picked up on the next turn.
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        max_wait=1.0,  # 1 second — forces background deferral for most files
    )

    # 2. Set up the LLM client
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=credential,
    )

    # 3. Create agent and session
    async with cu:
        agent = Agent(
            client=client,
            name="BackgroundAgent",
            instructions=(
                "You are a helpful assistant. When a document is still being "
                "analyzed, tell the user and suggest they ask again shortly. "
                "Use list_documents() to check document status."
            ),
            context_providers=[cu],
        )

        session = AgentSession()

        # 4. Turn 1: Upload PDF (will timeout and defer to background)
        # The provider starts CU analysis but it won't finish within 1 second,
        # so it defers to a background task. The agent is told the document
        # status is "analyzing" and responds accordingly.
        print("--- Turn 1: Upload PDF (max_wait=1s, will defer to background) ---")
        print("User: Analyze this invoice for me.")
        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text("Analyze this invoice for me."),
                    Content.from_data(
                        SAMPLE_PDF.read_bytes(),
                        "application/pdf",
                        additional_properties={"filename": "invoice.pdf"},
                    ),
                ],
            ),
            session=session,
        )
        usage = response.usage_details or {}
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")

        # 5. Turn 2: Check status (analysis likely still in progress)
        print("--- Turn 2: Check status ---")
        print("User: Is the invoice ready yet?")
        response = await agent.run("Is the invoice ready yet?", session=session)
        usage = response.usage_details or {}
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")

        # 6. Wait for background analysis to complete
        print("  (Waiting 30 seconds for CU background analysis to finish...)\n")
        await asyncio.sleep(30)

        # 7. Turn 3: Ask again (background task should be resolved now)
        # The provider checks the background task, finds it complete, and
        # injects the full document content into context. The agent can now
        # answer questions about the invoice.
        print("--- Turn 3: Ask again (analysis should be complete) ---")
        print("User: What is the total amount due on the invoice?")
        response = await agent.run(
            "What is the total amount due on the invoice?",
            session=session,
        )
        usage = response.usage_details or {}
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

--- Turn 1: Upload PDF (max_wait=1s, will defer to background) ---
User: Analyze this invoice for me.
  [Input tokens: 319]
Agent: invoice.pdf is still being analyzed. Please ask again in a moment.

--- Turn 2: Check status ---
User: Is the invoice ready yet?
  [Input tokens: 657]
Agent: Not yet -- invoice.pdf is still in analyzing status.

  (Waiting 30 seconds for CU background analysis to finish...)

--- Turn 3: Ask again (analysis should be complete) ---
User: What is the total amount due on the invoice?
  [Input tokens: 1252]
Agent: The amount due on the invoice is $610.00.
"""
