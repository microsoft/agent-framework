# Copyright (c) Microsoft. All rights reserved.

"""HTTP service for AG-UI protocol communication."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterable, Mapping, Sequence
from typing import Any, cast

import httpx
from ag_ui.core import Interrupt, ResumeEntry

logger = logging.getLogger(__name__)


def _json_safe_protocol_value(value: Any) -> Any:
    """Convert protocol values to JSON-compatible data using AG-UI aliases."""
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe_protocol_value(model_dump(by_alias=True, exclude_none=True))
    if isinstance(value, Mapping):
        return {key: _json_safe_protocol_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe_protocol_value(item) for item in value]
    return value


def _serialize_available_interrupts(available_interrupts: Sequence[Any] | None) -> list[dict[str, Any]] | None:
    """Serialize typed or compatible interrupt inputs to canonical AG-UI JSON."""
    if available_interrupts is None:
        return None
    serialized: list[dict[str, Any]] = []
    for interrupt in available_interrupts:
        if isinstance(interrupt, Interrupt):
            serialized.append(cast(dict[str, Any], interrupt.model_dump(by_alias=True, exclude_none=True)))
            continue
        if isinstance(interrupt, Mapping) and "reason" not in interrupt:
            interrupt = dict(interrupt)
            interrupt_type = interrupt.pop("type", None)
            if interrupt_type == "request_info" or interrupt_type is None:
                interrupt["reason"] = "input_required"
            elif isinstance(interrupt_type, str):
                interrupt["reason"] = interrupt_type
        serialized.append(
            cast(dict[str, Any], Interrupt.model_validate(interrupt).model_dump(by_alias=True, exclude_none=True))
        )
    return serialized


def _serialize_resume_entry(entry: Any) -> dict[str, Any]:
    """Serialize one typed or legacy resume entry to canonical AG-UI JSON."""
    if isinstance(entry, ResumeEntry):
        return cast(dict[str, Any], entry.model_dump(by_alias=True, exclude_none=True))

    model_dump = getattr(entry, "model_dump", None)
    if callable(model_dump):
        entry = model_dump(by_alias=True, exclude_none=True)

    if not isinstance(entry, Mapping):
        raise ValueError("Each resume entry must be an object.")

    entry_dict = cast(Mapping[str, Any], entry)
    interrupt_id = (
        entry_dict.get("interruptId")
        or entry_dict.get("interrupt_id")
        or entry_dict.get("id")
        or entry_dict.get("toolCallId")
    )
    if not interrupt_id:
        raise ValueError("Each resume entry must include interruptId.")

    status = entry_dict.get("status") or "resolved"
    payload = (
        entry_dict.get("payload")
        if "payload" in entry_dict
        else entry_dict.get("value")
        if "value" in entry_dict
        else entry_dict.get("response")
        if "response" in entry_dict
        else {
            key: value
            for key, value in entry_dict.items()
            if key not in {"id", "interruptId", "interrupt_id", "toolCallId", "type", "status"}
        }
    )

    serialized: dict[str, Any] = {"interruptId": str(interrupt_id), "status": str(status)}
    if status != "cancelled" or payload:
        serialized["payload"] = _json_safe_protocol_value(payload)
    return cast(dict[str, Any], ResumeEntry.model_validate(serialized).model_dump(by_alias=True, exclude_none=True))


def _serialize_resume(resume: Any) -> Any:  # noqa: ANN401
    """Serialize typed or compatible resume inputs to canonical AG-UI JSON."""
    if resume is None:
        return None
    if isinstance(resume, Sequence) and not isinstance(resume, (str, bytes, bytearray)):
        return [_serialize_resume_entry(entry) for entry in resume]
    if isinstance(resume, Mapping):
        resume_dict = cast(Mapping[str, Any], resume)
        if isinstance(resume_dict.get("interrupts"), Sequence) and not isinstance(
            resume_dict.get("interrupts"), (str, bytes, bytearray)
        ):
            return [_serialize_resume_entry(entry) for entry in cast(Sequence[Any], resume_dict["interrupts"])]
        if isinstance(resume_dict.get("interrupt"), Sequence) and not isinstance(
            resume_dict.get("interrupt"), (str, bytes, bytearray)
        ):
            return [_serialize_resume_entry(entry) for entry in cast(Sequence[Any], resume_dict["interrupt"])]
        if any(key in resume_dict for key in ("interruptId", "interrupt_id", "id", "toolCallId")):
            return [_serialize_resume_entry(resume_dict)]
    return _json_safe_protocol_value(resume)


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
        available_interrupts: Sequence[Any] | None = None,
        resume: Any = None,
    ) -> AsyncIterable[dict[str, Any]]:
        """Post a run request and stream AG-UI events.

        Args:
            thread_id: Thread identifier for conversation continuity
            run_id: Unique run identifier
            messages: List of messages in AG-UI format
            state: Optional state object to send to server
            tools: Optional list of tools available to the agent
            available_interrupts: Optional list of interrupt descriptors available for resumption
            resume: Optional resume payload to continue a paused run

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

        serialized_available_interrupts = _serialize_available_interrupts(available_interrupts)
        if serialized_available_interrupts is not None:
            request_data["availableInterrupts"] = serialized_available_interrupts

        serialized_resume = _serialize_resume(resume)
        if serialized_resume is not None:
            request_data["resume"] = serialized_resume

        logger.debug(
            f"Posting run to {self.endpoint}: thread_id={thread_id}, run_id={run_id}, "
            f"messages={len(messages)}, has_state={state is not None}, has_tools={tools is not None}, "
            f"has_available_interrupts={available_interrupts is not None}, has_resume={resume is not None}"
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

    async def __aenter__(self) -> AGUIHttpService:
        """Enter async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager and clean up resources."""
        await self.close()
