# Copyright (c) Microsoft. All rights reserved.

"""
Integration Tests for Reliable Streaming Sample

Tests the reliable streaming sample using Redis Streams for persistent message delivery.

The worker process is automatically started by the test fixture.

Prerequisites:
- Azure OpenAI credentials configured (see packages/durabletask/tests/integration_tests/.env.example)
- DTS emulator running (docker run -d -p 8080:8080 mcr.microsoft.com/durabletask/emulator:latest)
- Redis running (docker run -d --name redis -p 6379:6379 redis:latest)

Usage:
    uv run pytest packages/durabletask/tests/integration_tests/test_03_single_agent_streaming.py -v
"""

import asyncio
import os
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import redis.asyncio as aioredis
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

from agent_framework_durabletask import DurableAIAgentClient

from .testutils import OrchestrationHelper

# Add sample directory to path to import RedisStreamResponseHandler
SAMPLE_DIR = Path(__file__).parents[4] / "samples" / "getting_started" / "durabletask" / "03_single_agent_streaming"
sys.path.insert(0, str(SAMPLE_DIR))

from redis_stream_response_handler import RedisStreamResponseHandler  # type: ignore[reportMissingImports] # noqa: E402

# Module-level markers - applied to all tests in this file
pytestmark = [
    pytest.mark.sample("03_single_agent_streaming"),
    pytest.mark.integration_test,
    pytest.mark.requires_azure_openai,
    pytest.mark.requires_dts,
    pytest.mark.requires_redis,
]


