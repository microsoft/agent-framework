# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for WorkflowHitlContext (HITL respond-URL helper)."""

# pyright: reportPrivateUsage=false

from types import SimpleNamespace
from typing import Any

import pytest

from agent_framework_azurefunctions import WorkflowHitlContext
from agent_framework_azurefunctions._hitl_context import WEBSITE_HOSTNAME_ENV


def _ctx(metadata: Any) -> SimpleNamespace:
    """Build a stand-in WorkflowContext exposing ``_runner_context.host_metadata``."""
    return SimpleNamespace(_runner_context=SimpleNamespace(host_metadata=metadata))


class TestFromContext:
    """Construction from a workflow executor's context."""

    def test_returns_context_when_metadata_present(self) -> None:
        hitl = WorkflowHitlContext.from_context(_ctx({"instance_id": "inst-1", "workflow_name": "content_moderation"}))
        assert hitl is not None
        assert hitl.instance_id == "inst-1"
        assert hitl.workflow_name == "content_moderation"

    def test_returns_none_when_no_runner_context(self) -> None:
        # A bare object without _runner_context (e.g. an unexpected ctx) yields None.
        assert WorkflowHitlContext.from_context(SimpleNamespace()) is None

    def test_returns_none_when_metadata_absent(self) -> None:
        # In-process RunnerContext has no host_metadata -> getattr default None.
        assert WorkflowHitlContext.from_context(_ctx(None)) is None

    def test_returns_none_when_metadata_not_a_dict(self) -> None:
        assert WorkflowHitlContext.from_context(_ctx("not-a-dict")) is None

    def test_returns_none_when_instance_id_missing(self) -> None:
        assert WorkflowHitlContext.from_context(_ctx({"workflow_name": "wf"})) is None

    def test_returns_none_when_workflow_name_missing(self) -> None:
        assert WorkflowHitlContext.from_context(_ctx({"instance_id": "inst-1"})) is None


