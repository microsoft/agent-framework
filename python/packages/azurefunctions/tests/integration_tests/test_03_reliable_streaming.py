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

import time

import pytest
import requests
from testutils import (
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
        response = SampleTestHelper.post_json(
            f"{self.agent_url}/run",
            {"message": "Plan a 1-day trip to Seattle in 1 sentence", "wait_for_response": False},
        )
        assert response.status_code == 202
        data = response.json()

        thread_id = data.get("thread_id")

        # Wait a moment for the agent to start writing to Redis
        time.sleep(2)

        # Stream response from Redis with shorter timeout
        # Note: We use text/plain to avoid SSE parsing complexity
        stream_response = requests.get(
            f"{self.stream_url}/{thread_id}",
            headers={"Accept": "text/plain"},
            timeout=30,  # Shorter timeout for test
        )
        assert stream_response.status_code == 200

    def test_stream_with_sse_format(self) -> None:
        """Test streaming with Server-Sent Events format."""
        # Start agent run
        response = SampleTestHelper.post_json(
            f"{self.agent_url}/run",
            {"message": "What's the weather like?", "wait_for_response": False},
        )
        assert response.status_code == 202
        data = response.json()
        thread_id = data.get("thread_id")

        # Wait for agent to start writing
        time.sleep(2)

        # Stream with SSE format
        stream_response = requests.get(
            f"{self.stream_url}/{thread_id}",
            headers={"Accept": "text/event-stream"},
            timeout=30,  # Shorter timeout
        )
        assert stream_response.status_code == 200
        content_type = stream_response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        # Check for SSE event markers if we got content
        content = stream_response.text
        if content:
            assert "event:" in content or "data:" in content

    def test_stream_nonexistent_conversation(self) -> None:
        """Test streaming from a non-existent conversation.

        The endpoint will wait for data in Redis, but since the conversation
        doesn't exist, it will timeout. This is expected behavior.
        """
        fake_id = "nonexistent-conversation-12345"

        # Should timeout since the conversation doesn't exist
        with pytest.raises(requests.exceptions.ReadTimeout):
            requests.get(
                f"{self.stream_url}/{fake_id}",
                headers={"Accept": "text/plain"},
                timeout=10,  # Short timeout for non-existent ID
            )

    def test_health_endpoint(self) -> None:
        """Test health check endpoint."""
        response = SampleTestHelper.get(f"{self.base_url}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "agents" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
