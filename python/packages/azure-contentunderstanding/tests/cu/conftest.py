# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.ai.contentunderstanding.models import AnalysisResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text())  # type: ignore[no-any-return]


@pytest.fixture
def pdf_fixture_raw() -> dict[str, Any]:
    return _load_fixture("analyze_pdf_result.json")


@pytest.fixture
def pdf_analysis_result(pdf_fixture_raw: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(pdf_fixture_raw)


@pytest.fixture
def audio_fixture_raw() -> dict[str, Any]:
    return _load_fixture("analyze_audio_result.json")


@pytest.fixture
def audio_analysis_result(audio_fixture_raw: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(audio_fixture_raw)


@pytest.fixture
def invoice_fixture_raw() -> dict[str, Any]:
    return _load_fixture("analyze_invoice_result.json")


@pytest.fixture
def invoice_analysis_result(invoice_fixture_raw: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(invoice_fixture_raw)


@pytest.fixture
def video_fixture_raw() -> dict[str, Any]:
    return _load_fixture("analyze_video_result.json")


@pytest.fixture
def video_analysis_result(video_fixture_raw: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(video_fixture_raw)


@pytest.fixture
def image_fixture_raw() -> dict[str, Any]:
    return _load_fixture("analyze_image_result.json")


@pytest.fixture
def image_analysis_result(image_fixture_raw: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(image_fixture_raw)


@pytest.fixture
def mock_cu_client() -> AsyncMock:
    """Create a mock ContentUnderstandingClient."""
    client = AsyncMock()
    client.close = AsyncMock()
    return client


def make_mock_poller(result: AnalysisResult) -> AsyncMock:
    """Create a mock poller that returns the given result immediately."""
    poller = AsyncMock()
    poller.result = AsyncMock(return_value=result)
    poller.continuation_token = MagicMock(return_value="mock_continuation_token")
    poller.done = MagicMock(return_value=True)
    return poller


def make_slow_poller(result: AnalysisResult, delay: float = 10.0) -> MagicMock:
    """Create a mock poller that simulates a timeout then eventually returns."""
    poller = MagicMock()

    async def slow_result() -> AnalysisResult:
        await asyncio.sleep(delay)
        return result

    poller.result = slow_result
    poller.continuation_token = MagicMock(return_value="mock_slow_continuation_token")
    poller.done = MagicMock(return_value=False)
    return poller


def make_failing_poller(error: Exception) -> AsyncMock:
    """Create a mock poller that raises an exception."""
    poller = AsyncMock()
    poller.result = AsyncMock(side_effect=error)
    return poller
