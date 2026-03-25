# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from unittest.mock import AsyncMock

from agent_framework_azure_ai_contentunderstanding._models import (
    AnalysisSection,
    DocumentEntry,
    FileSearchConfig,
)


class TestAnalysisSection:
    def test_values(self) -> None:
        assert AnalysisSection.MARKDOWN == "markdown"
        assert AnalysisSection.FIELDS == "fields"
        assert AnalysisSection.FIELD_GROUNDING == "field_grounding"
        assert AnalysisSection.TABLES == "tables"
        assert AnalysisSection.PARAGRAPHS == "paragraphs"
        assert AnalysisSection.SECTIONS == "sections"

    def test_is_string(self) -> None:
        assert isinstance(AnalysisSection.MARKDOWN, str)
        assert isinstance(AnalysisSection.FIELDS, str)

    def test_members(self) -> None:
        assert len(AnalysisSection) == 6


class TestDocumentEntry:
    def test_construction(self) -> None:
        entry: DocumentEntry = {
            "status": "ready",
            "filename": "invoice.pdf",
            "media_type": "application/pdf",
            "analyzer_id": "prebuilt-documentSearch",
            "analyzed_at": "2026-01-01T00:00:00+00:00",
            "result": {"markdown": "# Title"},
            "error": None,
        }
        assert entry["status"] == "ready"
        assert entry["filename"] == "invoice.pdf"
        assert entry["analyzer_id"] == "prebuilt-documentSearch"

    def test_failed_entry(self) -> None:
        entry: DocumentEntry = {
            "status": "failed",
            "filename": "bad.pdf",
            "media_type": "application/pdf",
            "analyzer_id": "prebuilt-documentSearch",
            "analyzed_at": "2026-01-01T00:00:00+00:00",
            "result": None,
            "error": "Service unavailable",
        }
        assert entry["status"] == "failed"
        assert entry["error"] == "Service unavailable"
        assert entry["result"] is None


class TestFileSearchConfig:
    def test_defaults(self) -> None:
        client = AsyncMock()
        config = FileSearchConfig(openai_client=client)
        assert config.openai_client is client
        assert config.vector_store_name == "cu_extracted_docs"

    def test_custom_name(self) -> None:
        client = AsyncMock()
        config = FileSearchConfig(openai_client=client, vector_store_name="my_store")
        assert config.vector_store_name == "my_store"
