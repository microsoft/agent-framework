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
    """AG-UI request body schema for FastAPI endpoint.

    This model defines the structure of incoming requests to AG-UI endpoints,
    providing proper OpenAPI schema generation for Swagger UI documentation.

    Attributes:
        messages: List of AG-UI format messages for the conversation.
        run_id: Optional identifier for the current run.
        thread_id: Optional identifier for the conversation thread.
        state: Optional shared state dictionary for agentic generative UI.
    """

    messages: list[Any] = Field(
        default_factory=list,
        description="AG-UI format messages for the conversation",
    )
    run_id: str | None = Field(
        default=None,
        description="Optional identifier for the current run",
    )
    thread_id: str | None = Field(
        default=None,
        description="Optional identifier for the conversation thread",
    )
    state: dict[str, Any] | None = Field(
        default=None,
        description="Optional shared state for agentic generative UI",
    )

    model_config = {"extra": "allow"}
