# Copyright (c) Microsoft. All rights reserved.

"""Tests for WorkflowEvent factory methods and WorkflowEvent.emit() deprecation."""

from __future__ import annotations

import warnings

import pytest

from agent_framework import AgentResponse, Message
from agent_framework._workflows._events import WorkflowEvent


def test_workflow_event_output_selection_factories_are_not_public() -> None:
    """Callers should use ctx.yield_output(), not direct output/intermediate factories."""
    assert not hasattr(WorkflowEvent, "output")
    assert not hasattr(WorkflowEvent, "intermediate")


def test_workflow_event_emit_emits_deprecation_warning() -> None:
    """Calling WorkflowEvent.emit() raises a DeprecationWarning recommending the new path."""
    response = AgentResponse(messages=[Message(role="assistant", contents=["x"])])
    with pytest.warns(DeprecationWarning, match="yield_output"):
        WorkflowEvent.emit(executor_id="t", data=response)


def test_workflow_event_emit_still_returns_data_event() -> None:
    """During the deprecation window, emit() still produces a type='data' event."""
    response = AgentResponse(messages=[Message(role="assistant", contents=["x"])])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        event = WorkflowEvent.emit(executor_id="t", data=response)
    assert event.type == "data"
