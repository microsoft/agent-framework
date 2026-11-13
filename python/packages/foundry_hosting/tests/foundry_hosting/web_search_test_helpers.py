# Copyright (c) Microsoft. All rights reserved.

"""Reusable offline test helpers for web-search citations."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
from agent_framework import AgentResponseUpdate, Annotation, Content

from .toolbox_approval_helpers import ToolboxApprovalServer

_PYTHON_SOURCE_URL = "https://www.python.org/downloads/release/python-31315/"
_DOCS_SOURCE_URL = "https://docs.python.org/3/whatsnew/3.13.html"


class _ToolResultServer(ToolboxApprovalServer):
    """Offline Toolbox server whose ``tools/call`` response is configurable per test."""

    def __init__(self) -> None:
        super().__init__()
        self.call_result: dict[str, Any] = {}

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payload = json.loads(request.content)
            if payload.get("method") == "tools/call" and "id" in payload:
                self.calls.append(payload["params"])
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": self.call_result})
        return await super().handle(request)


def _web_search_result(call_id: str) -> Content:
    """Build a search result with duplicate URLs and non-web citations for response-host tests."""
    return Content.from_function_result(
        call_id,
        result=[
            Content.from_text(
                "Python 3.13.15 is the latest release.",
                annotations=[
                    _url_citation(),
                    Annotation(type="citation", url=_DOCS_SOURCE_URL, title="What's New"),
                ],
            ),
            Content.from_text(
                '{"annotations": []}',
                annotations=[
                    Annotation(type="citation", url=_PYTHON_SOURCE_URL, title="Duplicate title"),
                    Annotation(type="citation", url="javascript:alert(1)", title="Unsafe"),
                    Annotation(type="citation", url="notes.txt", file_id="file_123", title="File"),
                ],
            ),
        ],
    )


def _expected_source_citations(text: str) -> list[dict[str, Any]]:
    """Return the zero-length end-of-text citations expected for ``_web_search_result``."""
    return [
        _expected_url_citation(start_index=len(text), end_index=len(text)),
        _expected_url_citation(url=_DOCS_SOURCE_URL, title="What's New", start_index=len(text), end_index=len(text)),
    ]


def _web_search_citation_updates(answer: str) -> list[AgentResponseUpdate]:
    return [
        AgentResponseUpdate(
            contents=[Content.from_function_call("call_1", "web_search", arguments={})],
            role="assistant",
            message_id="msg_call",
        ),
        AgentResponseUpdate(contents=[_web_search_result("call_1")], role="tool", message_id="msg_result"),
        AgentResponseUpdate(contents=[Content.from_text(answer)], role="assistant", message_id="msg_answer"),
    ]


def _url_citation(
    *,
    url: str = _PYTHON_SOURCE_URL,
    title: str = "Python 3.13.15",
    start_index: int = 0,
    end_index: int = 6,
) -> Annotation:
    return Annotation(
        type="citation",
        url=url,
        title=title,
        annotated_regions=[{"type": "text_span", "start_index": start_index, "end_index": end_index}],
    )


def _expected_url_citation(
    *,
    url: str = _PYTHON_SOURCE_URL,
    title: str = "Python 3.13.15",
    start_index: int = 0,
    end_index: int = 6,
) -> dict[str, Any]:
    return {
        "type": "url_citation",
        "url": url,
        "title": title,
        "start_index": start_index,
        "end_index": end_index,
    }
