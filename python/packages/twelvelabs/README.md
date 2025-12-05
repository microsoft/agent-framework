# Twelve Labs Integration for Microsoft Agent Framework

Add video intelligence capabilities to your agents using Twelve Labs Pegasus 1.2 and Marengo 3.0 APIs.

## Features

### Pegasus 1.2 - Video Understanding
- 💬 **Interactive Q&A** - Chat with video content using natural language
- 📝 **Summarization** - Generate comprehensive summaries
- 📑 **Chapter Generation** - Create chapter markers with timestamps
- ✨ **Highlight Extraction** - Extract key moments and highlights

### Marengo 3.0 - Video Search
- 🔍 **Text Search** - Find specific moments using natural language queries
- 🖼️ **Image Search** - Find similar video moments using an image
- 📊 **Semantic Matching** - Multimodal embeddings for accurate results

### General
- 🎥 **Video Upload & Indexing** - Upload videos from files or URLs
- 📊 **Batch Processing** - Process multiple videos concurrently

## Installation

### From Source (Development)

```bash
# Clone the repository
git clone https://github.com/microsoft/agent-framework.git
cd agent-framework/python/packages/twelvelabs

# Install in development mode
pip install -e .
```

### Requirements

- Python 3.10+
- `twelvelabs>=1.0.2` (automatically installed)
- `agent-framework>=1.0.0b251001` (automatically installed)
- Valid Twelve Labs API key

## Quick Start

Set your API key from [Twelve Labs](https://twelvelabs.io):

```bash
export TWELVELABS_API_KEY="your-api-key"
```

### Option 1: Add Video Tools to Your Existing Agent

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework_twelvelabs import TwelveLabsTools

# Add video capabilities to any agent
tools = TwelveLabsTools()
agent = ChatAgent(
    chat_client=OpenAIChatClient(),  # or any chat client
    instructions="You are a helpful assistant",
    tools=tools.get_all_tools()  # Adds 10 video functions
)

# Now your agent can process videos
result = await agent.run("Upload and analyze video.mp4")
```

### Option 2: Use Pre-configured Video Agent

```python
import asyncio
from agent_framework import ChatMessage
from agent_framework.openai import OpenAIChatClient
from agent_framework_twelvelabs import VideoProcessingAgent

async def main():
    # Create agent
    agent = VideoProcessingAgent(
        chat_client=OpenAIChatClient(
            api_key="your-openai-key",
            model_id="gpt-4"
        )
    )

    # Build conversation with message history
    messages = []

    # Upload video
    messages.append(ChatMessage(role="user", text="Upload video.mp4"))
    response = await agent.run(messages)
    print(f"Upload: {response}")
    messages.append(ChatMessage(role="assistant", text=str(response)))

    # Ask about the video - agent maintains context
    messages.append(ChatMessage(role="user", text="What do you see in this video?"))
    response = await agent.run(messages)
    print(f"Analysis: {response}")

    # Generate chapters
    messages.append(ChatMessage(role="user", text="Generate chapter markers for this video"))
    response = await agent.run(messages)
    print(f"Chapters: {response}")

asyncio.run(main())
```

### Option 3: Direct Client Usage (No Agent)

```python
from agent_framework_twelvelabs import TwelveLabsClient

# For custom workflows without an agent
client = TwelveLabsClient()

# Upload video
metadata = await client.upload_video(
    url="https://example.com/video.mp4"  # or file_path="video.mp4"
)

# Chat with video (Pegasus)
response = await client.chat_with_video(
    video_id=metadata.video_id,
    query="What products are shown?"
)

# Search video (Marengo)
results = await client.search_videos(
    query="person walking",
    limit=5
)
for result in results.results:
    print(f"Found at {result.start_time}-{result.end_time}s (score: {result.score})")

# Search by image (Marengo)
results = await client.search_by_image(
    image_path="screenshot.jpg",
    limit=5
)

# Generate summary
summary = await client.summarize_video(video_id=metadata.video_id)

# Generate chapters
chapters = await client.generate_chapters(video_id=metadata.video_id)

# Generate highlights
highlights = await client.generate_highlights(video_id=metadata.video_id)
```

## Configuration

```bash
export TWELVELABS_API_KEY="your-api-key"
```

Additional configuration options are available through environment variables or `TwelveLabsSettings`.

## Available Tools

These 10 AI functions are added to your agent when using TwelveLabsTools:

### Video Understanding (Pegasus 1.2)
- `chat_with_video` - Q&A with video content
- `summarize_video` - Generate comprehensive video summaries
- `generate_chapters` - Create chapter markers with timestamps
- `generate_highlights` - Extract key highlights and moments

### Video Search (Marengo 3.0)
- `search_videos` - Search videos using natural language queries
- `search_by_image` - Find similar moments using an image

### General
- `upload_video` - Upload and index videos from file path or URL
- `get_video_info` - Get video metadata
- `delete_video` - Remove indexed videos
- `batch_process_videos` - Process multiple videos concurrently

The agent can automatically call these tools based on user requests.

## Video Requirements

### Supported Formats
- All FFmpeg-compatible video and audio codecs
- Common formats: MP4, AVI, MOV, MKV, WebM

### Technical Specifications
- **Resolution**: 360x360 minimum, 3840x2160 maximum
- **Aspect Ratios**: 1:1, 4:3, 4:5, 5:4, 16:9, 9:16, 17:9
- **Duration**: 4 seconds to 60 minutes (Pegasus 1.2)
- **File Size**: Up to 5GB (configurable)