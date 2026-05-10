# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from unittest.mock import AsyncMock

from agent_framework_azure_contentunderstanding._models import (
    DocumentEntry,
    DocumentStatus,
    FileSearchConfig,
)


class TestDocumentEntry:
    def test_construction(self) -> None:
        entry: DocumentEntry = {
            "status": DocumentStatus.READY,
            "filename": "invoice.pdf",
            "media_type": "application/pdf",
            "analyzer_id": "prebuilt-documentSearch",
            "analyzed_at": "2026-01-01T00:00:00+00:00",
            "analysis_duration_s": 1.23,
            "upload_duration_s": None,
            "result": {"markdown": "# Title"},
            "error": None,
        }
        assert entry["status"] == DocumentStatus.READY
        assert entry["filename"] == "invoice.pdf"
        assert entry["analyzer_id"] == "prebuilt-documentSearch"
        assert entry["analysis_duration_s"] == 1.23
        assert entry["upload_duration_s"] is None

    def test_failed_entry(self) -> None:
        entry: DocumentEntry = {
            "status": DocumentStatus.FAILED,
            "filename": "bad.pdf",
            "media_type": "application/pdf",
            "analyzer_id": "prebuilt-documentSearch",
            "analyzed_at": "2026-01-01T00:00:00+00:00",
            "analysis_duration_s": 0.5,
            "upload_duration_s": None,
            "result": None,
            "error": "Service unavailable",
        }
        assert entry["status"] == DocumentStatus.FAILED
        assert entry["error"] == "Service unavailable"
        assert entry["result"] is None


class TestFileSearchConfig:
    def test_required_fields(self) -> None:
        backend = AsyncMock()
        tool = {"type": "file_search", "vector_store_ids": ["vs_123"]}
        config = FileSearchConfig(backend=backend, vector_store_id="vs_123", file_search_tool=tool)
        assert config.backend is backend
        assert config.vector_store_id == "vs_123"
        assert config.file_search_tool is tool

    def test_from_openai_factory(self) -> None:
        from agent_framework_azure_contentunderstanding._file_search import OpenAIFileSearchBackend

        client = AsyncMock()
        tool = {"type": "file_search", "vector_store_ids": ["vs_abc"]}
        config = FileSearchConfig.from_openai(client, vector_store_id="vs_abc", file_search_tool=tool)
        assert isinstance(config.backend, OpenAIFileSearchBackend)
        assert config.vector_store_id == "vs_abc"
        assert config.file_search_tool is tool