class TestSampleReliableStreaming:
    """Tests for 03_single_agent_streaming sample."""

    @pytest.fixture(autouse=True)
    def setup(self, worker_process: dict[str, Any], dts_endpoint: str) -> None:
        """Setup test fixtures."""
        self.endpoint: str = dts_endpoint
        self.taskhub: str = str(worker_process["taskhub"])

        # Create agent client
        dts_client = DurableTaskSchedulerClient(
            host_address=self.endpoint,
            secure_channel=False,
            taskhub=self.taskhub,
            token_credential=None,
        )
        self.agent_client = DurableAIAgentClient(dts_client)
        self.helper = OrchestrationHelper(dts_client)

        # Redis configuration
        self.redis_connection_string = os.environ.get("REDIS_CONNECTION_STRING", "redis://localhost:6379")
        self.redis_stream_ttl_minutes = int(os.environ.get("REDIS_STREAM_TTL_MINUTES", "10"))

    async def _get_stream_handler(self) -> RedisStreamResponseHandler:  # type: ignore[reportMissingTypeStubs]
        """Create a new Redis stream handler for each request."""
        redis_client = aioredis.from_url(  # type: ignore[reportUnknownMemberType]
            self.redis_connection_string,
            encoding="utf-8",
            decode_responses=False,
        )
        return RedisStreamResponseHandler(  # type: ignore[reportUnknownMemberType]
            redis_client=redis_client,
            stream_ttl=timedelta(minutes=self.redis_stream_ttl_minutes),
        )

    async def _stream_from_redis(
        self,
        thread_id: str,
        cursor: str | None = None,
        timeout: float = 30.0,
    ) -> tuple[str, bool, str]:
        """
        Stream responses from Redis using the sample's RedisStreamResponseHandler.

        Args:
            thread_id: The conversation/thread ID to stream from
            cursor: Optional cursor to resume from
            timeout: Maximum time to wait for stream completion

        Returns:
            Tuple of (accumulated text, completion status, last entry_id)
        """
        accumulated_text = ""
        is_complete = False
        last_entry_id = cursor if cursor else "0-0"
        start_time = time.time()

        async with await self._get_stream_handler() as stream_handler:  # type: ignore[reportUnknownMemberType]
            try:
                async for chunk in stream_handler.read_stream(thread_id, cursor):  # type: ignore[reportUnknownMemberType]
                    if time.time() - start_time > timeout:
                        break

                    last_entry_id = chunk.entry_id  # type: ignore[reportUnknownMemberType]

                    if chunk.error:  # type: ignore[reportUnknownMemberType]
                        # Stream not found or timeout - this is expected if agent hasn't written yet
                        # Don't raise an error, just return what we have
                        break

                    if chunk.is_done:  # type: ignore[reportUnknownMemberType]
                        is_complete = True
                        break

                    if chunk.text:  # type: ignore[reportUnknownMemberType]
                        accumulated_text += chunk.text  # type: ignore[reportUnknownMemberType]

            except Exception as ex:
                # For test purposes, we catch exceptions and return what we have
                if "timed out" not in str(ex).lower():
                    raise

        return accumulated_text, is_complete, last_entry_id  # type: ignore[reportReturnType]

    def test_agent_run_and_stream(self) -> None:
        """Test agent execution with Redis streaming."""
        # Get the TravelPlanner agent
        travel_planner = self.agent_client.get_agent("TravelPlanner")
        assert travel_planner is not None
        assert travel_planner.name == "TravelPlanner"

        # Create a new thread
        thread = travel_planner.get_new_thread()
        assert thread.session_id is not None
        assert thread.session_id.key is not None
        thread_id = str(thread.session_id.key)

        # Start agent run with wait_for_response=False for non-blocking execution
        travel_planner.run(
            "Plan a 1-day trip to Seattle in 1 sentence", thread=thread, options={"wait_for_response": False}
        )

        # Poll Redis stream with retries to handle race conditions
        # The agent may take a few seconds to process and start writing to Redis
        max_retries = 20  # Try for up to 40 seconds (20 * 2 seconds)
        retry_count = 0
        text = ""
        is_complete = False

        while retry_count < max_retries:
            text, is_complete, _ = asyncio.run(self._stream_from_redis(thread_id, timeout=5.0))

            if len(text) > 0 or is_complete:
                # We got content or completion marker
                break

            # Wait before retrying
            time.sleep(3)
            retry_count += 1

        # Verify we got content
        assert len(text) > 0, (
            f"Expected text content but got empty string for thread_id: {thread_id} after {retry_count} retries"
        )
        assert "seattle" in text.lower(), f"Expected 'seattle' in response but got: {text}"
        assert is_complete, "Expected stream to be complete"

    def test_stream_with_cursor_resumption(self) -> None:
        """Test streaming with cursor-based resumption."""
        # Get the TravelPlanner agent
        travel_planner = self.agent_client.get_agent("TravelPlanner")
        thread = travel_planner.get_new_thread()
        assert thread.session_id is not None
        assert thread.session_id.key is not None
        thread_id = str(thread.session_id.key)

        # Start agent run
        travel_planner.run("What's the weather like?", thread=thread, options={"wait_for_response": False})

        # Wait for agent to start writing
        time.sleep(3)

        # Read partial stream to get a cursor
        async def get_partial_stream() -> tuple[str, str]:
            async with await self._get_stream_handler() as stream_handler:  # type: ignore[reportUnknownMemberType]
                accumulated_text = ""
                last_entry_id = "0-0"
                chunk_count = 0

                # Read just first 2 chunks
                async for chunk in stream_handler.read_stream(thread_id):  # type: ignore[reportUnknownMemberType]
                    last_entry_id = chunk.entry_id  # type: ignore[reportUnknownMemberType]
                    if chunk.text:  # type: ignore[reportUnknownMemberType]
                        accumulated_text += chunk.text  # type: ignore[reportUnknownMemberType]
                    chunk_count += 1
                    if chunk_count >= 2:
                        break

                return accumulated_text, last_entry_id  # type: ignore[reportReturnType]

        partial_text, cursor = asyncio.run(get_partial_stream())

        # Resume from cursor
        remaining_text, _, _ = asyncio.run(self._stream_from_redis(thread_id, cursor=cursor))

        # Verify we got some initial content
        assert len(partial_text) > 0

        # Combined text should be coherent
        full_text = partial_text + remaining_text
        assert len(full_text) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
