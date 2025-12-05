#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""Test: Upload, Search, then Chat with Twelve Labs.

This script tests the core Twelve Labs workflow:
1. Upload a video (uses Pegasus + Marengo index)
2. Search the video using Marengo 3.0
3. Chat with the video using Pegasus 1.2
4. Clean up by deleting the video

Usage:
    python test_upload_search_chat.py [video_url_or_path]
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from agent_framework_twelvelabs import TwelveLabsClient

# Load environment variables
load_dotenv(override=True)


async def main():
    # Check for API key
    if not os.getenv("TWELVELABS_API_KEY"):
        print("Error: TWELVELABS_API_KEY not set")
        return

    # Get video source from args or use default
    if len(sys.argv) > 1:
        video_source = sys.argv[1]
    else:
        video_source = "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"
        print(f"Using default video: {video_source}")

    # Create client
    client = TwelveLabsClient()

    print("\n" + "=" * 60)
    print("Test: Upload -> Search -> Chat")
    print("=" * 60)

    # 1. Upload video
    print("\n[1/4] UPLOADING VIDEO...")
    print("-" * 40)
    try:
        metadata = await client.upload_video(url=video_source)
        video_id = metadata.video_id
        print(f"Uploaded: {video_id}")
        print(f"  Resolution: {metadata.width}x{metadata.height}")
        print(f"  FPS: {metadata.fps}")
    except Exception as e:
        print(f"Upload failed: {e}")
        return

    # 2. Search video (Marengo 3.0)
    print("\n[2/4] SEARCHING VIDEO (Marengo 3.0)...")
    print("-" * 40)
    try:
        search_query = "rabbit"
        results = await client.search_videos(query=search_query, limit=5)
        print(f"Query: '{search_query}'")
        print(f"Found {results.total_count} results:")
        for i, result in enumerate(results.results, 1):
            print(f"  {i}. {result.start_time:.1f}s - {result.end_time:.1f}s (score: {result.score:.2f})")
    except Exception as e:
        print(f"Search failed: {e}")

    # 3. Chat with video (Pegasus 1.2)
    print("\n[3/4] CHATTING WITH VIDEO (Pegasus 1.2)...")
    print("-" * 40)
    try:
        question = "What is the main character doing in this video?"
        print(f"Q: {question}")
        answer = await client.chat_with_video(video_id=video_id, query=question)
        print(f"A: {answer}")
    except Exception as e:
        print(f"Chat failed: {e}")

    # 4. Clean up
    print("\n[4/4] CLEANING UP...")
    print("-" * 40)
    try:
        await client.delete_video(video_id)
        print(f"Deleted video: {video_id}")
    except Exception as e:
        print(f"Delete failed: {e}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
