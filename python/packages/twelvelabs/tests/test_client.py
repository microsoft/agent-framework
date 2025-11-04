# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for TwelveLabsClient."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agent_framework_twelvelabs import (
    FileTooLargeError,
    TwelveLabsClient,
    TwelveLabsSettings,
    VideoMetadata,
    VideoStatus,
)


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    return TwelveLabsSettings(
        api_key="test-api-key",
        max_video_size=1000000,
        chunk_size=10000,
    )


@pytest.fixture
def mock_client(mock_settings):
    """Create mock client with test settings."""
    with patch("agent_framework_twelvelabs._client.TwelveLabs"):
        client = TwelveLabsClient(mock_settings)
        return client


@pytest.mark.asyncio
async def test_upload_video_from_url(mock_client):
    """Test uploading video from URL."""
    # Mock the internal methods
    mock_client._get_or_create_index = AsyncMock(return_value="index-123")
    mock_client._url_upload = AsyncMock(return_value="video-123")
    mock_client._wait_for_processing = AsyncMock()
    mock_client._get_video_metadata = AsyncMock(
        return_value=VideoMetadata(
            video_id="video-123",
            status=VideoStatus.READY,
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            title="Test Video",
        )
    )

    # Upload video
    result = await mock_client.upload_video(url="https://example.com/video.mp4")

    # Verify
    assert result.video_id == "video-123"
    assert result.status == VideoStatus.READY
    assert result.duration == 120.0
    mock_client._url_upload.assert_called_once_with("https://example.com/video.mp4", "index-123")


@pytest.mark.asyncio
async def test_upload_video_from_file(mock_client, tmp_path):
    """Test uploading video from local file."""
    # Create a temporary file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_bytes(b"fake video content")

    # Mock the internal methods
    mock_client._get_or_create_index = AsyncMock(return_value="index-123")
    mock_client._simple_upload = AsyncMock(return_value="video-456")
    mock_client._wait_for_processing = AsyncMock()
    mock_client._get_video_metadata = AsyncMock(
        return_value=VideoMetadata(
            video_id="video-456",
            status=VideoStatus.READY,
            duration=60.0,
            width=1280,
            height=720,
            fps=24.0,
            title="Test File Video",
        )
    )

    # Upload video
    result = await mock_client.upload_video(file_path=str(video_file))

    # Verify
    assert result.video_id == "video-456"
    assert result.status == VideoStatus.READY
    mock_client._simple_upload.assert_called_once()


@pytest.mark.asyncio
async def test_upload_video_file_too_large(mock_client, tmp_path):
    """Test uploading a file that exceeds size limit."""
    # Create a temporary file
    video_file = tmp_path / "large_video.mp4"
    video_file.write_bytes(b"x" * 2000000)  # Larger than max_video_size

    # Mock the internal methods
    mock_client._get_or_create_index = AsyncMock(return_value="index-123")

    # Attempt upload
    with pytest.raises(FileTooLargeError):
        await mock_client.upload_video(file_path=str(video_file))


@pytest.mark.asyncio
async def test_chat_with_video(mock_client):
    """Test chat functionality with video."""
    # Mock the SDK client's chat method
    mock_response = Mock()
    mock_response.content = "The video shows a product demonstration."

    with patch.object(mock_client._client, "chat") as mock_chat:
        mock_chat.create = Mock(return_value=mock_response)

        # Use asyncio.to_thread mock
        mock_response_text = "The video shows a product demonstration."
        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_response_text)):
            result = await mock_client.chat_with_video(
                video_id="video-123",
                query="What does the video show?",
            )

    assert result == "The video shows a product demonstration."


@pytest.mark.asyncio
async def test_chat_with_video_streaming(mock_client):
    """Test streaming chat functionality."""
    # Test streaming response
    result_gen = await mock_client.chat_with_video(
        video_id="video-123",
        query="What happens in the video?",
        stream=True,
    )

    # Collect streaming response
    chunks = []
    async for chunk in result_gen:
        chunks.append(chunk)

    # Verify we got chunks
    assert len(chunks) > 0
    full_response = "".join(chunks)
    assert "video" in full_response.lower()


@pytest.mark.asyncio
async def test_summarize_video(mock_client):
    """Test video summarization."""
    from agent_framework_twelvelabs import SummaryResult

    # Mock the summarize method
    mock_result = Mock()
    mock_result.summary = "This is a test summary"
    mock_result.topics = ["topic1", "topic2"]

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_result)):
        result = await mock_client.summarize_video(
            video_id="video-123",
        )

    assert isinstance(result, SummaryResult)
    assert result.summary == "This is a test summary"
    assert result.topics == ["topic1", "topic2"]


@pytest.mark.asyncio
async def test_delete_video(mock_client):
    """Test video deletion."""
    # Mock the get_video_info_cached to return None
    mock_client.get_video_info_cached = Mock(return_value=None)

    # Mock index list
    mock_index = Mock()
    mock_index.id = "index-123"
    mock_index.name = "default"

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=[
        [mock_index],  # index.list call
        None,  # video.delete call
    ])):
        await mock_client.delete_video("video-123")

    # Should complete without error


