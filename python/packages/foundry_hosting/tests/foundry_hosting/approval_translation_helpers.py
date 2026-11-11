# Copyright (c) Microsoft. All rights reserved.

"""Helpers for Responses approval translation tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from agent_framework import Content


def _approval_request(request_id: str = "orig-1") -> Content:
    return Content.from_function_approval_request(
        id=request_id,
        function_call=Content.from_function_call("call-1", "dangerous", arguments='{"x": 1}'),
    )


class _OrderedRecorder:
    def __init__(self, log: list[str]) -> None:
        self._log = log
        self.saved: list[tuple[str, Content]] = []

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        self._log.append(f"save:{approval_request_id}")
        self.saved.append((approval_request_id, request))


def _event_type(event: Any) -> str:
    event_type = event.get("type") if isinstance(event, Mapping) else event.type  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(event_type, str)
    return event_type


async def _events_without_id(*_: Any, **__: Any) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "response.output_item.added", "item": {"type": "mcp_approval_request"}}
