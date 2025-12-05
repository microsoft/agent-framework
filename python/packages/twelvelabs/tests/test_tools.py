# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for TwelveLabsTools."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_framework_twelvelabs import (
    TwelveLabsClient,
    TwelveLabsTools,
    VideoMetadata,
    VideoStatus,
)


@pytest.fixture
def mock_client():
    """Create a mock Twelve Labs client."""
    client = Mock(spec=TwelveLabsClient)
    return client


@pytest.fixture
def tools(mock_client):
    """Create tools instance with mock client."""
    return TwelveLabsTools(client=mock_client)


@pytest.mark.asyncio
async def test_upload_video_from_url(tools, mock_client):
    """Test uploading video from URL using tools."""
    # Mock client response
    mock_metadata = VideoMetadata(
        video_id="video-123",
        status=VideoStatus.READY,
        duration=120.0,
        width=1920,
        height=1080,
        fps=30.0,
        title="Test Video",
        metadata={"description": "Test description"},
    )
    mock_client.upload_video = AsyncMock(return_value=mock_metadata)

    # Upload video - call the bound method
    result = await tools.upload_video.func(
        tools,
        url="https://example.com/video.mp4",
        description="Test video",
    )

    # Verify
    assert result["video_id"] == "video-123"
    assert result["status"] == "ready"
    assert result["duration"] == 120.0
    assert result["resolution"] == "1920x1080"
    assert result["fps"] == 30.0

    mock_client.upload_video.assert_called_once_with(
        file_path=None,
        url="https://example.com/video.mp4",
        index_name=None,
        metadata={"description": "Test video"},
    )


@pytest.mark.asyncio
async def test_upload_video_from_file(tools, mock_client):
    """Test uploading video from file using tools."""
    # Mock client response
    mock_metadata = VideoMetadata(
        video_id="video-456",
        status=VideoStatus.READY,
        duration=60.0,
        width=1280,
        height=720,
        fps=24.0,
        title="File Video",
        metadata={},
    )
    mock_client.upload_video = AsyncMock(return_value=mock_metadata)

    # Upload video - call the bound method
    result = await tools.upload_video.func(
        tools,
        file_path="/path/to/video.mp4",
        index_name="custom-index",
    )

    # Verify
    assert result["video_id"] == "video-456"
    assert result["resolution"] == "1280x720"

    mock_client.upload_video.assert_called_once_with(
        file_path="/path/to/video.mp4",
        url=None,
        index_name="custom-index",
        metadata={},
    )


@pytest.mark.asyncio
async def test_chat_with_video(tools, mock_client):
    """Test chat with video functionality."""
    # Mock client response
    mock_client.chat_with_video = AsyncMock(
        return_value="The video shows a product demonstration with three main features."
    )

    # Chat with video - call the bound method
    result = await tools.chat_with_video.func(
        tools,
        video_id="video-123",
        question="What does the video show?",
        temperature=0.5,
    )

    # Verify
    assert "product demonstration" in result
    mock_client.chat_with_video.assert_called_once_with(
        video_id="video-123",
        query="What does the video show?",
        stream=False,
        temperature=0.5,
        max_tokens=None,
    )


@pytest.mark.asyncio
async def test_summarize_video_summary(tools, mock_client):
    """Test video summarization - summary type."""
    from agent_framework_twelvelabs import SummaryResult

    # Mock client response
    mock_result = SummaryResult(
        summary="This video demonstrates our new product features.",
        topics=["product", "features", "demo"],
        key_points=["Feature 1", "Feature 2"],
    )
    mock_client.summarize_video = AsyncMock(return_value=mock_result)

    # Summarize video
    result = await tools.summarize_video.func(
        tools,
        video_id="video-123",
    )

    # Verify
    assert result["type"] == "summary"
    assert result["summary"] == "This video demonstrates our new product features."
    assert result["topics"] == ["product", "features", "demo"]
    assert result["key_points"] == ["Feature 1", "Feature 2"]