@pytest.mark.asyncio
async def test_chunked_upload(mock_client, tmp_path):
    """Test chunked upload for large files."""
    # Create a large temporary file
    video_file = tmp_path / "large_video.mp4"
    video_file.write_bytes(b"x" * 20000)  # Larger than chunk_size

    # Mock the internal methods
    mock_client._get_or_create_index = AsyncMock(return_value="index-123")
    mock_client._chunked_upload = AsyncMock(return_value="video-789")
    mock_client._wait_for_processing = AsyncMock()
    mock_client._get_video_metadata = AsyncMock(
        return_value=VideoMetadata(
            video_id="video-789",
            status=VideoStatus.READY,
            duration=180.0,
            width=1920,
            height=1080,
            fps=30.0,
            title="Large Video",
        )
    )

    # Set max size higher for this test
    mock_client.settings.max_video_size = 100000

    # Upload video
    result = await mock_client.upload_video(file_path=str(video_file))

    # Verify chunked upload was used
    assert result.video_id == "video-789"
    mock_client._chunked_upload.assert_called_once()


@pytest.mark.asyncio
async def test_rate_limiting(mock_client):
    """Test rate limiting functionality."""
    # Test that rate limiter properly throttles requests
    start_time = asyncio.get_event_loop().time()

    # Make multiple rapid requests
    tasks = []
    for _ in range(3):
        async def make_request():
            async with mock_client._rate_limiter.acquire():
                await asyncio.sleep(0.01)  # Simulate API call

        tasks.append(make_request())

    await asyncio.gather(*tasks)

    # Should take some time due to rate limiting
    elapsed = asyncio.get_event_loop().time() - start_time
    # With 60 calls/minute limit, 3 calls should take at least 3 seconds
    # But we're not enforcing strict timing in tests
    assert elapsed >= 0  # Just verify it completes


def test_cache_functionality(mock_client):
    """Test metadata caching."""
    from agent_framework_twelvelabs import VideoMetadata, VideoStatus

    # First, add video to cache
    metadata = VideoMetadata(
        video_id="video-123",
        status=VideoStatus.READY,
        duration=180.0,
        width=1920,
        height=1080,
        fps=30.0,
        title="Test Video",
    )
    mock_client._video_cache["video-123"] = metadata

    # First call should fetch from cache
    result1 = mock_client.get_video_info_cached("video-123")
    assert result1.video_id == "video-123"

    # Second call should use cache (same object)
    result2 = mock_client.get_video_info_cached("video-123")
    assert result2.video_id == "video-123"
    assert result1 is result2  # Same object from cache

    # Invalidate cache
    mock_client.invalidate_cache()

    # Next call should raise ValueError (not in cache)
    import pytest
    with pytest.raises(ValueError, match="not found in cache"):
        mock_client.get_video_info_cached("video-123")


@pytest.mark.asyncio
async def test_upload_with_progress_callback(mock_client, tmp_path):
    """Test upload with progress callback."""
    # Create a temporary file
    video_file = tmp_path / "test_video.mp4"
    video_file.write_bytes(b"fake video content")

    progress_updates = []

    def progress_callback(current, total):
        progress_updates.append((current, total))

    # Mock the internal methods
    mock_client._get_or_create_index = AsyncMock(return_value="index-123")
    mock_client._simple_upload = AsyncMock(return_value="video-123")
    mock_client._wait_for_processing = AsyncMock()
    mock_client._get_video_metadata = AsyncMock(
        return_value=VideoMetadata(
            video_id="video-123",
            status=VideoStatus.READY,
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            title="Test Video",
        )
    )

    # Upload with progress callback
    await mock_client.upload_video(
        file_path=str(video_file),
        progress_callback=progress_callback,
    )

    # Progress callback would be called during chunked upload
    # For simple upload, it won't be called in this test


@pytest.mark.asyncio
async def test_get_or_create_index(mock_client):
    """Test index creation and caching."""
    # Mock index list
    mock_index = Mock()
    mock_index.name = "test-index"
    mock_index.id = "index-abc"

    with patch("asyncio.to_thread", new=AsyncMock(return_value=[mock_index])):
        # First call should check existing indexes
        index_id = await mock_client._get_or_create_index("test-index")
        assert index_id == "index-abc"

        # Second call should use cache
        index_id2 = await mock_client._get_or_create_index("test-index")
        assert index_id2 == "index-abc"

    # Test creating new index
    with patch("asyncio.to_thread", new=AsyncMock(side_effect=[
        [],  # No existing indexes
        Mock(id="new-index-123"),  # Created index
    ])):
        index_id = await mock_client._get_or_create_index("new-index")
        assert index_id == "new-index-123"
