# Copyright (c) Microsoft. All rights reserved.

"""Fixtures for Foundry Hosting tests."""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from agent_framework_foundry_hosting import (
        InvocationsHostServer,
        InvocationsWorkflowHostServer,
        ResponsesHostServer,
        ResponsesWorkflowHostServer,
    )


@pytest.fixture(autouse=True)
def disable_agentserver_external_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep package regressions offline, including SDK resource detection and exporters."""
    monkeypatch.setattr("azure.ai.agentserver.core._tracing._configure_tracing", lambda **kwargs: None)


@pytest.fixture(autouse=True)
def isolate_local_agentserver_state_root(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test attempt an independent local AgentServer state root."""
    # pytest-retry bypasses the report hooks needed by tmp_path's teardown bookkeeping.
    with TemporaryDirectory(prefix="agentserver-test-") as directory:
        monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(Path(directory) / "agentserver-state"))
        yield


@pytest.fixture(
    params=[
        "ResponsesHostServer",
        "ResponsesWorkflowHostServer",
        "InvocationsHostServer",
        "InvocationsWorkflowHostServer",
    ]
)
def host_type(
    request: pytest.FixtureRequest,
) -> type[ResponsesHostServer | ResponsesWorkflowHostServer | InvocationsHostServer | InvocationsWorkflowHostServer]:
    import agent_framework_foundry_hosting

    return getattr(agent_framework_foundry_hosting, request.param)


@pytest.fixture
def host_constructor(
    host_type: type[
        ResponsesHostServer | ResponsesWorkflowHostServer | InvocationsHostServer | InvocationsWorkflowHostServer
    ],
) -> partial[Any]:
    settings: dict[str, Any]
    if "Workflow" in host_type.__name__:
        settings = {
            "workflow": lambda request: pytest.fail("Construction must not invoke the workflow factory."),
            "parse_input": lambda request: pytest.fail("Construction must not invoke the parser."),
        }
    else:
        settings = {"agent": lambda request: pytest.fail("Construction must not invoke the agent factory.")}
    return partial(host_type, **settings)