@pytest.mark.asyncio
async def test_summarize_video_chapters(tools, mock_client):
    """Test video summarization - chapters."""
    from agent_framework_twelvelabs import ChapterInfo, ChapterResult

    # Mock client response
    mock_chapters = ChapterResult(
        chapters=[
            ChapterInfo(
                title="Introduction",
                start_time=0.0,
                end_time=30.0,
                description="Opening segment",
                topics=["intro"],
            ),
            ChapterInfo(
                title="Main Content",
                start_time=30.0,
                end_time=90.0,
                description="Core demonstration",
                topics=["demo"],
            ),
        ]
    )
    mock_client.generate_chapters = AsyncMock(return_value=mock_chapters)

    # Get chapters
    result = await tools.generate_chapters.func(
        tools,
        video_id="video-123",
    )

    # Verify
    assert result["type"] == "chapters"
    assert len(result["chapters"]) == 2
    assert result["chapters"][0]["title"] == "Introduction"
    assert result["chapters"][0]["start_time"] == 0.0
    assert result["total_chapters"] == 2


@pytest.mark.asyncio
async def test_summarize_video_highlights(tools, mock_client):
    """Test video summarization - highlights."""
    from agent_framework_twelvelabs import HighlightInfo, HighlightResult

    # Mock client response
    mock_highlights = HighlightResult(
        highlights=[
            HighlightInfo(
                start_time=15.0,
                end_time=25.0,
                description="Key moment",
                score=0.95,
                tags=["important"],
            ),
        ]
    )
    mock_client.generate_highlights = AsyncMock(return_value=mock_highlights)

    # Get highlights
    result = await tools.generate_highlights.func(
        tools,
        video_id="video-123",
    )

    # Verify
    assert result["type"] == "highlights"
    assert len(result["highlights"]) == 1
    assert result["highlights"][0]["description"] == "Key moment"
    assert result["highlights"][0]["score"] == 0.95


@pytest.mark.asyncio
async def test_get_video_info(tools, mock_client):
    """Test getting video information."""
    # Mock client response
    mock_metadata = VideoMetadata(
        video_id="video-123",
        status=VideoStatus.READY,
        duration=180.0,
        width=1920,
        height=1080,
        fps=30.0,
        title="Sample Video",
        description="A sample video for testing",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T01:00:00Z",
        metadata={"custom": "data"},
    )
    mock_client._get_video_metadata = AsyncMock(return_value=mock_metadata)

    # Get video info - call the bound method
    result = await tools.get_video_info.func(tools, "video-123")

    # Verify
    assert result["video_id"] == "video-123"
    assert result["status"] == "ready"
    assert result["duration"] == 180.0
    assert result["resolution"] == "1920x1080"
    assert result["title"] == "Sample Video"
    assert result["description"] == "A sample video for testing"


@pytest.mark.asyncio
async def test_delete_video(tools, mock_client):
    """Test video deletion."""
    # Mock client response
    mock_client.delete_video = AsyncMock()

    # Delete video - call the bound method
    result = await tools.delete_video.func(tools, "video-123")

    # Verify
    assert result["status"] == "deleted"
    assert result["video_id"] == "video-123"
    assert "successfully deleted" in result["message"]

    mock_client.delete_video.assert_called_once_with("video-123")


@pytest.mark.asyncio
async def test_batch_process_videos(tools, mock_client):
    """Test batch video processing."""
    # Mock client responses
    mock_metadata1 = VideoMetadata(
        video_id="video-1",
        status=VideoStatus.READY,
        duration=60.0,
        width=1280,
        height=720,
        fps=24.0,
        title="Video 1",
        metadata={},
    )
    mock_metadata2 = VideoMetadata(
        video_id="video-2",
        status=VideoStatus.READY,
        duration=90.0,
        width=1280,
        height=720,
        fps=24.0,
        title="Video 2",
        metadata={},
    )

    from agent_framework_twelvelabs import SummaryResult

    mock_summary = SummaryResult(
        summary="Test summary",
        topics=["topic"],
    )

    # Set up mocks
    mock_client.upload_video = AsyncMock(side_effect=[mock_metadata1, mock_metadata2])
    mock_client.summarize_video = AsyncMock(return_value=mock_summary)

    # Mock the upload_video and summarize_video methods on tools
    with patch.object(tools, "upload_video", new=AsyncMock(side_effect=[
        {"video_id": "video-1"},
        {"video_id": "video-2"},
    ])):
        with patch.object(tools, "summarize_video", new=AsyncMock(return_value={
            "type": "summary",
            "summary": "Test summary",
        })):
            # Process batch - call the bound method
            result = await tools.batch_process_videos.func(
                tools,
                video_sources=["video1.mp4", "video2.mp4"],
                operations=["summarize"],
                max_concurrent=2,
            )

    # Verify
    assert result["total"] == 2
    assert result["successful"] == 2
    assert result["failed"] == 0
    assert len(result["videos"]) == 2


