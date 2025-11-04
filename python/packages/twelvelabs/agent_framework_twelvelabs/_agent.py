# Copyright (c) Microsoft. All rights reserved.

"""Specialized agent for video processing with Twelve Labs."""

import os
from typing import Any, Dict, List, Optional

from agent_framework import ChatAgent
from agent_framework._middleware import AgentMiddleware

from ._client import TwelveLabsClient, TwelveLabsSettings
from ._middleware import VideoUploadProgressMiddleware
from ._tools import TwelveLabsTools


class VideoProcessingAgent(ChatAgent):
    """Specialized agent for video processing with Twelve Labs Pegasus.

    This agent comes pre-configured with all Twelve Labs tools and optimized
    instructions for video analysis tasks.

    Example:
        ```python
        from agent_framework.azure import AzureOpenAIChatClient
        from agent_framework_twelvelabs import VideoProcessingAgent

        # Create agent with Azure OpenAI
        agent = VideoProcessingAgent(
            chat_client=AzureOpenAIChatClient(...)
        )

        # Upload and analyze video
        result = await agent.run(
            "Upload this video and tell me what happens: sample.mp4"
        )

        # Ask follow-up questions
        followup = await agent.run(
            "What were the main topics discussed in the video?"
        )
        ```

    """

    def __init__(
        self,
        name: str = "video_analyst",
        chat_client: Optional[Any] = None,
        twelvelabs_client: Optional[TwelveLabsClient] = None,
        twelvelabs_settings: Optional[TwelveLabsSettings] = None,
        instructions: Optional[str] = None,
        middleware: Optional[List[AgentMiddleware]] = None,
        enable_progress: bool = True,
        **kwargs,
    ):
        """Initialize the video processing agent.

        Args:
            name: Agent name (default: "video_analyst")
            chat_client: Chat client for LLM interaction. If not provided,
                attempts to create Azure OpenAI client from environment.
            twelvelabs_client: Twelve Labs client instance. If not provided,
                creates one from settings or environment.
            twelvelabs_settings: Configuration for Twelve Labs. If not provided,
                loads from environment variables.
            instructions: Custom instructions for the agent. If not provided,
                uses optimized default instructions.
            middleware: List of middleware to apply. Progress middleware is
                added by default if enable_progress is True.
            enable_progress: Whether to enable upload progress reporting (default: True)
            **kwargs: Additional arguments passed to ChatAgent

        """
        # Initialize Twelve Labs client
        if not twelvelabs_client:
            settings = twelvelabs_settings or TwelveLabsSettings()
            twelvelabs_client = TwelveLabsClient(settings)

        # Create tools
        tl_tools = TwelveLabsTools(twelvelabs_client)

        # Get all available tools
        tools = kwargs.pop("tools", []) + tl_tools.get_all_tools()

        # Set up instructions
        if not instructions:
            instructions = self._get_default_instructions()

        # Set up middleware
        if middleware is None:
            middleware = []

        # Add progress middleware if enabled
        if enable_progress:
            middleware.append(VideoUploadProgressMiddleware())

        # Create default chat client if not provided
        if not chat_client:
            chat_client = self._create_default_chat_client()

        # Initialize parent ChatAgent
        super().__init__(
            name=name,
            instructions=instructions,
            chat_client=chat_client,
            tools=tools,
            middleware=middleware,
            **kwargs,
        )

        # Store client references
        self.twelvelabs_client = twelvelabs_client
        self.tl_tools = tl_tools
        self.tools = tools
        self.current_video_id = None  # Track the current video for context

    def _get_default_instructions(self) -> str:
        """Get default optimized instructions for video processing."""
        return """You are an advanced video analysis expert powered by Twelve Labs Pegasus.

Your capabilities include:
- Uploading and indexing videos from files or URLs
- Answering detailed questions about video content
- Generating comprehensive summaries of videos
- Creating chapter markers with timestamps
- Extracting key highlights and moments
- Processing multiple videos in batch

CRITICAL CONTEXT MANAGEMENT:
- When you successfully upload a video, REMEMBER its video_id for the entire conversation
- When users ask follow-up questions about "the video" or "this video", use the most
  recently uploaded video_id
- If a user asks about visual style, characters, chapters, or any analysis without
  specifying a video, assume they mean the most recently uploaded video
- Always maintain context of what videos have been uploaded in the conversation

When users provide videos:
1. Upload and index the video using the upload_video tool
2. Wait for processing to complete (you'll receive a video_id)
3. REMEMBER this video_id for all subsequent operations
4. When users ask follow-up questions, use this video_id automatically

For video uploads:
- Support both local file paths and URLs
- For large files, the upload may take some time - keep the user informed
- Always confirm successful upload with the video_id
- STORE the video_id mentally for the conversation

For video analysis:
- When users ask about "the video" without specifying, use the most recent video_id
- Be specific and detailed in your responses
- Reference timestamps when discussing specific moments
- If asked about multiple aspects, address each thoroughly

For batch operations:
- Process videos efficiently using the batch tools
- Provide clear summaries of results
- Handle errors gracefully and inform users of any issues

Remember:
- MAINTAIN CONTEXT: Track which videos have been uploaded in this conversation
- When users ask follow-up questions, they're referring to the video you just uploaded
- Always base responses on actual video content, not assumptions
- Provide timestamps and specific details when available"""

    def _create_default_chat_client(self):
        """Create a default chat client from environment variables."""
        # Try Azure OpenAI first
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

        if azure_endpoint and azure_deployment:
            try:
                from agent_framework.azure import AzureOpenAIChatClient
                from azure.identity import DefaultAzureCredential

                return AzureOpenAIChatClient(
                    endpoint=azure_endpoint,
                    deployment_name=azure_deployment,
                    credential=DefaultAzureCredential(),
                )
            except ImportError:
                pass

        # Try OpenAI
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from agent_framework.openai import OpenAIChatClient

                return OpenAIChatClient(
                    api_key=openai_key,
                    model_id=os.getenv("OPENAI_CHAT_MODEL_ID"),
                )
            except ImportError:
                pass

        raise ValueError(
            "No chat client provided and unable to create default from environment. "
            "Please provide a chat_client or set AZURE_OPENAI_* or OPENAI_API_KEY "
            "environment variables."
        )

    async def upload_and_analyze(
        self,
        video_source: str,
        operations: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Upload and analyze a video in one call.

        Args:
            video_source: Path to video file or URL
            operations: List of operations to perform after upload
                (e.g., ["summarize", "chapters", "highlights"])
            **kwargs: Additional arguments for operations

        Returns:
            Dictionary with video_id and operation results

        Example:
            ```python
            results = await agent.upload_and_analyze(
                "demo.mp4",
                operations=["summarize", "chapters"]
            )
            print(f"Video ID: {results['video_id']}")
            print(f"Summary: {results['summary']}")
            ```

        """
        # Upload video
        if video_source.startswith("http"):
            upload_result = await self.tl_tools.upload_video(url=video_source)
        else:
            upload_result = await self.tl_tools.upload_video(file_path=video_source)

        video_id = upload_result["video_id"]
        results = {"video_id": video_id, "upload": upload_result}

        # Perform requested operations
        if operations:
            for op in operations:
                if op == "summarize":
                    results["summary"] = await self.tl_tools.summarize_video(
                        video_id, **kwargs
                    )
                elif op == "chapters":
                    results["chapters"] = await self.tl_tools.generate_chapters(
                        video_id, **kwargs
                    )
                elif op == "highlights":
                    results["highlights"] = await self.tl_tools.generate_highlights(
                        video_id, **kwargs
                    )
                elif op == "info":
                    results["info"] = await self.tl_tools.get_video_info(video_id)

        return results

    async def chat_about_video(
        self,
        video_id: str,
        question: str,
        **kwargs,
    ) -> str:
        """Ask questions about a video directly.

        Args:
            video_id: ID of indexed video
            question: Question about the video
            **kwargs: Additional arguments for chat

        Returns:
            Answer string

        Example:
            ```python
            answer = await agent.chat_about_video(
                "video123",
                "What products were demonstrated?"
            )
            ```

        """
        return await self.tl_tools.chat_with_video(video_id, question, **kwargs)
