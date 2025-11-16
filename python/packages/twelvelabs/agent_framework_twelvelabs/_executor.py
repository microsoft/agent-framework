# Copyright (c) Microsoft. All rights reserved.

"""Workflow executors for video processing tasks."""

import asyncio
import os
from typing import Any, Dict, Optional

from agent_framework._workflows import Executor, WorkflowContext, handler

from ._client import TwelveLabsClient
from ._types import VideoOperationType, WorkflowInput, WorkflowOutput


class VideoExecutor(Executor):
    """Workflow executor for video processing tasks.

    This executor handles single video processing through a complete pipeline,
    including upload, indexing, and various analysis operations.

    Example:
        ```python
        from agent_framework._workflows import Workflow, WorkflowBuilder
        from agent_framework_twelvelabs import VideoExecutor

        # Create workflow with video executor
        workflow = (
            WorkflowBuilder()
            .add_executor("video", VideoExecutor())
            .add_edge("video")
            .build()
        )

        # Run workflow
        result = await workflow.run({
            "video_source": "presentation.mp4",
            "operations": ["summarize", "chapters"]
        })
        ```

    """

    def __init__(self, client: Optional[TwelveLabsClient] = None):
        """Initialize video executor.

        Args:
            client: Twelve Labs client instance. If not provided, creates default.

        """
        super().__init__()
        self.client = client or TwelveLabsClient()

    @handler
    async def process_video(
        self,
        input: Dict[str, Any],
        ctx: WorkflowContext[Dict[str, Any]],
    ) -> None:
        """Process a video through the full pipeline.

        Args:
            input: Dictionary containing:
                - video_source: File path or URL of video
                - operations: List of operations to perform
                - options: Optional operation-specific options
            ctx: Workflow context for sending messages

        The executor will:
        1. Upload and index the video
        2. Perform requested operations (summarize, chapters, highlights)
        3. Send progress updates throughout
        4. Return final results

        """
        # Parse input
        workflow_input = WorkflowInput(**input)
        start_time = asyncio.get_event_loop().time()

        # Send initial status
        await ctx.send_message(
            {
                "status": "starting",
                "message": "Beginning video processing pipeline",
                "video_source": workflow_input.video_source,
            }
        )

        try:
            # Upload and index video
            await ctx.send_message(
                {"status": "uploading", "message": "Uploading and indexing video..."}
            )

            if os.path.exists(workflow_input.video_source):
                video_metadata = await self.client.upload_video(
                    file_path=workflow_input.video_source,
                    metadata=workflow_input.metadata,
                    progress_callback=lambda curr, total: asyncio.create_task(
                        ctx.send_message(
                            {
                                "status": "upload_progress",
                                "current_bytes": curr,
                                "total_bytes": total,
                                "percentage": (curr / total) * 100,
                            }
                        )
                    ),
                )
            else:
                # Assume it's a URL
                video_metadata = await self.client.upload_video(
                    url=workflow_input.video_source,
                    metadata=workflow_input.metadata,
                )

            video_id = video_metadata.video_id

            await ctx.send_message(
                {
                    "status": "indexed",
                    "message": f"Video indexed successfully: {video_id}",
                    "video_id": video_id,
                    "duration": video_metadata.duration,
                    "resolution": f"{video_metadata.width}x{video_metadata.height}",
                }
            )

            # Process requested operations
            results = {}

            for operation in workflow_input.operations:
                await ctx.send_message(
                    {
                        "status": "processing",
                        "operation": operation.value,
                        "message": f"Performing {operation.value} operation...",
                    }
                )

                if operation == VideoOperationType.SUMMARIZE:
                    summary = await self.client.summarize_video(
                        video_id,
                        summary_type="summary",
                        temperature=workflow_input.options.get("temperature", 0.2),
                    )
                    results["summary"] = summary.dict() if hasattr(summary, "dict") else summary

                elif operation == VideoOperationType.CHAPTERS:
                    chapters = await self.client.summarize_video(
                        video_id,
                        summary_type="chapter",
                    )
                    results["chapters"] = chapters.dict() if hasattr(chapters, "dict") else chapters

                elif operation == VideoOperationType.HIGHLIGHTS:
                    highlights = await self.client.summarize_video(
                        video_id,
                        summary_type="highlight",
                    )
                    results["highlights"] = (
                        highlights.dict() if hasattr(highlights, "dict") else highlights
                    )

                elif operation == VideoOperationType.CHAT:
                    # For chat, we just prepare the video for Q&A
                    results["chat_ready"] = True
                    results["message"] = "Video is ready for interactive Q&A"

                elif operation == VideoOperationType.SEARCH:
                    # For search, perform a sample search if query provided
                    query = workflow_input.options.get("search_query")
                    if query:
                        search_results = await self.client.search_moments(video_id, query)
                        results["search"] = [r.dict() for r in search_results]

            # Calculate processing time
            processing_time = asyncio.get_event_loop().time() - start_time

            # Send final output
            output = WorkflowOutput(
                video_id=video_id,
                status="complete",
                results=results,
                metadata={
                    "source": workflow_input.video_source,
                    "operations_performed": [op.value for op in workflow_input.operations],
                    **workflow_input.metadata,
                },
                processing_time=processing_time,
            )

            await ctx.send_message(output.dict())

        except Exception as e:
            await ctx.send_message(
                {
                    "status": "error",
                    "error": str(e),
                    "message": f"Video processing failed: {e}",
                }
            )
            raise


