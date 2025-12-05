# Copyright (c) Microsoft. All rights reserved.

"""AI function tools for Twelve Labs video operations."""

from typing import Any, Dict, List, Optional

from agent_framework import ai_function

from ._client import TwelveLabsClient
from ._types import (
    ChapterResult,
    HighlightResult,
    SearchResults,
    SummaryResult,
)


class TwelveLabsTools:
    """Collection of AI functions for video processing with Twelve Labs."""

    def __init__(self, client: Optional[TwelveLabsClient] = None):
        """Initialize tools with Twelve Labs client.

        Args:
            client: Twelve Labs client instance. If not provided, creates default client.

        """
        self.client = client or TwelveLabsClient()

    @ai_function(
        description="Upload and index a video for analysis",
        name="upload_video",
    )
    async def upload_video(
        self,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        description: Optional[str] = None,
        index_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload a video from local file or URL for processing.

        Args:
            file_path: Path to local video file
            url: URL of video to process
            description: Optional description of video content
            index_name: Name of index to use (defaults to 'default')

        Returns:
            Dictionary with video_id, status, and metadata

        Example:
            ```python
            result = await tools.upload_video(
                url="https://example.com/video.mp4",
                description="Product demo video"
            )
            print(f"Video uploaded: {result['video_id']}")
            ```

        """
        metadata_dict = {"description": description} if description else {}

        video_metadata = await self.client.upload_video(
            file_path=file_path,
            url=url,
            index_name=index_name,
            metadata=metadata_dict,
        )

        return {
            "video_id": video_metadata.video_id,
            "status": video_metadata.status.value,
            "duration": video_metadata.duration,
            "resolution": f"{video_metadata.width}x{video_metadata.height}",
            "fps": video_metadata.fps,
            "title": video_metadata.title,
            "metadata": video_metadata.metadata,
        }

    @ai_function(
        description="Ask questions about video content and get answers",
        name="chat_with_video",
    )
    async def chat_with_video(
        self,
        video_id: str,
        question: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Ask questions about a video's content and receive detailed answers.

        Args:
            video_id: ID of the indexed video
            question: Question about the video content
            temperature: Response temperature (0-1, default 0.7)
            max_tokens: Maximum tokens in response

        Returns:
            Answer based on video analysis

        Example:
            ```python
            answer = await tools.chat_with_video(
                video_id="abc123",
                question="What products are shown in the video?"
            )
            print(answer)
            ```

        """
        response = await self.client.chat_with_video(
            video_id=video_id,
            query=question,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response

    @ai_function(
        description="Generate a comprehensive summary of a video",
        name="summarize_video",
    )
    async def summarize_video(
        self,
        video_id: str,
        custom_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Generate a summary of a video.

        Args:
            video_id: ID of the indexed video
            custom_prompt: Optional custom prompt for generation
            temperature: Generation temperature (0-1, default .2)

        Returns:
            Summary with key points and topics

        Example:
            ```python
            summary = await tools.summarize_video(video_id="abc123")
            print(summary['summary'])
            ```

        """
        result = await self.client.summarize_video(
            video_id=video_id,
            prompt=custom_prompt,
            temperature=temperature,
        )

        if isinstance(result, SummaryResult):
            return {
                "type": "summary",
                "summary": result.summary,
                "topics": result.topics,
                "key_points": result.key_points,
            }
        return {"type": "error", "data": str(result)}

    @ai_function(
        description="Generate chapter markers with timestamps for a video",
        name="generate_chapters",
    )
    async def generate_chapters(
        self,
        video_id: str,
        custom_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Generate chapter markers for a video.

        Args:
            video_id: ID of the indexed video
            custom_prompt: Optional custom prompt for generation
            temperature: Generation temperature (0-1, default .2)

        Returns:
            List of chapters with titles, timestamps, and descriptions

        Example:
            ```python
            chapters = await tools.generate_chapters(video_id="abc123")
            for ch in chapters['chapters']:
                print(f"{ch['title']}: {ch['start_time']}-{ch['end_time']}")
            ```

        """
        result = await self.client.generate_chapters(
            video_id=video_id,
            prompt=custom_prompt,
            temperature=temperature,
        )

        if isinstance(result, ChapterResult):
            return {
                "type": "chapters",
                "chapters": [
                    {
                        "title": ch.title,
                        "start_time": ch.start_time,
                        "end_time": ch.end_time,
                        "description": ch.description,
                        "topics": ch.topics,
                    }
                    for ch in result.chapters
                ],
                "total_chapters": len(result.chapters),
            }
        return {"type": "error", "data": str(result)}

    @ai_function(
        description="Extract key highlights and important moments from a video",
        name="generate_highlights",
    )
    async def generate_highlights(
        self,
        video_id: str,
        custom_prompt: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Generate highlights for a video.

        Args:
            video_id: ID of the indexed video
            custom_prompt: Optional custom prompt for generation
            temperature: Generation temperature (0-1, default .2)

        Returns:
            List of highlights with timestamps and descriptions

        Example:
            ```python
            highlights = await tools.generate_highlights(video_id="abc123")
            for h in highlights['highlights']:
                print(f"{h['start_time']}: {h['description']}")
            ```

        """
        result = await self.client.generate_highlights(
            video_id=video_id,
            prompt=custom_prompt,
            temperature=temperature,
        )

        if isinstance(result, HighlightResult):
            return {
                "type": "highlights",
                "highlights": [
                    {
                        "start_time": hl.start_time,
                        "end_time": hl.end_time,
                        "description": hl.description,
                        "score": hl.score,
                        "tags": hl.tags,
                    }
                    for hl in result.highlights
                ],
                "total_highlights": len(result.highlights),
            }
        return {"type": "error", "data": str(result)}


    @ai_function(
        description="Get metadata and information about an indexed video",
        name="get_video_info",
    )
    async def get_video_info(self, video_id: str) -> Dict[str, Any]:
        """Get metadata and information about an indexed video.

        Args:
            video_id: ID of the video

        Returns:
            Video metadata including duration, resolution, status

        Example:
            ```python
            info = await tools.get_video_info("abc123")
            print(f"Duration: {info['duration']} seconds")
            print(f"Resolution: {info['resolution']}")
            ```

        """
        metadata = await self.client._get_video_metadata(video_id)

        return {
            "video_id": metadata.video_id,
            "status": metadata.status.value,
            "duration": metadata.duration,
            "resolution": f"{metadata.width}x{metadata.height}",
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "title": metadata.title,
            "description": metadata.description,
            "created_at": metadata.created_at,
            "updated_at": metadata.updated_at,
            "metadata": metadata.metadata,
        }

    @ai_function(
        description="Delete an indexed video from the system",
        name="delete_video",
        approval_mode="always_require",  # Requires approval for destructive action
    )
    async def delete_video(self, video_id: str) -> Dict[str, str]:
        """Delete an indexed video from the system.

        Args:
            video_id: ID of the video to delete

        Returns:
            Confirmation of deletion

        Example:
            ```python
            result = await tools.delete_video("abc123")
            print(result['message'])
            ```

        """
        await self.client.delete_video(video_id)

        return {
            "status": "deleted",
            "video_id": video_id,
            "message": f"Video {video_id} has been successfully deleted",
        }

    @ai_function(
        description="Search across indexed videos using natural language to find specific moments",
        name="search_videos",
    )
    async def search_videos(
        self,
        query: str,
        index_name: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search videos using a natural language query.

        Uses Marengo 3.0 embeddings for semantic video search across all indexed content.

        Args:
            query: Natural language search query (e.g., "person walking in the park")
            index_name: Name of index to search (defaults to 'default')
            limit: Maximum number of results to return (default 10)

        Returns:
            Dictionary with search results including timestamps and scores

        Example:
            ```python
            results = await tools.search_videos(
                query="product demonstration",
                limit=5
            )
            for r in results['results']:
                print(f"Video {r['video_id']}: {r['start_time']}-{r['end_time']}s (score: {r['score']})")
            ```

        """
        search_results = await self.client.search_videos(
            query=query,
            index_name=index_name,
            limit=limit,
        )

        return {
            "query": search_results.query,
            "total_count": search_results.total_count,
            "search_options": search_results.search_options,
            "results": [
                {
                    "video_id": r.video_id,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "score": r.score,
                    "confidence": r.confidence,
                    "thumbnail_url": r.thumbnail_url,
                    "metadata": r.metadata,
                }
                for r in search_results.results
            ],
        }

    @ai_function(
        description="Search videos using an image to find visually similar moments",
        name="search_by_image",
    )
    async def search_by_image(
        self,
        image_path: str,
        index_name: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search videos using an image to find visually similar moments.

        Uses Marengo 3.0 visual embeddings for image-to-video similarity search.

        Args:
            image_path: Path to the query image file
            index_name: Name of index to search (defaults to 'default')
            limit: Maximum number of results to return (default 10)

        Returns:
            Dictionary with search results including timestamps and scores

        Example:
            ```python
            results = await tools.search_by_image(
                image_path="product_screenshot.jpg",
                limit=5
            )
            for r in results['results']:
                print(f"Found similar content in video {r['video_id']} at {r['start_time']}s")
            ```

        """
        search_results = await self.client.search_by_image(
            image_path=image_path,
            index_name=index_name,
            limit=limit,
        )

        return {
            "query": search_results.query,
            "total_count": search_results.total_count,
            "search_options": search_results.search_options,
            "results": [
                {
                    "video_id": r.video_id,
                    "start_time": r.start_time,
                    "end_time": r.end_time,
                    "score": r.score,
                    "confidence": r.confidence,
                    "thumbnail_url": r.thumbnail_url,
                }
                for r in search_results.results
            ],
        }

    @ai_function(
        description="Process multiple videos in batch",
        name="batch_process_videos",
    )
    async def batch_process_videos(
        self,
        video_sources: List[str],
        operations: List[str],
        max_concurrent: int = 3,
    ) -> Dict[str, Any]:
        """Process multiple videos in batch with specified operations.

        Args:
            video_sources: List of video file paths or URLs
            operations: List of operations to perform ('summarize', 'chapters', 'highlights')
            max_concurrent: Maximum concurrent processing (default 3)

        Returns:
            Batch processing results

        Example:
            ```python
            results = await tools.batch_process_videos(
                video_sources=["video1.mp4", "video2.mp4"],
                operations=["summarize", "chapters"]
            )
            print(f"Processed {results['successful']} videos successfully")
            ```

        """
        import asyncio

        results = {
            "total": len(video_sources),
            "successful": 0,
            "failed": 0,
            "videos": [],
        }

        # Process videos with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_single(source: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    # Upload video
                    if source.startswith("http"):
                        upload_result = await self.upload_video(url=source)
                    else:
                        upload_result = await self.upload_video(file_path=source)

                    video_id = upload_result["video_id"]
                    video_results = {"source": source, "video_id": video_id, "operations": {}}

                    # Perform operations
                    for op in operations:
                        if op == "summarize":
                            video_results["operations"]["summary"] = await self.summarize_video(
                                video_id
                            )
                        elif op == "chapters":
                            video_results["operations"]["chapters"] = await self.generate_chapters(
                                video_id
                            )
                        elif op == "highlights":
                            video_results["operations"]["highlights"] = (
                                await self.generate_highlights(video_id)
                            )

                    return {"status": "success", **video_results}

                except Exception as e:
                    return {"status": "failed", "source": source, "error": str(e)}

        # Process all videos
        tasks = [process_single(source) for source in video_sources]
        batch_results = await asyncio.gather(*tasks, return_exceptions=False)

        for result in batch_results:
            if result["status"] == "success":
                results["successful"] += 1
            else:
                results["failed"] += 1
            results["videos"].append(result)

        return results

    def get_all_tools(self) -> List:
        """Get all available tool functions.

        Returns:
            List of all tool functions that can be used with an agent.

        """
        from functools import partial

        # The ai_function decorator doesn't preserve self binding properly,
        # so we need to create new AIFunction instances with bound methods
        tools = []

        # Get the decorated methods and bind them properly
        for method_name in ['upload_video', 'chat_with_video', 'summarize_video',
                           'generate_chapters', 'generate_highlights',
                           'get_video_info', 'delete_video', 'search_videos',
                           'search_by_image', 'batch_process_videos']:
            method = getattr(self, method_name)
            # The method is already an AIFunction, we need to update its func
            if hasattr(method, 'func'):
                # Create a new AIFunction with the bound method
                from agent_framework import AIFunction
                bound_func = partial(method.func, self)
                tool = AIFunction(
                    name=method.name,
                    description=method.description,
                    func=bound_func,
                    approval_mode=method.approval_mode,
                    additional_properties=method.additional_properties,
                    input_model=method.input_model  # Include the input model
                )
                tools.append(tool)
            else:
                tools.append(method)

        return tools
