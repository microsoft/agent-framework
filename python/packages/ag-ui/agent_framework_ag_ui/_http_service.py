# Copyright (c) Microsoft. All rights reserved.

"""HTTP service for AG-UI protocol communication."""

import json
import logging
from collections.abc import AsyncIterable
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AGUIHttpService:
    """HTTP service for AG-UI protocol communication.

    Handles HTTP POST requests and Server-Sent Events (SSE) stream parsing
    for the AG-UI protocol.

    Examples:
        Basic usage:

        .. code-block:: python

            service = AGUIHttpService("http://localhost:8888/")
            async for event in service.post_run(
                thread_id="thread_123",
                run_id="run_456",
                messages=[{"role": "user", "content": "Hello"}]
            ):
                print(event["type"])

        With context manager:

        .. code-block:: python

            async with AGUIHttpService("http://localhost:8888/") as service:
                async for event in service.post_run(...):
                    print(event)
    """

    def __init__(
        self,
        endpoint: str,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Initialize the HTTP service.

        Args:
            endpoint: AG-UI server endpoint URL (e.g., "http://localhost:8888/")
            http_client: Optional httpx AsyncClient. If None, creates a new one.
            timeout: Request timeout in seconds (default: 60.0)
        """
        self.endpoint = endpoint.rstrip("/")
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.AsyncClient(timeout=timeout)

    async def post_run(
        self,
        thread_id: str,
        run_id: str,
        messages: list[dict[str, Any]],
        state: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterable[dict[str, Any]]:
        """Post a run request and stream AG-UI events.

        Args:
            thread_id: Thread identifier for conversation continuity
            run_id: Unique run identifier
            messages: List of messages in AG-UI format
            state: Optional state object to send to server
            tools: Optional list of tools available to the agent

        Yields:
            AG-UI event dictionaries parsed from SSE stream

        Raises:
            httpx.HTTPStatusError: If the HTTP request fails
            ValueError: If SSE parsing encounters invalid data

        Examples:
            .. code-block:: python

                service = AGUIHttpService("http://localhost:8888/")
                async for event in service.post_run(
                    thread_id="thread_abc",
                    run_id="run_123",
                    messages=[{"role": "user", "content": "Hello"}],
                    state={"user_context": {"name": "Alice"}}
                ):
                    if event["type"] == "TEXT_MESSAGE_CONTENT":
                        print(event["delta"])
        """
        # Build request payload
        request_data: dict[str, Any] = {
            "thread_id": thread_id,
            "run_id": run_id,
            "messages": messages,
        }

        if state is not None:
            request_data["state"] = state

        if tools is not None:
            request_data["tools"] = tools

        logger.debug(
            f"Posting run to {self.endpoint}: thread_id={thread_id}, run_id={run_id}, "
            f"messages={len(messages)}, has_state={state is not None}, has_tools={tools is not None}"
        )

        # Stream the response using SSE
        async with self.http_client.stream(
            "POST",
            self.endpoint,
            json=request_data,
            headers={"Accept": "text/event-stream"},
        ) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP request failed: {e.response.status_code} - {e.response.text}")
                raise

            async for line in response.aiter_lines():
                # Parse Server-Sent Events format
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    try:
                        event = json.loads(data)
                        logger.debug(f"Received event: {event.get('type', 'UNKNOWN')}")
                        yield event
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse SSE data: {data}. Error: {e}")
                        # Continue processing other events instead of failing
                        continue

    async def close(self) -> None:
        """Close the HTTP client if owned by this service.

        Only closes the client if it was created by this service instance.
        If an external client was provided, it remains the caller's
        responsibility to close it.
        """
        if self._owns_client and self.http_client:
            await self.http_client.aclose()

    async def __aenter__(self) -> "AGUIHttpService":
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager and clean up resources."""
        await self.close()
