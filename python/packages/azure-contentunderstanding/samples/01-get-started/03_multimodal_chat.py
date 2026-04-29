# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-azure-contentunderstanding",
#     "agent-framework-foundry",
#     "azure-identity",
# ]
# ///
# Run with: uv run packages/azure-contentunderstanding/samples/01-get-started/03_multimodal_chat.py


import asyncio
import os
import time
from pathlib import Path

from agent_framework import Agent, AgentSession, Content, Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from agent_framework.foundry import ContentUnderstandingContextProvider

load_dotenv()

"""
Multi-Modal Chat — PDF, audio, and video in a single turn

This sample demonstrates CU's multi-modal capability: upload a PDF invoice,
an audio call recording, and a video file all at once. The provider analyzes
all three in parallel using the right CU analyzer for each media type.

The provider auto-detects the media type and selects the right CU analyzer:
  - PDF/images  → prebuilt-documentSearch
  - Audio       → prebuilt-audioSearch
  - Video       → prebuilt-videoSearch

Environment variables:
  FOUNDRY_PROJECT_ENDPOINT                — Azure AI Foundry project endpoint
  FOUNDRY_MODEL             — Model deployment name (e.g. gpt-4.1)
  AZURE_CONTENTUNDERSTANDING_ENDPOINT      — CU endpoint URL
"""

# Local PDF from package assets
SAMPLE_PDF = Path(__file__).resolve().parents[1] / "shared" / "sample_assets" / "invoice.pdf"

# Public audio/video from Azure CU samples repo (raw GitHub URLs)
_CU_ASSETS = "https://raw.githubusercontent.com/Azure-Samples/azure-ai-content-understanding-assets/main"
AUDIO_URL = f"{_CU_ASSETS}/audio/callCenterRecording.mp3"
VIDEO_URL = f"{_CU_ASSETS}/videos/sdk_samples/FlightSimulator.mp4"


async def main() -> None:
    # 1. Set up credentials and CU context provider
    credential = AzureCliCredential()

    # No analyzer_id specified — the provider auto-detects from media type:
    #   PDF/images → prebuilt-documentSearch
    #   Audio      → prebuilt-audioSearch
    #   Video      → prebuilt-videoSearch
    cu = ContentUnderstandingContextProvider(
        endpoint=os.environ["AZURE_CONTENTUNDERSTANDING_ENDPOINT"],
        credential=credential,
        max_wait=None,  # wait until each analysis finishes
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
            name="MultiModalAgent",
            instructions=(
                "You are a helpful assistant that can analyze documents, audio, "
                "and video files. Answer questions using the extracted content."
            ),
            context_providers=[cu],
        )

        session = AgentSession()

        # --- Turn 1: Upload all 3 modalities at once ---
        # The provider analyzes all files in parallel using the appropriate
        # CU analyzer for each media type. All results are injected into
        # the same context so the agent can answer about all of them.
        turn1_prompt = (
            "I'm uploading three files: an invoice PDF, a call center "
            "audio recording, and a flight simulator video. "
            "Give a brief summary of each file."
        )
        print("--- Turn 1: Upload PDF + audio + video (parallel analysis) ---")
        print("  (CU analysis may take a few minutes for these audio/video files...)")
        print(f"User: {turn1_prompt}")
        t0 = time.perf_counter()
        response = await agent.run(
            Message(
                role="user",
                contents=[
                    Content.from_text(turn1_prompt),
                    Content.from_data(
                        SAMPLE_PDF.read_bytes(),
                        "application/pdf",
                        additional_properties={"filename": "invoice.pdf"},
                    ),
                    Content.from_uri(
                        AUDIO_URL,
                        media_type="audio/mp3",
                        additional_properties={"filename": "callCenterRecording.mp3"},
                    ),
                    Content.from_uri(
                        VIDEO_URL,
                        media_type="video/mp4",
                        additional_properties={"filename": "FlightSimulator.mp4"},
                    ),
                ],
            ),
            session=session,
        )
        elapsed = time.perf_counter() - t0
        usage = response.usage_details or {}
        print(f"  [Analyzed in {elapsed:.1f}s | Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")

        # --- Turn 2: Detail question about the PDF ---
        turn2_prompt = "What are the line items and their amounts on the invoice?"
        print("--- Turn 2: PDF detail ---")
        print(f"User: {turn2_prompt}")
        response = await agent.run(turn2_prompt, session=session)
        usage = response.usage_details or {}
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")

        # --- Turn 3: Detail question about the audio ---
        turn3_prompt = "What was the customer's issue in the call recording?"
        print("--- Turn 3: Audio detail ---")
        print(f"User: {turn3_prompt}")
        response = await agent.run(turn3_prompt, session=session)
        usage = response.usage_details or {}
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")

        # --- Turn 4: Detail question about the video ---
        turn4_prompt = "What key scenes or actions are shown in the flight simulator video?"
        print("--- Turn 4: Video detail ---")
        print(f"User: {turn4_prompt}")
        response = await agent.run(turn4_prompt, session=session)
        usage = response.usage_details or {}
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")

        # --- Turn 5: Cross-document question ---
        turn5_prompt = (
            "Across all three files, which one contains financial data, "
            "which one involves a customer interaction, and which one is "
            "a visual demonstration?"
        )
        print("--- Turn 5: Cross-document question ---")
        print(f"User: {turn5_prompt}")
        response = await agent.run(turn5_prompt, session=session)
        usage = response.usage_details or {}
        print(f"  [Input tokens: {usage.get('input_token_count', 'N/A')}]")
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

--- Turn 1: Upload PDF + audio + video (parallel analysis) ---
User: I'm uploading three files...
  (CU analysis may take 1-2 minutes for audio/video files...)
  [Analyzed in ~94s | Input tokens: ~2939]
Agent: ### invoice.pdf: An invoice from CONTOSO LTD. to MICROSOFT CORPORATION...
       ### callCenterRecording.mp3: A customer service call about point balance...
       ### FlightSimulator.mp4: A clip discussing neural text-to-speech...

--- Turn 2-5: Detail and cross-document questions ---
(Agent answers from conversation history without re-analysis)
"""
