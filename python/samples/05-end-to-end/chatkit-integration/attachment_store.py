# Copyright (c) Microsoft. All rights reserved.

"""File-based AttachmentStore implementation for ChatKit.

This module provides a simple AttachmentStore implementation that stores
uploaded files on the local filesystem. In production, you should use
cloud storage like S3, Azure Blob Storage, or Google Cloud Storage.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from chatkit.store import AttachmentStore
from chatkit.types import Attachment, AttachmentCreateParams, FileAttachment, ImageAttachment
from pydantic import AnyUrl

if TYPE_CHECKING:
    from store import SQLiteStore


class FileBasedAttachmentStore(AttachmentStore[dict[str, Any]]):
    """File-based AttachmentStore that stores files on local disk.

    This implementation stores uploaded files in a local directory and provides
    upload URLs that point to the FastAPI upload endpoint. It supports both
    image and file attachments.

    Features:
    - Stores files in a local uploads directory
    - Generates upload URLs for two-phase upload
    - Generates preview URLs for images
    - Proper cleanup on deletion

    Note: This is for demonstration purposes. In production, use cloud storage
    with signed URLs for better security and scalability.
    """

    def __init__(
        self,
        uploads_dir: str = "./uploads",
        base_url: str = "http://localhost:8001",
        data_store: "SQLiteStore | None" = None,
    ):
        """Initialize the file-based attachment store.

        Args:
            uploads_dir: Directory where uploaded files will be stored
            base_url: Base URL for generating upload and preview URLs
            data_store: Optional data store to persist attachment metadata
        """
        self.uploads_dir = Path(uploads_dir)
        self.base_url = base_url.rstrip("/")
        self.data_store = data_store

        # Create uploads directory if it doesn't exist
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def get_file_path(self, attachment_id: str) -> Path:
        """Get the filesystem path for an attachment."""
        return self.uploads_dir / attachment_id

    async def delete_attachment(self, attachment_id: str, context: dict[str, Any]) -> None:
        """Delete an attachment and its file from disk."""
        file_path = self.get_file_path(attachment_id)
        if file_path.exists():
            file_path.unlink()

    async def create_attachment(self, input: AttachmentCreateParams, context: dict[str, Any]) -> Attachment:
        """Create an attachment with upload URL for two-phase upload.

        This creates the attachment metadata and returns upload URLs that
        the client will use to POST the actual file bytes.
        """
        # Generate unique ID for this attachment
        attachment_id = self.generate_attachment_id(input.mime_type, context)

        # Generate upload URL that points to our FastAPI upload endpoint
        upload_url = f"{self.base_url}/upload/{attachment_id}"

        # Create appropriate attachment type based on MIME type
        if input.mime_type.startswith("image/"):
            # For images, also provide a preview URL
            preview_url = f"{self.base_url}/preview/{attachment_id}"

            attachment = ImageAttachment(
                id=attachment_id,
                type="image",
                mime_type=input.mime_type,
                name=input.name,
                upload_url=AnyUrl(upload_url),
                preview_url=AnyUrl(preview_url),
            )
        else:
            # For files, just provide upload URL
            attachment = FileAttachment(
                id=attachment_id,
                type="file",
                mime_type=input.mime_type,
                name=input.name,
                upload_url=AnyUrl(upload_url),
            )

        # Save attachment metadata to data store so it's available during upload
        if self.data_store is not None:
            await self.data_store.save_attachment(attachment, context)

        return attachment

    async def read_attachment_bytes(self, attachment_id: str) -> bytes:
        """Read the raw bytes of an uploaded attachment.

        This is used by the ThreadItemConverter to create base64-encoded
        content for sending to the Agent Framework.
        """
        file_path = self.get_file_path(attachment_id)
        if not file_path.exists():
            raise FileNotFoundError(f"Attachment {attachment_id} not found on disk")

        return file_path.read_bytes()
