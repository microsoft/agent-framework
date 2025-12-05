#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""Sample: Video Q&A and Search with Twelve Labs Pegasus and Marengo.

This sample demonstrates how to use the VideoProcessingAgent to:
1. Upload and index a video (from URL or local file)
2. Get video metadata
3. Ask questions about the video content (Pegasus)
4. Search for specific moments in the video (Marengo)
5. Generate summaries
6. Create chapter markers
7. Generate highlights
8. Clean up by deleting the video

Prerequisites:
    - Set TWELVELABS_API_KEY environment variable
    - Set OPENAI_API_KEY environment variable
    - Set OPENAI_CHAT_MODEL_ID environment variable (e.g., "gpt-4")
    - Install: pip install agent-framework-twelvelabs

Usage:
    # With a URL
    python video_qa_example.py https://example.com/video.mp4

    # With a local file
    python video_qa_example.py /path/to/video.mp4

    # With default sample video
    python video_qa_example.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_framework import ChatMessage
from agent_framework.openai import OpenAIChatClient
from agent_framework_twelvelabs import VideoProcessingAgent

# Load environment variables from .env file
load_dotenv(override=True)


async def main():
    """Run the video Q&A example."""
    # Check for required environment variables
    if not os.getenv("TWELVELABS_API_KEY"):
        print("❌ Error: TWELVELABS_API_KEY environment variable not set")
        print("Please set it with: export TWELVELABS_API_KEY=your-api-key")
        return

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY=your-api-key")
        return

    # Get video source (URL or local file path) from command line or use default
    if len(sys.argv) > 1:
        video_source = sys.argv[1]
    else:
        # Default to Big Buck Bunny sample video
        video_source = "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
        print(f"No video provided, using default: {video_source}")

    # Create the video processing agent
    agent = VideoProcessingAgent(
        chat_client=OpenAIChatClient(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_id=os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4")
        )
    )

    # Conversation history
    messages = []

    print("\n" + "=" * 60)
    print("🎬 Video Q&A and Search with Twelve Labs Pegasus + Marengo")
    print("=" * 60)

    # 1. Upload video
    print("\n1. UPLOADING VIDEO")
    print("-" * 60)
    print(f"Uploading: {video_source}")
    messages.append(ChatMessage(role="user", text=f"Upload {video_source}"))
    response = await agent.run(messages)
    print(f"✅ {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # 2. Get video info
    print("\n2. GETTING VIDEO INFO")
    print("-" * 60)
    messages.append(ChatMessage(role="user", text="Get the metadata and info for this video"))
    response = await agent.run(messages)
    print(f"✅ {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # 3. Chat with video
    print("\n3. ASKING QUESTIONS ABOUT VIDEO")
    print("-" * 60)
    messages.append(ChatMessage(role="user", text="What animals or characters are in this video?"))
    response = await agent.run(messages)
    print(f"✅ {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # 4. Search video (Marengo)
    print("\n4. SEARCHING VIDEO (Marengo 3.0)")
    print("-" * 60)
    messages.append(ChatMessage(role="user", text="Search the video for 'rabbit' or 'bunny'"))
    response = await agent.run(messages)
    print(f"✅ {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # 5. Summarize video
    print("\n5. GENERATING SUMMARY")
    print("-" * 60)
    messages.append(ChatMessage(role="user", text="Generate a summary of this video"))
    response = await agent.run(messages)
    print(f"✅ {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # 6. Generate chapters
    print("\n6. GENERATING CHAPTERS")
    print("-" * 60)
    messages.append(ChatMessage(role="user", text="Generate chapter markers for this video"))
    response = await agent.run(messages)
    print(f"✅ {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # 7. Generate highlights
    print("\n7. GENERATING HIGHLIGHTS")
    print("-" * 60)
    messages.append(ChatMessage(role="user", text="Generate highlights for this video"))
    response = await agent.run(messages)
    print(f"✅ {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # 8. Delete video
    print("\n8. CLEANING UP")
    print("-" * 60)
    messages.append(ChatMessage(role="user", text="Delete this video from the index"))
    response = await agent.run(messages)
    print(f"✅ {response}")

    print("\n" + "=" * 60)
    print("✅ ALL OPERATIONS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
