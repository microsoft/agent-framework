# Copyright (c) Microsoft. All rights reserved.

"""Type definitions for Twelve Labs integration."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VideoStatus(str, Enum):
    """Video processing status."""

    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class VideoOperationType(str, Enum):
    """Types of video operations."""

    UPLOAD = "upload"
    SUMMARIZE = "summarize"
    CHAPTERS = "chapters"
    HIGHLIGHTS = "highlights"
    CHAT = "chat"
    SEARCH = "search"
    DELETE = "delete"


class VideoMetadata(BaseModel):
    """Metadata for an indexed video."""

    video_id: str = Field(..., description="Unique video identifier")
    status: VideoStatus = Field(..., description="Current processing status")
    duration: float = Field(..., description="Video duration in seconds")
    width: int = Field(..., description="Video width in pixels")
    height: int = Field(..., description="Video height in pixels")
    fps: float = Field(..., description="Frames per second")
    title: Optional[str] = Field(None, description="Video title")
    description: Optional[str] = Field(None, description="Video description")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata")


class SummaryResult(BaseModel):
    """Result from video summarization."""

    summary: str = Field(..., description="Generated summary text")
    topics: List[str] = Field(default_factory=list, description="Main topics covered")
    sentiment: Optional[str] = Field(None, description="Overall sentiment")
    key_points: List[str] = Field(default_factory=list, description="Key points extracted")


class ChapterInfo(BaseModel):
    """Information about a video chapter."""

    title: str = Field(..., description="Chapter title")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    description: Optional[str] = Field(None, description="Chapter description")
    topics: List[str] = Field(default_factory=list, description="Topics covered")


class ChapterResult(BaseModel):
    """Result from chapter generation."""

    chapters: List[ChapterInfo] = Field(..., description="List of generated chapters")
    total_chapters: int = Field(0, description="Total number of chapters")


class HighlightInfo(BaseModel):
    """Information about a video highlight."""

    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    description: str = Field(..., description="Highlight description")
    score: float = Field(..., description="Relevance score (0-1)")
    tags: List[str] = Field(default_factory=list, description="Associated tags")


class HighlightResult(BaseModel):
    """Result from highlight extraction."""

    highlights: List[HighlightInfo] = Field(..., description="List of highlights")
    total_highlights: int = Field(0, description="Total number of highlights")



class VideoUploadProgress(BaseModel):
    """Progress information for video upload."""

    video_id: Optional[str] = Field(None, description="Video ID if available")
    current_bytes: int = Field(..., description="Bytes uploaded")
    total_bytes: int = Field(..., description="Total file size")
    percentage: float = Field(..., description="Upload percentage (0-100)")
    estimated_time_remaining: Optional[float] = Field(
        None, description="Estimated seconds remaining"
    )
    status: str = Field(..., description="Current status message")


class BatchProcessingRequest(BaseModel):
    """Request for batch video processing."""

    videos: List[Dict[str, Any]] = Field(..., description="List of videos to process")
    operations: List[VideoOperationType] = Field(..., description="Operations to perform")
    parallel: bool = Field(True, description="Process videos in parallel")
    max_concurrent: int = Field(5, description="Maximum concurrent processing")


class BatchProcessingResult(BaseModel):
    """Result from batch video processing."""

    total_videos: int = Field(..., description="Total videos processed")
    successful: int = Field(..., description="Successfully processed count")
    failed: int = Field(..., description="Failed processing count")
    results: List[Dict[str, Any]] = Field(..., description="Individual results")
    errors: List[Dict[str, str]] = Field(default_factory=list, description="Error details")


class WorkflowInput(BaseModel):
    """Input for video workflow execution."""

    video_source: str = Field(..., description="Video file path or URL")
    operations: List[VideoOperationType] = Field(
        default_factory=lambda: [VideoOperationType.SUMMARIZE],
        description="Operations to perform",
    )
    options: Dict[str, Any] = Field(default_factory=dict, description="Operation options")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata")


class WorkflowOutput(BaseModel):
    """Output from video workflow execution."""

    video_id: str = Field(..., description="Processed video ID")
    status: str = Field(..., description="Processing status")
    results: Dict[str, Any] = Field(..., description="Operation results")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Output metadata")
    processing_time: float = Field(..., description="Total processing time in seconds")


class VideoIndex(BaseModel):
    """Information about a video index."""

    index_id: str = Field(..., description="Index identifier")
    index_name: str = Field(..., description="Index name")
    video_count: int = Field(..., description="Number of videos in index")
    created_at: str = Field(..., description="Creation timestamp")
    engines: List[str] = Field(..., description="Enabled engines")
    status: str = Field(..., description="Index status")
