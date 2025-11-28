# Copyright (c) Microsoft. All rights reserved.

"""Type definitions for AG-UI integration."""

from typing import Any, TypedDict

from pydantic import BaseModel, Field


class PredictStateConfig(TypedDict):
    """Configuration for predictive state updates."""

    state_key: str
    tool: str
    tool_argument: str | None


class RunMetadata(TypedDict):
    """Metadata for agent run."""

    run_id: str
    thread_id: str
    predict_state: list[PredictStateConfig] | None


class AgentState(TypedDict):
    """Base state for AG-UI agents."""

    messages: list[Any] | None


class AGUIRequest(BaseModel):
    """Request model for AG-UI endpoints."""

    messages: list[dict[str, Any]] = Field(
        ...,
        description="AG-UI format messages array",
    )
    run_id: str | None = Field(
        None,
        description="Optional run identifier for tracking",
    )
    thread_id: str | None = Field(
        None,
        description="Optional thread identifier for conversation context",
    )
    state: dict[str, Any] | None = Field(
        None,
        description="Optional shared state for agentic generative UI",
    )
