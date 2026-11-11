# Copyright (c) Microsoft. All rights reserved.

"""Verify explicit framework settings and the unvalidated AgentServer constructor boundary."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

import pytest
from azure.ai.agentserver.responses import ResponsesServerOptions


@pytest.mark.parametrize(
    "settings",
    [
        None,
        {},
        MappingProxyType({}),
        {"default_model": "sdk-owned", "custom_sdk_setting": {"value": object()}},
        MappingProxyType({"steerable_conversations": True, "custom_sdk_setting": object()}),
    ],
)
def test_agent_server_kwargs_are_forwarded_without_validation_or_mutation(
    host_type: type[Any], host_constructor: partial[Any], settings: Mapping[str, Any] | None
) -> None:
    before = dict(settings or {})
    sdk_host = host_type.__bases__[0]
    with (
        patch.object(sdk_host, "__init__", side_effect=RuntimeError("SDK construction failed")) as initialize,
        pytest.raises(RuntimeError, match="SDK construction failed"),
    ):
        host_constructor(agent_server_kwargs=settings)
    initialize.assert_called_once()
    forwarded = initialize.call_args.kwargs
    assert "agent_server_kwargs" not in forwarded
    for key, value in before.items():
        assert forwarded[key] is value
    assert dict(settings or {}) == before


@pytest.mark.parametrize("log_level", [None, "DEBUG"])
def test_log_level_is_forwarded_unchanged_to_agent_server(
    host_type: type[Any], host_constructor: partial[Any], log_level: str | None
) -> None:
    with (
        patch.object(host_type.__bases__[0], "__init__", side_effect=RuntimeError("SDK boundary")) as initialize,
        pytest.raises(RuntimeError, match="SDK boundary"),
    ):
        host_constructor(log_level=log_level)
    assert initialize.call_args.kwargs["log_level"] == log_level


@pytest.mark.parametrize("interval", [True, 1.5, "5", 0, -1])
def test_invalid_explicit_heartbeats_fail_before_sdk_construction(
    host_type: type[Any], host_constructor: partial[Any], interval: Any
) -> None:
    with (
        patch.object(host_type.__bases__[0], "__init__") as initialize,
        pytest.raises((TypeError, ValueError), match="sse_keep_alive_interval_seconds"),
    ):
        host_constructor(sse_keep_alive_interval_seconds=interval)
    initialize.assert_not_called()


@pytest.mark.parametrize("host_type", ["ResponsesHostServer", "ResponsesWorkflowHostServer"], indirect=True)
@pytest.mark.parametrize(
    "settings",
    [
        {"shutdown_grace_period_seconds": True},
        {"shutdown_grace_period_seconds": 0},
        {"shutdown_grace_period_seconds": -1},
        {"resilient_background": None},
        {"resilient_background": 1},
    ],
)
def test_invalid_responses_settings_fail_before_sdk_construction(
    host_type: type[Any], host_constructor: partial[Any], settings: dict[str, Any]
) -> None:
    with (
        patch.object(host_type.__bases__[0], "__init__") as initialize,
        pytest.raises((TypeError, ValueError), match=next(iter(settings))),
    ):
        host_constructor(**settings)
    initialize.assert_not_called()


@pytest.mark.parametrize("host_type", ["ResponsesHostServer"], indirect=True)
@pytest.mark.parametrize("limit", [None, 3])
def test_history_limit_inherits_sdk_default_or_sets_an_explicit_cap(
    host_type: type[Any], host_constructor: partial[Any], monkeypatch: pytest.MonkeyPatch, limit: int | None
) -> None:
    monkeypatch.setenv("DEFAULT_FETCH_HISTORY_ITEM_COUNT", "7")
    with (
        patch.object(host_type.__bases__[0], "__init__", side_effect=RuntimeError("SDK boundary")) as initialize,
        pytest.raises(RuntimeError, match="SDK boundary"),
    ):
        host_constructor(max_history_items=limit)
    options = initialize.call_args.kwargs["options"]
    expected = ResponsesServerOptions().default_fetch_history_count if limit is None else limit
    assert options.default_fetch_history_count == expected
    assert options.default_model is None
    assert options.steerable_conversations is False


@pytest.mark.parametrize("host_type", ["ResponsesHostServer", "ResponsesWorkflowHostServer"], indirect=True)
def test_response_operational_settings_reach_the_sdk(host_type: type[Any], host_constructor: partial[Any]) -> None:
    settings: dict[str, Any] = {
        "sse_keep_alive_interval_seconds": 3,
        "shutdown_grace_period_seconds": 2,
        "resilient_background": True,
    }
    if host_type.__name__ == "ResponsesHostServer":
        settings.update(history_source="inference_service", background_source="inference_service")
    with (
        patch.object(host_type.__bases__[0], "__init__", side_effect=RuntimeError("SDK boundary")) as initialize,
        pytest.raises(RuntimeError, match="SDK boundary"),
    ):
        host_constructor(**settings)
    options = initialize.call_args.kwargs["options"]
    assert options.sse_keep_alive_interval_seconds == 3
    assert options.shutdown_grace_period_seconds == 2
    assert options.resilient_background is True


@pytest.mark.parametrize("host_type", ["InvocationsHostServer", "InvocationsWorkflowHostServer"], indirect=True)
@pytest.mark.parametrize("environment, explicit, expected", [(None, None, 0), ("3", None, 3), ("3", 5, 5)])
def test_invocations_heartbeat_configuration_is_per_host(
    host_constructor: partial[Any],
    monkeypatch: pytest.MonkeyPatch,
    environment: str | None,
    explicit: int | None,
    expected: int,
) -> None:
    if environment is None:
        monkeypatch.delenv("SSE_KEEPALIVE_INTERVAL", raising=False)
    else:
        monkeypatch.setenv("SSE_KEEPALIVE_INTERVAL", environment)
    configured = host_constructor(sse_keep_alive_interval_seconds=explicit)
    inherited = host_constructor()
    assert configured.config.sse_keepalive_interval == expected
    assert inherited.config.sse_keepalive_interval == int(environment or "0")
    assert configured.config is not inherited.config


@pytest.mark.parametrize("host_type", ["InvocationsHostServer"], indirect=True)
def test_legacy_agent_stream_cannot_enable_heartbeats(
    host_constructor: partial[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SSE_KEEPALIVE_INTERVAL", "3")
    with pytest.warns(DeprecationWarning):
        server = host_constructor(legacy_wire_format=True)
    assert server.config.sse_keepalive_interval == 0
    with pytest.raises(ValueError, match="framed SSE"):
        host_constructor(legacy_wire_format=True, sse_keep_alive_interval_seconds=1)


@pytest.mark.parametrize("host_type", ["ResponsesHostServer"], indirect=True)
@pytest.mark.parametrize(
    "settings",
    [
        {"max_history_items": True},
        {"max_history_items": 1.5},
        {"max_history_items": 0},
        {"max_history_items": -1},
        {"max_history_items": 3, "history_source": "agent_managed"},
        {"max_history_items": 3, "history_source": "inference_service"},
        {"resilient_background": True},
    ],
)
def test_agent_setting_applicability_fails_before_sdk_construction(
    host_type: type[Any], host_constructor: partial[Any], settings: dict[str, Any]
) -> None:
    with (
        patch.object(host_type.__bases__[0], "__init__") as initialize,
        pytest.raises((TypeError, ValueError), match=next(iter(settings))),
    ):
        host_constructor(**settings)
    initialize.assert_not_called()