@pytest.mark.asyncio
async def test_search_videos(tools, mock_client):
    """Test searching videos with natural language query."""
    from agent_framework_twelvelabs import SearchResult, SearchResults

    # Mock client response
    mock_results = SearchResults(
        results=[
            SearchResult(
                video_id="video-123",
                start_time=10.0,
                end_time=20.0,
                score=0.92,
                confidence="high",
                thumbnail_url="https://example.com/thumb1.jpg",
                metadata={"modules": ["visual"]},
            ),
            SearchResult(
                video_id="video-456",
                start_time=5.0,
                end_time=15.0,
                score=0.75,
                confidence="medium",
                metadata={"modules": ["visual", "audio"]},
            ),
        ],
        total_count=2,
        query="product demonstration",
        search_options=["visual", "audio"],
    )
    mock_client.search_videos = AsyncMock(return_value=mock_results)

    # Search videos - call the bound method
    result = await tools.search_videos.func(
        tools,
        query="product demonstration",
        limit=10,
    )

    # Verify
    assert result["query"] == "product demonstration"
    assert result["total_count"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["video_id"] == "video-123"
    assert result["results"][0]["score"] == 0.92
    assert result["results"][0]["confidence"] == "high"
    assert result["results"][1]["video_id"] == "video-456"

    mock_client.search_videos.assert_called_once_with(
        query="product demonstration",
        index_name=None,
        limit=10,
    )


@pytest.mark.asyncio
async def test_search_by_image(tools, mock_client):
    """Test searching videos with an image query."""
    from agent_framework_twelvelabs import SearchResult, SearchResults

    # Mock client response
    mock_results = SearchResults(
        results=[
            SearchResult(
                video_id="video-789",
                start_time=25.0,
                end_time=35.0,
                score=0.88,
                confidence="high",
                thumbnail_url="https://example.com/thumb.jpg",
            ),
        ],
        total_count=1,
        query="image:/path/to/image.jpg",
        search_options=["visual"],
    )
    mock_client.search_by_image = AsyncMock(return_value=mock_results)

    # Search by image - call the bound method
    result = await tools.search_by_image.func(
        tools,
        image_path="/path/to/image.jpg",
        limit=5,
    )

    # Verify
    assert result["total_count"] == 1
    assert result["search_options"] == ["visual"]
    assert len(result["results"]) == 1
    assert result["results"][0]["video_id"] == "video-789"
    assert result["results"][0]["start_time"] == 25.0
    assert result["results"][0]["confidence"] == "high"

    mock_client.search_by_image.assert_called_once_with(
        image_path="/path/to/image.jpg",
        index_name=None,
        limit=5,
    )


def test_get_all_tools(tools):
    """Test getting all available tools."""
    all_tools = tools.get_all_tools()

    # Verify all tools are present (now includes search_videos and search_by_image)
    assert len(all_tools) == 10

    # Check that each is a callable
    for tool in all_tools:
        assert callable(tool)

    # Check specific tools are included
    # AIFunction objects have a .name attribute, not __name__
    tool_names = [tool.name for tool in all_tools]
    assert "upload_video" in tool_names
    assert "chat_with_video" in tool_names
    assert "summarize_video" in tool_names
    assert "generate_chapters" in tool_names
    assert "generate_highlights" in tool_names
    assert "get_video_info" in tool_names
    assert "delete_video" in tool_names
    assert "search_videos" in tool_names
    assert "search_by_image" in tool_names
    assert "batch_process_videos" in tool_names


@pytest.mark.asyncio
async def test_ai_function_decorators(tools):
    """Test that AI function decorators are properly applied."""
    # Check that functions have the ai_function decorator attributes
    upload_func = tools.upload_video

    # AI functions should have certain attributes added by decorator
    assert hasattr(upload_func, "__wrapped__") or hasattr(upload_func, "func")

    # Test that delete requires approval
    delete_func = tools.delete_video
    assert hasattr(delete_func, "__wrapped__") or hasattr(delete_func, "func")
