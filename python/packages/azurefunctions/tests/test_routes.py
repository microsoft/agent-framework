# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the shared route-prefix resolution and HITL URL builders."""

# pyright: reportPrivateUsage=false

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agent_framework_azurefunctions import _routes

SCRIPT_ROOT_ENV = "AzureWebJobsScriptRoot"


@pytest.fixture(autouse=True)
def _reset_prefix_cache() -> Iterator[None]:
    """Keep the route-prefix cache from leaking across tests."""
    _routes.route_prefix.cache_clear()
    yield
    _routes.route_prefix.cache_clear()


def _write_host_json(directory: Path, config: dict[str, Any]) -> None:
    (directory / "host.json").write_text(json.dumps(config), encoding="utf-8")


class TestRoutePrefix:
    """Resolving ``extensions.http.routePrefix`` from host.json, with an ``api`` default."""

    def test_defaults_to_api_without_host_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(SCRIPT_ROOT_ENV, str(tmp_path))
        assert _routes.route_prefix() == "api"

    def test_defaults_to_api_when_prefix_absent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_host_json(tmp_path, {"version": "2.0", "extensions": {"http": {}}})
        monkeypatch.setenv(SCRIPT_ROOT_ENV, str(tmp_path))
        assert _routes.route_prefix() == "api"

    def test_reads_custom_prefix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_host_json(tmp_path, {"extensions": {"http": {"routePrefix": "gateway"}}})
        monkeypatch.setenv(SCRIPT_ROOT_ENV, str(tmp_path))
        assert _routes.route_prefix() == "gateway"

    def test_reads_empty_prefix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_host_json(tmp_path, {"extensions": {"http": {"routePrefix": ""}}})
        monkeypatch.setenv(SCRIPT_ROOT_ENV, str(tmp_path))
        assert _routes.route_prefix() == ""

    def test_strips_surrounding_slashes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_host_json(tmp_path, {"extensions": {"http": {"routePrefix": "/custom/"}}})
        monkeypatch.setenv(SCRIPT_ROOT_ENV, str(tmp_path))
        assert _routes.route_prefix() == "custom"

    def test_defaults_to_api_on_malformed_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "host.json").write_text("{ not json", encoding="utf-8")
        monkeypatch.setenv(SCRIPT_ROOT_ENV, str(tmp_path))
        assert _routes.route_prefix() == "api"

    def test_caches_first_read(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_host_json(tmp_path, {"extensions": {"http": {"routePrefix": "one"}}})
        monkeypatch.setenv(SCRIPT_ROOT_ENV, str(tmp_path))
        assert _routes.route_prefix() == "one"
        # A later host.json change is not observed within a running host.
        _write_host_json(tmp_path, {"extensions": {"http": {"routePrefix": "two"}}})
        assert _routes.route_prefix() == "one"


class TestUrlBuilders:
    """Respond/status URL shapes, parameterized by an explicit prefix."""

    def test_respond_url_default_prefix(self) -> None:
        assert (
            _routes.build_workflow_respond_url("https://h", "wf", "i", "r", prefix="api")
            == "https://h/api/workflow/wf/respond/i/r"
        )

    def test_respond_url_custom_prefix(self) -> None:
        assert (
            _routes.build_workflow_respond_url("https://h", "wf", "i", "r", prefix="gw")
            == "https://h/gw/workflow/wf/respond/i/r"
        )

    def test_respond_url_empty_prefix(self) -> None:
        assert (
            _routes.build_workflow_respond_url("https://h", "wf", "i", "r", prefix="")
            == "https://h/workflow/wf/respond/i/r"
        )

    def test_respond_url_template_placeholder(self) -> None:
        assert (
            _routes.build_workflow_respond_url("https://h", "wf", "i", "{requestId}", prefix="api")
            == "https://h/api/workflow/wf/respond/i/{requestId}"
        )

    def test_status_url_custom_prefix(self) -> None:
        assert (
            _routes.build_workflow_status_url("https://h", "wf", "i", prefix="gw")
            == "https://h/gw/workflow/wf/status/i"
        )

    def test_status_url_empty_prefix(self) -> None:
        assert _routes.build_workflow_status_url("https://h", "wf", "i", prefix="") == "https://h/workflow/wf/status/i"


class TestSplitRequestUrl:
    """Deriving base URL and route prefix from an incoming request URL."""

    def test_default_prefix(self) -> None:
        assert _routes.split_request_url("https://h:7071/api/workflow/wf/run") == ("https://h:7071", "api")

    def test_custom_prefix(self) -> None:
        assert _routes.split_request_url("https://h/gw/workflow/wf/status/i") == ("https://h", "gw")

    def test_empty_prefix(self) -> None:
        assert _routes.split_request_url("https://h/workflow/wf/run") == ("https://h", "")

    def test_multi_segment_prefix(self) -> None:
        assert _routes.split_request_url("https://h/a/b/workflow/wf/run") == ("https://h", "a/b")

    def test_no_workflow_segment(self) -> None:
        assert _routes.split_request_url("https://h/api/health") == ("https://h", "")

    def test_non_absolute_falls_back(self) -> None:
        assert _routes.split_request_url("/api/workflow/wf/run") == ("/api/workflow/wf/run", "")