class BatchVideoExecutor(Executor):
    """Workflow executor for batch video processing.

    Processes multiple videos in parallel with configurable concurrency.

    Example:
        ```python
        from agent_framework._workflows import Workflow
        from agent_framework_twelvelabs import BatchVideoExecutor

        executor = BatchVideoExecutor(max_concurrent=5)

        result = await workflow.run({
            "videos": [
                {"source": "video1.mp4", "operations": ["summarize"]},
                {"source": "video2.mp4", "operations": ["chapters"]},
            ]
        })
        ```

    """

    def __init__(
        self,
        client: Optional[TwelveLabsClient] = None,
        max_concurrent: int = 3,
    ):
        """Initialize batch video executor.

        Args:
            client: Twelve Labs client instance
            max_concurrent: Maximum videos to process concurrently

        """
        super().__init__()
        self.client = client or TwelveLabsClient()
        self.max_concurrent = max_concurrent
        self.video_executor = VideoExecutor(client)

    @handler
    async def batch_process(
        self,
        input: Dict[str, Any],
        ctx: WorkflowContext[Dict[str, Any]],
    ) -> None:
        """Process multiple videos in batch.

        Args:
            input: Dictionary containing:
                - videos: List of video configurations, each with:
                    - source: Video file path or URL
                    - operations: List of operations
                    - metadata: Optional metadata
            ctx: Workflow context

        Processes videos with controlled concurrency and reports progress.

        """
        videos = input.get("videos", [])
        total = len(videos)

        await ctx.send_message(
            {
                "status": "batch_starting",
                "total_videos": total,
                "max_concurrent": self.max_concurrent,
            }
        )

        # Process with concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results = {"successful": 0, "failed": 0, "videos": []}

        async def process_single(idx: int, video_config: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                await ctx.send_message(
                    {
                        "status": "processing_video",
                        "current": idx + 1,
                        "total": total,
                        "video": video_config.get("source"),
                    }
                )

                try:
                    # Create a sub-context for this video
                    video_results = []

                    async def capture_message(msg):
                        video_results.append(msg)

                    # Process video
                    sub_ctx = type(
                        "SubContext",
                        (),
                        {"send_message": capture_message},
                    )()

                    await self.video_executor.process_video(
                        {
                            "video_source": video_config.get("source"),
                            "operations": video_config.get("operations", ["summarize"]),
                            "metadata": video_config.get("metadata", {}),
                        },
                        sub_ctx,
                    )

                    # Get final result
                    final_result = video_results[-1] if video_results else {}

                    return {
                        "status": "success",
                        "index": idx,
                        "source": video_config.get("source"),
                        **final_result,
                    }

                except Exception as e:
                    return {
                        "status": "failed",
                        "index": idx,
                        "source": video_config.get("source"),
                        "error": str(e),
                    }

        # Process all videos
        tasks = [process_single(i, video) for i, video in enumerate(videos)]
        batch_results = await asyncio.gather(*tasks, return_exceptions=False)

        # Aggregate results
        for result in batch_results:
            if result["status"] == "success":
                results["successful"] += 1
            else:
                results["failed"] += 1
            results["videos"].append(result)

        # Send final batch results
        await ctx.send_message(
            {
                "status": "batch_complete",
                "total": total,
                "successful": results["successful"],
                "failed": results["failed"],
                "results": results["videos"],
            }
        )
