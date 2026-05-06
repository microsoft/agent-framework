# Copyright (c) Microsoft. All rights reserved.

"""Tests for WorkflowEvent factory methods, including the new intermediate factory
and the deprecation of WorkflowEvent.emit() / type='data'."""

from __future__ import annotations

import warnings

import pytest

from agent_framework import AgentResponse, Message
from agent_framework._workflows._events import WorkflowEvent


def test_workflow_event_intermediate_factory_creates_intermediate_event() -> None:
    """WorkflowEvent.intermediate(executor_id, data) creates a type='intermediate' event."""
    response = AgentResponse(messages=[Message(role="assistant", contents=["Hello"])])
    event: WorkflowEvent[AgentResponse] = WorkflowEvent.intermediate(executor_id="test", data=response)

    assert event.type == "intermediate"
    assert event.executor_id == "test"
    assert event.data is response


def test_workflow_event_emit_emits_deprecation_warning() -> None:
    """Calling WorkflowEvent.emit() raises a DeprecationWarning recommending the new path."""
    response = AgentResponse(messages=[Message(role="assistant", contents=["x"])])
    with pytest.warns(DeprecationWarning, match="intermediate"):
        WorkflowEvent.emit(executor_id="t", data=response)


def test_workflow_event_emit_still_returns_data_event() -> None:
    """During the deprecation window, emit() still produces a type='data' event."""
    response = AgentResponse(messages=[Message(role="assistant", contents=["x"])])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        event = WorkflowEvent.emit(executor_id="t", data=response)
    assert event.type == "data"
