# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Reliable Streaming Sample

Tests the reliable streaming sample using Redis Streams for persistent message delivery.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite or Azure Storage account configured
- Redis running (docker run -d --name redis -p 6379:6379 redis:latest)

Usage:
    uv run pytest packages/azurefunctions/tests/integration_tests/test_03_reliable_streaming.py -v
"""

import pytest
import requests

from .testutils import (
    TIMEOUT,
    SampleTestHelper,
    skip_if_azure_functions_integration_tests_disabled,
)

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("03_reliable_streaming"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


class TestSampleReliableStreaming:
    """Tests for 03_reliable_streaming sample."""

    @pytest.fixture(autouse=True)
    def _set_base_url(self, base_url: str) -> None:
        """Provide the base URL for each test."""
        self.base_url = base_url
        self.agent_url = f"{base_url}/api/agents/TravelPlanner"
        self.stream_url = f"{base_url}/api/agent/stream"

    def test_agent_run_and_stream(self) -> None:
        """Test agent execution with Redis streaming."""
        # Start agent run
        response = SampleTestHelper.post_text(
            f"{self.agent_url}/run",
            "Plan a 1-day trip to Seattle",
        )
        assert response.status_code == 202
        data = response.json()

        assert data["status"] == "accepted"
        assert "conversation_id" in data
        conversation_id = data["conversation_id"]

        # Stream response from Redis
        # Note: We use text/plain to avoid SSE parsing complexity
        stream_response = requests.get(
            f"{self.stream_url}/{conversation_id}",
            headers={"Accept": "text/plain"},
            timeout=TIMEOUT,
        )
        assert stream_response.status_code == 200
        assert len(stream_response.text) > 0

    def test_stream_with_sse_format(self) -> None:
        """Test streaming with Server-Sent Events format."""
        # Start agent run
        response = SampleTestHelper.post_text(
            f"{self.agent_url}/run",
            "What's the weather like?",
        )
        assert response.status_code == 202
        data = response.json()
        conversation_id = data["conversation_id"]

        # Stream with SSE format
        stream_response = requests.get(
            f"{self.stream_url}/{conversation_id}",
            headers={"Accept": "text/event-stream"},
            timeout=TIMEOUT,
        )
        assert stream_response.status_code == 200
        assert stream_response.headers.get("content-type") == "text/event-stream"

        # Check for SSE event markers
        content = stream_response.text
        assert "event:" in content or "data:" in content

    def test_stream_nonexistent_conversation(self) -> None:
        """Test streaming from a non-existent conversation."""
        fake_id = "nonexistent-conversation-12345"

        # Should timeout or return error after waiting
        stream_response = requests.get(
            f"{self.stream_url}/{fake_id}",
            headers={"Accept": "text/plain"},
            timeout=TIMEOUT,
        )
        assert stream_response.status_code == 200
        # Should contain error or timeout message
        assert len(stream_response.text) > 0

    def test_health_endpoint(self) -> None:
        """Test health check endpoint."""
        response = SampleTestHelper.get(f"{self.base_url}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "agents" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