class TestBaseUrl:
    """base_url resolution from override and WEBSITE_HOSTNAME."""

    def test_explicit_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(WEBSITE_HOSTNAME_ENV, "ignored.azurewebsites.net")
        hitl = WorkflowHitlContext.from_context(
            _ctx({"instance_id": "i", "workflow_name": "wf"}),
            base_url="https://contoso.example.com/",
        )
        assert hitl is not None
        # Trailing slash trimmed; override used verbatim over the env host.
        assert hitl.base_url == "https://contoso.example.com"

    def test_website_hostname_gets_https(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(WEBSITE_HOSTNAME_ENV, "myapp.azurewebsites.net")
        hitl = WorkflowHitlContext.from_context(_ctx({"instance_id": "i", "workflow_name": "wf"}))
        assert hitl is not None
        assert hitl.base_url == "https://myapp.azurewebsites.net"

    def test_localhost_gets_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(WEBSITE_HOSTNAME_ENV, "localhost:7071")
        hitl = WorkflowHitlContext.from_context(_ctx({"instance_id": "i", "workflow_name": "wf"}))
        assert hitl is not None
        assert hitl.base_url == "http://localhost:7071"

    def test_override_with_scheme_preserved(self) -> None:
        hitl = WorkflowHitlContext.from_context(
            _ctx({"instance_id": "i", "workflow_name": "wf"}),
            base_url="http://127.0.0.1:7071",
        )
        assert hitl is not None
        assert hitl.base_url == "http://127.0.0.1:7071"

    def test_raises_when_no_base_url_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(WEBSITE_HOSTNAME_ENV, raising=False)
        hitl = WorkflowHitlContext.from_context(_ctx({"instance_id": "i", "workflow_name": "wf"}))
        assert hitl is not None
        with pytest.raises(RuntimeError, match=WEBSITE_HOSTNAME_ENV):
            _ = hitl.base_url


class TestUrlBuilders:
    """respond/status URL shapes match the AgentFunctionApp routes."""

    def test_build_respond_url(self) -> None:
        hitl = WorkflowHitlContext.from_context(
            _ctx({"instance_id": "inst-1", "workflow_name": "content_moderation"}),
            base_url="https://app.example.com",
        )
        assert hitl is not None
        assert hitl.build_respond_url("req-9") == (
            "https://app.example.com/api/workflow/content_moderation/respond/inst-1/req-9"
        )

    def test_build_respond_url_accepts_qualified_id(self) -> None:
        # A nested sub-workflow request id (executor~ordinal~rid) flows through unchanged.
        hitl = WorkflowHitlContext.from_context(
            _ctx({"instance_id": "inst-1", "workflow_name": "wf"}),
            base_url="https://app.example.com",
        )
        assert hitl is not None
        assert hitl.build_respond_url("reviewer~0~req-9") == (
            "https://app.example.com/api/workflow/wf/respond/inst-1/reviewer~0~req-9"
        )

    def test_build_status_url(self) -> None:
        hitl = WorkflowHitlContext.from_context(
            _ctx({"instance_id": "inst-1", "workflow_name": "wf"}),
            base_url="https://app.example.com",
        )
        assert hitl is not None
        assert hitl.build_status_url() == "https://app.example.com/api/workflow/wf/status/inst-1"


class TestNestedPrefix:
    """request_path_prefix qualifies a bare request id back to the root instance."""

    def test_prefix_read_from_metadata(self) -> None:
        # host_metadata for a nested executor carries the root instance/workflow and the
        # accumulated path prefix; instance_id/workflow_name are the *root* values.
        hitl = WorkflowHitlContext.from_context(
            _ctx({
                "instance_id": "root-inst",
                "workflow_name": "moderation_pipeline",
                "request_path_prefix": "review_sub~0~",
            }),
            base_url="https://app.example.com",
        )
        assert hitl is not None
        assert hitl.request_path_prefix == "review_sub~0~"
        # A bare request id is qualified back to the top-level instance automatically.
        assert hitl.build_respond_url("req-9") == (
            "https://app.example.com/api/workflow/moderation_pipeline/respond/root-inst/review_sub~0~req-9"
        )

    def test_deep_prefix(self) -> None:
        hitl = WorkflowHitlContext.from_context(
            _ctx({
                "instance_id": "root-inst",
                "workflow_name": "wf",
                "request_path_prefix": "outer~2~inner~1~",
            }),
            base_url="https://app.example.com",
        )
        assert hitl is not None
        assert hitl.build_respond_url("rid") == (
            "https://app.example.com/api/workflow/wf/respond/root-inst/outer~2~inner~1~rid"
        )

    def test_absent_prefix_defaults_empty(self) -> None:
        # Top-level metadata may omit the key; the bare id is used unqualified.
        hitl = WorkflowHitlContext.from_context(
            _ctx({"instance_id": "inst-1", "workflow_name": "wf"}),
            base_url="https://app.example.com",
        )
        assert hitl is not None
        assert hitl.request_path_prefix == ""
        assert hitl.build_respond_url("rid") == ("https://app.example.com/api/workflow/wf/respond/inst-1/rid")


def _ctx_with_pending(pending: dict[str, Any] | None, *, has_getter: bool = True) -> SimpleNamespace:
    """Build a ctx whose runner context returns the given pending request-info events."""
    if not has_getter:
        return SimpleNamespace(_runner_context=SimpleNamespace())

    async def _get() -> dict[str, Any]:
        return pending or {}

    return SimpleNamespace(_runner_context=SimpleNamespace(get_pending_request_info_events=_get))


class TestPendingRequestId:
    """Reading back the framework-generated request id after request_info."""

    async def test_returns_latest_request_id(self) -> None:
        # Dicts preserve insertion order; the most recently emitted request wins.
        ctx = _ctx_with_pending({"r1": object(), "r2": object()})
        assert await WorkflowHitlContext.pending_request_id(ctx) == "r2"

    async def test_returns_single_request_id(self) -> None:
        ctx = _ctx_with_pending({"only-one": object()})
        assert await WorkflowHitlContext.pending_request_id(ctx) == "only-one"

    async def test_returns_none_when_no_pending(self) -> None:
        ctx = _ctx_with_pending({})
        assert await WorkflowHitlContext.pending_request_id(ctx) is None

    async def test_returns_none_when_no_runner_context(self) -> None:
        assert await WorkflowHitlContext.pending_request_id(SimpleNamespace()) is None

    async def test_returns_none_when_getter_absent(self) -> None:
        # A runner context that doesn't track request-info events degrades to None.
        ctx = _ctx_with_pending(None, has_getter=False)
        assert await WorkflowHitlContext.pending_request_id(ctx) is None
