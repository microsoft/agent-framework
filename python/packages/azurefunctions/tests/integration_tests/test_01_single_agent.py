# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Single Agent Sample

Tests the single agent sample with various message formats and session management.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite or Azure Storage account configured

Usage:
    uv run pytest packages/azurefunctions/tests/integration_tests/test_01_single_agent.py -v
"""

import pytest

from .testutils import SampleTestHelper, skip_if_azure_functions_integration_tests_disabled

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("01_single_agent"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


class TestSampleSingleAgent:
    """Tests for 01_single_agent sample."""

    @pytest.fixture(autouse=True)
    def _set_base_url(self, base_url: str) -> None:
        """Provide agent-specific base URL for the tests."""
        self.base_url = f"{base_url}/api/agents/Joker"

    def test_health_check(self, base_url: str) -> None:
        """Test health check endpoint."""
        response = SampleTestHelper.get(f"{base_url}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_simple_message_json(self) -> None:
        """Test sending a simple message with JSON payload."""
        response = SampleTestHelper.post_json(
            f"{self.base_url}/run",
            {"message": "Tell me a short joke about cloud computing.", "thread_id": "test-simple-json"},
        )
        # Agent can return 200 (immediate) or 202 (async with wait_for_response=false)
        assert response.status_code in [200, 202]
        data = response.json()

        if response.status_code == 200:
            # Synchronous response - check result directly
            assert data["status"] == "success"
            assert "response" in data
            assert data["message_count"] >= 1
        else:
            # Async response - check we got correlation info
            assert "correlation_id" in data or "thread_id" in data

    def test_simple_message_plain_text(self) -> None:
        """Test sending a message with plain text payload."""
        response = SampleTestHelper.post_text(f"{self.base_url}/run", "Tell me a short joke about networking.")
        assert response.status_code in [200, 202]

        # Agent responded with plain text when the request body was text/plain.
        assert response.text.strip()
        assert response.headers.get("x-ms-thread-id") is not None

    def test_thread_id_in_query(self) -> None:
        """Test using thread_id in query parameter."""
        response = SampleTestHelper.post_text(
            f"{self.base_url}/run?thread_id=test-query-thread", "Tell me a short joke about weather in Texas."
        )
        assert response.status_code in [200, 202]

        assert response.text.strip()
        assert response.headers.get("x-ms-thread-id") == "test-query-thread"

    def test_conversation_continuity(self) -> None:
        """Test conversation context is maintained across requests."""
        thread_id = "test-continuity"

        # First message
        response1 = SampleTestHelper.post_json(
            f"{self.base_url}/run",
            {"message": "Tell me a short joke about weather in Seattle.", "thread_id": thread_id},
        )
        assert response1.status_code in [200, 202]

        if response1.status_code == 200:
            data1 = response1.json()
            assert data1["message_count"] == 1

            # Second message in same session
            response2 = SampleTestHelper.post_json(
                f"{self.base_url}/run", {"message": "What about San Francisco?", "thread_id": thread_id}
            )
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["message_count"] == 2
        else:
            # In async mode, we can't easily test message count
            # Just verify we can make multiple calls
            response2 = SampleTestHelper.post_json(
                f"{self.base_url}/run", {"message": "What about Texas?", "thread_id": thread_id}
            )
            assert response2.status_code == 202


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
