# Copyright (c) Microsoft. All rights reserved.

"""End-to-end YAML integration test for ``HttpRequestAction``.

Loads the ``tests/workflows/http_request.yaml`` fixture (parity with the .NET
integration fixture) through ``WorkflowFactory.create_workflow_from_yaml_path``
with a stub :class:`HttpRequestHandler` and asserts state is populated.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

pytestmark = [
    pytest.mark.skipif(
        not _powerfx_available,
        reason="powerfx not available — declarative workflows require it.",
    ),
    pytest.mark.skipif(
        sys.version_info >= (3, 14),
        reason="Skipped on Python 3.14+ to keep parity with declarative suite.",
    ),
]

from agent_framework_declarative import WorkflowFactory  # noqa: E402
from agent_framework_declarative._workflows import DECLARATIVE_STATE_KEY  # noqa: E402
from agent_framework_declarative._workflows._http_handler import (  # noqa: E402
    HttpRequestInfo,
    HttpRequestResult,
)

FIXTURE_PATH = Path(__file__).parent / "workflows" / "http_request.yaml"


class _StubHandler:
    """Test double that records requests and returns a canned response."""

    def __init__(self, result: HttpRequestResult) -> None:
        self._result = result
        self.received: list[HttpRequestInfo] = []

    async def send(self, info: HttpRequestInfo) -> HttpRequestResult:
        self.received.append(info)
        return self._result


@pytest.mark.asyncio
async def test_http_request_yaml_roundtrip() -> None:
    handler = _StubHandler(
        HttpRequestResult(
            status_code=200,
            is_success_status_code=True,
            body='{"name": "runtime", "visibility": "public", "stars": 12345}',
            headers={
                "content-type": ["application/json"],
                "x-ratelimit-remaining": ["59"],
            },
        )
    )

    factory = WorkflowFactory(http_request_handler=handler)
    workflow = factory.create_workflow_from_yaml_path(FIXTURE_PATH)
    await workflow.run({})

    decl: dict[str, Any] = workflow._state.get(DECLARATIVE_STATE_KEY) or {}
    local = decl.get("Local") or {}

    assert local.get("RepoOwner") == "dotnet"
    repo_info = local.get("RepoInfo")
    assert isinstance(repo_info, dict), f"Expected dict body, got {type(repo_info)!r}"
    assert repo_info["name"] == "runtime"
    assert repo_info["visibility"] == "public"
    assert repo_info["stars"] == 12345

    repo_headers = local.get("RepoHeaders")
    assert isinstance(repo_headers, dict)
    # Single-value header surfaces as plain string.
    assert repo_headers.get("content-type") == "application/json"
    assert repo_headers.get("x-ratelimit-remaining") == "59"

    # Stub got the right call.
    assert len(handler.received) == 1
    sent = handler.received[0]
    assert sent.method == "GET"
    assert sent.url == "https://api.github.com/repos/dotnet/runtime"
    assert sent.headers["Accept"] == "application/vnd.github+json"
    assert sent.headers["User-Agent"] == "agent-framework-integration-test"


@pytest.mark.asyncio
async def test_http_request_yaml_missing_handler_fails_at_build_time() -> None:
    """Without an http_request_handler, building the workflow must raise."""
    from agent_framework_declarative._workflows._errors import DeclarativeWorkflowError

    factory = WorkflowFactory()  # no handler configured
    with pytest.raises(DeclarativeWorkflowError) as excinfo:
        factory.create_workflow_from_yaml_path(FIXTURE_PATH)
    msg = str(excinfo.value)
    assert "HttpRequestAction" in msg
    assert "http_request_handler" in msg
