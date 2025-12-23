# Copyright (c) Microsoft. All rights reserved.
"""
Integration Tests for Callbacks Sample

Tests the callbacks sample for event tracking and management.

The function app is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/azurefunctions/tests/integration_tests/.env.example)
- Azurite or Azure Storage account configured

Usage:
    uv run pytest packages/azurefunctions/tests/integration_tests/test_03_callbacks.py -v
"""

from typing import Any

import pytest
import requests

from .testutils import (
    TIMEOUT,
    SampleTestHelper,
    skip_if_azure_functions_integration_tests_disabled,
)

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("03_callbacks"),
    pytest.mark.usefixtures("function_app_for_test"),
    skip_if_azure_functions_integration_tests_disabled,
]


class TestSampleCallbacks:
    """Tests for 03_callbacks sample."""

    @pytest.fixture(autouse=True)
    def _set_base_url(self, base_url: str) -> None:
        """Provide the callback agent base URL for each test."""
        self.base_url = f"{base_url}/api/agents/CallbackAgent"

    @staticmethod
    def _wait_for_callback_events(base_url: str, thread_id: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        response = SampleTestHelper.get(f"{base_url}/callbacks/{thread_id}")
        if response.status_code == 200:
            events = response.json()
        return events

    def test_agent_with_callbacks(self) -> None:
        """Test agent execution with callback tracking."""
        thread_id = "test-callback"

        response = SampleTestHelper.post_json(
            f"{self.base_url}/run",
            {"message": "Tell me about Python", "thread_id": thread_id},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"

        events = self._wait_for_callback_events(self.base_url, thread_id)

        assert events
        assert any(event.get("event_type") == "final" for event in events)

    def test_get_callbacks(self) -> None:
        """Test retrieving callback events."""
        thread_id = "test-callback-retrieve"

        # Send a message first
        SampleTestHelper.post_json(
            f"{self.base_url}/run",
            {"message": "Hello", "thread_id": thread_id, "wait_for_response": False},
        )

        # Get callbacks
        response = SampleTestHelper.get(f"{self.base_url}/callbacks/{thread_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_delete_callbacks(self) -> None:
        """Test clearing callback events."""
        thread_id = "test-callback-delete"

        # Send a message first
        SampleTestHelper.post_json(
            f"{self.base_url}/run",
            {"message": "Test", "thread_id": thread_id, "wait_for_response": False},
        )

        # Delete callbacks
        response = requests.delete(f"{self.base_url}/callbacks/{thread_id}", timeout=TIMEOUT)
        assert response.status_code == 204


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
