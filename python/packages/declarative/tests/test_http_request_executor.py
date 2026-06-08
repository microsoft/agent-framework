# Copyright (c) Microsoft. All rights reserved.

"""Tests for HttpRequestActionExecutor.

These tests use a stub HttpRequestHandler that returns canned HttpRequestResults.
No real network or httpx transports are exercised. See
test_default_http_request_handler.py for tests that exercise the real
DefaultHttpRequestHandler against httpx.MockTransport.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import httpx
import pytest

try:
    import powerfx  # noqa: F401

    _powerfx_available = True
except (ImportError, RuntimeError):
    _powerfx_available = False

pytestmark = pytest.mark.skipif(
    not _powerfx_available or sys.version_info >= (3, 14),
    reason="PowerFx engine not available (requires dotnet runtime)",
)

from agent_framework_declarative._workflows import (  # noqa: E402
    DECLARATIVE_STATE_KEY,
    DeclarativeActionError,
    DeclarativeWorkflowError,
    HttpRequestHandler,
    HttpRequestInfo,
    HttpRequestResult,
    WorkflowFactory,
)


class StubHandler:
    """Test stub that records the last call and returns a canned result."""

    def __init__(
        self,
        result: HttpRequestResult | None = None,
        *,
        raise_exc: BaseException | None = None,
    ) -> None:
        self.result = result
        self.raise_exc = raise_exc
        self.last_info: HttpRequestInfo | None = None
        self.call_count = 0

    async def send(self, info: HttpRequestInfo) -> HttpRequestResult:
        self.call_count += 1
        self.last_info = info
        if self.raise_exc is not None:
            raise self.raise_exc
        assert self.result is not None
        return self.result


def _ok(body: str = "", headers: dict[str, list[str]] | None = None) -> HttpRequestResult:
    return HttpRequestResult(
        status_code=200,
        is_success_status_code=True,
        body=body,
        headers=headers or {},
    )


def _err(status: int = 500, body: str = "", headers: dict[str, list[str]] | None = None) -> HttpRequestResult:
    return HttpRequestResult(
        status_code=status,
        is_success_status_code=False,
        body=body,
        headers=headers or {},
    )


async def _run(yaml_def: dict[str, Any], handler: HttpRequestHandler) -> Any:
    """Build & run a workflow, returning final WorkflowState."""
    factory = WorkflowFactory(http_request_handler=handler)
    workflow = factory.create_workflow_from_definition(yaml_def)
    return await workflow.run({})


def _state(workflow: Any, events: Any) -> dict[str, Any]:
    """Read declarative state out of the workflow after run completes."""
    return workflow._state.get(DECLARATIVE_STATE_KEY) or {}


# Helper used by parametrised path tests
_TEST_URL = "https://api.example.test/items"


def _action(
    *,
    method: str | None = None,
    url: str = _TEST_URL,
    headers: dict[str, Any] | None = None,
    query_parameters: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    response: Any = None,
    response_headers: Any = None,
    conversation_id: str | None = None,
    request_timeout_ms: int | None = None,
    connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "kind": "HttpRequestAction",
        "id": "http_action",
        "url": url,
    }
    if method is not None:
        action["method"] = method
    if headers is not None:
        action["headers"] = headers
    if query_parameters is not None:
        action["queryParameters"] = query_parameters
    if body is not None:
        action["body"] = body
    if response is not None:
        action["response"] = response
    if response_headers is not None:
        action["responseHeaders"] = response_headers
    if conversation_id is not None:
        action["conversationId"] = conversation_id
    if request_timeout_ms is not None:
        action["requestTimeoutInMilliseconds"] = request_timeout_ms
    if connection is not None:
        action["connection"] = connection
    return action


def _yaml(action: dict[str, Any]) -> dict[str, Any]:
    return {"name": "http_test", "actions": [action]}


# ---------- Success path: response parsing ----------------------------------


class TestSuccessPath:
    @pytest.mark.asyncio
    async def test_get_parses_json_object(self) -> None:
        handler = StubHandler(_ok('{"key":"value","number":42}'))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(method="GET", response="Local.Result")))
        await workflow.run({})

        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == {"key": "value", "number": 42}
        assert handler.last_info is not None
        assert handler.last_info.method == "GET"
        assert handler.last_info.url == _TEST_URL

    @pytest.mark.asyncio
    async def test_get_parses_plain_string(self) -> None:
        handler = StubHandler(_ok("not-json content"))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(response="Local.Result")))
        await workflow.run({})

        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == "not-json content"

    @pytest.mark.asyncio
    async def test_get_empty_body_yields_none(self) -> None:
        handler = StubHandler(_ok(""))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(response="Local.Result")))
        await workflow.run({})

        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] is None

    @pytest.mark.asyncio
    async def test_response_object_form_path(self) -> None:
        handler = StubHandler(_ok('{"x":1}'))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(response={"path": "Local.Result"})))
        await workflow.run({})

        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["Result"] == {"x": 1}

    @pytest.mark.asyncio
    async def test_no_response_path_does_not_assign(self) -> None:
        handler = StubHandler(_ok('{"x":1}'))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        # Should complete without error and without writing anything
        await workflow.run({})


# ---------- Method / headers / query params --------------------------------


class TestRequestComposition:
    @pytest.mark.asyncio
    async def test_default_method_is_get(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        await workflow.run({})

        assert handler.last_info is not None
        assert handler.last_info.method == "GET"

    @pytest.mark.asyncio
    async def test_method_uppercased(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(method="post")))
        await workflow.run({})

        assert handler.last_info is not None
        assert handler.last_info.method == "POST"

    @pytest.mark.asyncio
    async def test_headers_are_forwarded_and_empty_skipped(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    headers={
                        "Accept": "application/json",
                        "X-Empty": "",
                        "Authorization": "Bearer token",
                    }
                )
            )
        )
        await workflow.run({})

        assert handler.last_info is not None
        assert handler.last_info.headers == {
            "Accept": "application/json",
            "Authorization": "Bearer token",
        }

    @pytest.mark.asyncio
    async def test_query_parameters_stringified(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    query_parameters={
                        "name": "alpha",
                        "limit": 10,
                        "active": True,
                        "ratio": 0.5,
                        "missing": None,  # dropped
                    }
                )
            )
        )
        await workflow.run({})

        assert handler.last_info is not None
        assert handler.last_info.query_parameters == {
            "name": "alpha",
            "limit": "10",
            "active": "true",
            "ratio": "0.5",
        }


# ---------- Body composition ------------------------------------------------


class TestBody:
    @pytest.mark.asyncio
    async def test_post_json_body_sets_content_type_and_serialises(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    method="POST",
                    body={"kind": "json", "content": {"k": "v", "n": 1}},
                )
            )
        )
        await workflow.run({})

        info = handler.last_info
        assert info is not None
        assert info.body_content_type == "application/json"
        assert info.body is not None
        # JSON serialized, key order may vary
        import json

        assert json.loads(info.body) == {"k": "v", "n": 1}

    @pytest.mark.asyncio
    async def test_post_raw_body_uses_declared_content_type(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    method="POST",
                    body={
                        "kind": "raw",
                        "content": "raw body text",
                        "contentType": "text/plain",
                    },
                )
            )
        )
        await workflow.run({})

        info = handler.last_info
        assert info is not None
        assert info.body == "raw body text"
        assert info.body_content_type == "text/plain"

    @pytest.mark.asyncio
    async def test_post_raw_body_without_content_type_defaults_to_text_plain(self) -> None:
        """Match .NET RawRequestContent: no contentType => default text/plain.

        Otherwise the request is sent without a Content-Type header which most
        servers will treat as application/octet-stream and fail to parse.
        """
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    method="POST",
                    body={"kind": "raw", "content": "plain body"},
                )
            )
        )
        await workflow.run({})

        info = handler.last_info
        assert info is not None
        assert info.body == "plain body"
        assert info.body_content_type == "text/plain"

    @pytest.mark.asyncio
    async def test_long_form_body_kinds_accepted(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    method="POST",
                    body={"kind": "JsonRequestContent", "content": {"k": 1}},
                )
            )
        )
        await workflow.run({})
        info = handler.last_info
        assert info is not None
        assert info.body_content_type == "application/json"

    @pytest.mark.asyncio
    async def test_unknown_body_kind_raises(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(body={"kind": "weirdform", "content": "x"})))
        with pytest.raises(Exception) as excinfo:
            await workflow.run({})
        # Should surface as ValueError (potentially wrapped by runner)
        msg = str(excinfo.value)
        assert "weirdform" in msg or "unsupported value" in msg

    @pytest.mark.asyncio
    async def test_no_body_omitted(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        await workflow.run({})
        info = handler.last_info
        assert info is not None
        assert info.body is None
        assert info.body_content_type is None


# ---------- Non-2xx and error handling -------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_non_2xx_raises_declarative_action_error(self) -> None:
        handler = StubHandler(_err(status=500, body="server exploded"))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        msg = str(excinfo.value)
        assert "500" in msg
        assert "server exploded" in msg

    @pytest.mark.asyncio
    async def test_non_2xx_long_body_truncated(self) -> None:
        big_body = "A" * 1000
        handler = StubHandler(_err(status=500, body=big_body))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        msg = str(excinfo.value)
        assert "[truncated]" in msg
        assert len(msg) < 512
        # Should NOT contain the full 1000-char body
        assert big_body not in msg

    @pytest.mark.asyncio
    async def test_non_2xx_empty_body_omits_body_section(self) -> None:
        handler = StubHandler(_err(status=404, body=""))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        msg = str(excinfo.value)
        assert "404" in msg
        assert "Body:" not in msg

    @pytest.mark.asyncio
    async def test_non_2xx_control_chars_collapsed(self) -> None:
        handler = StubHandler(_err(status=500, body="line1\r\nline2\tlong"))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        msg = str(excinfo.value)
        assert "\r" not in msg
        assert "\n" not in msg
        assert "\t" not in msg
        assert "line1  line2 long" in msg

    @pytest.mark.asyncio
    async def test_timeout_exception_becomes_declarative_action_error(self) -> None:
        handler = StubHandler(raise_exc=httpx.TimeoutException("timeout"))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        assert "timed out" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_stdlib_timeout_error_becomes_declarative_action_error(self) -> None:
        handler = StubHandler(raise_exc=TimeoutError("clock"))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        assert "timed out" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_transport_error_becomes_declarative_action_error(self) -> None:
        handler = StubHandler(raise_exc=httpx.ConnectError("dns failure"))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        msg = str(excinfo.value)
        assert "failed" in msg
        assert _TEST_URL in msg

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates_unchanged(self) -> None:
        """CancelledError from the handler must propagate so cancellation works."""
        handler = StubHandler(raise_exc=asyncio.CancelledError())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        # CancelledError is allowed to surface as either CancelledError or as
        # the runner's wrapped form, but it MUST NOT be DeclarativeActionError.
        with pytest.raises(BaseException) as excinfo:
            await workflow.run({})
        assert not isinstance(excinfo.value, DeclarativeActionError)

    @pytest.mark.asyncio
    async def test_generic_exception_from_custom_handler_wrapped(self) -> None:
        """A custom handler raising a non-httpx Exception must be wrapped.

        Authors can plug in custom HttpRequestHandler implementations that use
        any transport (requests-like clients, gRPC bridges, mock test doubles,
        etc.). The executor must wrap arbitrary Exception subclasses uniformly
        so that workflow error handling stays consistent across transports.
        """
        handler = StubHandler(raise_exc=RuntimeError("custom transport blew up"))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action()))
        with pytest.raises(DeclarativeActionError) as excinfo:
            await workflow.run({})
        msg = str(excinfo.value)
        assert "failed" in msg
        assert "RuntimeError" in msg
        assert _TEST_URL in msg


# ---------- Response headers ------------------------------------------------


class TestResponseHeaders:
    @pytest.mark.asyncio
    async def test_response_headers_folded_with_commas(self) -> None:
        handler = StubHandler(
            _ok(
                "ok",
                headers={
                    "Content-Type": ["application/json"],
                    "Set-Cookie": ["a=1", "b=2"],
                },
            )
        )
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(response_headers="Local.H")))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        h = decl["Local"]["H"]
        assert h["Content-Type"] == "application/json"
        assert h["Set-Cookie"] == "a=1,b=2"

    @pytest.mark.asyncio
    async def test_response_headers_empty_assigned_none(self) -> None:
        handler = StubHandler(_ok("ok", headers={}))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(response_headers="Local.H")))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["H"] is None

    @pytest.mark.asyncio
    async def test_non_2xx_still_publishes_headers(self) -> None:
        handler = StubHandler(_err(status=500, body="boom", headers={"X-Trace": ["abc"]}))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(response_headers="Local.H")))
        with pytest.raises(DeclarativeActionError):
            await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        assert decl["Local"]["H"] == {"X-Trace": "abc"}


# ---------- ConversationId append -------------------------------------------


class TestConversationAppend:
    @pytest.mark.asyncio
    async def test_conversation_id_appends_message(self) -> None:
        handler = StubHandler(_ok('{"answer":"hello"}'))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(
            _yaml(
                _action(
                    response="Local.Result",
                    conversation_id="conv-test-1",
                )
            )
        )
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        conv = decl["System"]["conversations"].get("conv-test-1")
        assert conv is not None
        assert len(conv["messages"]) == 1

    @pytest.mark.asyncio
    async def test_empty_conversation_id_does_not_append(self) -> None:
        handler = StubHandler(_ok('{"answer":"hello"}'))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(response="Local.Result", conversation_id="")))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        # Auto-init creates an entry for the System.ConversationId conversation,
        # but it should NOT have HTTP-appended messages from us.
        for _cid, conv in decl["System"]["conversations"].items():
            assert conv["messages"] == []

    @pytest.mark.asyncio
    async def test_empty_body_skips_conversation_append(self) -> None:
        handler = StubHandler(_ok(""))
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(conversation_id="conv-test-1")))
        await workflow.run({})
        decl = workflow._state.get(DECLARATIVE_STATE_KEY)
        # No conversation entry should have been created either.
        assert "conv-test-1" not in decl["System"]["conversations"]


# ---------- Connection name -------------------------------------------------


class TestConnection:
    @pytest.mark.asyncio
    async def test_connection_name_forwarded(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(connection={"name": "my-connection"})))
        await workflow.run({})
        assert handler.last_info is not None
        assert handler.last_info.connection_name == "my-connection"


# ---------- Build-time validation -------------------------------------------


class TestBuildTimeValidation:
    def test_missing_url_fails_validation(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        bad = {
            "name": "no_url",
            "actions": [{"kind": "HttpRequestAction", "id": "x"}],
        }
        with pytest.raises(DeclarativeWorkflowError):
            factory.create_workflow_from_definition(bad)

    def test_missing_handler_fails_at_build(self) -> None:
        factory = WorkflowFactory()  # no handler
        with pytest.raises(DeclarativeWorkflowError) as excinfo:
            factory.create_workflow_from_definition(_yaml(_action()))
        assert "http_request_handler" in str(excinfo.value)


# ---------- Timeout forwarding ----------------------------------------------


class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_ms_forwarded(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(request_timeout_ms=2500)))
        await workflow.run({})
        assert handler.last_info is not None
        assert handler.last_info.timeout_ms == 2500

    @pytest.mark.asyncio
    async def test_timeout_ms_zero_treated_as_unset(self) -> None:
        handler = StubHandler(_ok())
        factory = WorkflowFactory(http_request_handler=handler)
        workflow = factory.create_workflow_from_definition(_yaml(_action(request_timeout_ms=0)))
        await workflow.run({})
        assert handler.last_info is not None
        assert handler.last_info.timeout_ms is None
