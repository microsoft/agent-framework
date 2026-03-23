# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from agent_framework_azure_ai_contentunderstanding._models import AnalysisSection, ContentLimits


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


class TestContentLimits:
    def test_defaults(self) -> None:
        limits = ContentLimits()
        assert limits.max_pages == 20
        assert limits.max_file_size_mb == 10
        assert limits.max_audio_duration_s == 300
        assert limits.max_video_duration_s == 120

    def test_custom_values(self) -> None:
        limits = ContentLimits(
            max_pages=50,
            max_file_size_mb=50,
            max_audio_duration_s=600,
            max_video_duration_s=300,
        )
        assert limits.max_pages == 50
        assert limits.max_file_size_mb == 50
        assert limits.max_audio_duration_s == 600
        assert limits.max_video_duration_s == 300
