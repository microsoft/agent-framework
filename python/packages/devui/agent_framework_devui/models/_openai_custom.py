# Copyright (c) Microsoft. All rights reserved.

"""Custom OpenAI-compatible event types for Agent Framework extensions.

These are custom event types that extend beyond the standard OpenAI Responses API
to support Agent Framework specific features like workflows, traces, and function results.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# Custom Agent Framework OpenAI event types for structured data


class ResponseWorkflowEventDelta(BaseModel):
    """Structured workflow event with completion tracking."""

    type: Literal["response.workflow_event.delta"] = "response.workflow_event.delta"
    delta: dict[str, Any]
    executor_id: str | None = None
    is_complete: bool = False  # Track if this is the final part
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseWorkflowEventComplete(BaseModel):
    """Complete workflow event data."""

    type: Literal["response.workflow_event.complete"] = "response.workflow_event.complete"
    data: dict[str, Any]  # Complete event data, not delta
    executor_id: str | None = None
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseFunctionResultDelta(BaseModel):
    """Structured function result with completion tracking."""

    type: Literal["response.function_result.delta"] = "response.function_result.delta"
    delta: dict[str, Any]
    call_id: str
    is_complete: bool = False
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseFunctionResultComplete(BaseModel):
    """Complete function result data."""

    type: Literal["response.function_result.complete"] = "response.function_result.complete"
    data: dict[str, Any]  # Complete function result data, not delta
    call_id: str
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseTraceEventDelta(BaseModel):
    """Structured trace event with completion tracking."""

    type: Literal["response.trace.delta"] = "response.trace.delta"
    delta: dict[str, Any]
    span_id: str | None = None
    is_complete: bool = False
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseTraceEventComplete(BaseModel):
    """Complete trace event data."""

    type: Literal["response.trace.complete"] = "response.trace.complete"
    data: dict[str, Any]  # Complete trace data, not delta
    span_id: str | None = None
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseUsageEventDelta(BaseModel):
    """Structured usage event with completion tracking."""

    type: Literal["response.usage.delta"] = "response.usage.delta"
    delta: dict[str, Any]
    is_complete: bool = False
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseUsageEventComplete(BaseModel):
    """Complete usage event data."""

    type: Literal["response.usage.complete"] = "response.usage.complete"
    data: dict[str, Any]  # Complete usage data, not delta
    item_id: str
    output_index: int = 0
    sequence_number: int


# Agent Framework extension fields
class AgentFrameworkExtraBody(BaseModel):
    """Agent Framework specific routing fields for OpenAI requests."""

    entity_id: str
    input_data: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


# Agent Framework Request Model - Extending real OpenAI types
class AgentFrameworkRequest(BaseModel):
    """OpenAI ResponseCreateParams with Agent Framework routing.

    This properly extends the real OpenAI API request format.
    - Uses 'model' field as entity_id (agent/workflow name)
    - Uses 'conversation' field for conversation context (OpenAI standard)
    """

    # All OpenAI fields from ResponseCreateParams
    model: str  # Used as entity_id in DevUI!
    input: str | list[Any]  # ResponseInputParam
    stream: bool | None = False

    # OpenAI conversation parameter (standard!)
    conversation: str | dict[str, Any] | None = None  # Union[str, {"id": str}]

    # Common OpenAI optional fields
    instructions: str | None = None
    metadata: dict[str, Any] | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None

    # Optional extra_body for advanced use cases
    extra_body: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    def get_entity_id(self) -> str:
        """Get entity_id from model field.

        In DevUI, model IS the entity_id (agent/workflow name).
        Simple and clean!
        """
        return self.model

    def get_conversation_id(self) -> str | None:
        """Extract conversation_id from conversation parameter.

        Supports both string and object forms:
        - conversation: "conv_123"
        - conversation: {"id": "conv_123"}
        """
        if isinstance(self.conversation, str):
            return self.conversation
        if isinstance(self.conversation, dict):
            return self.conversation.get("id")
        return None

    def to_openai_params(self) -> dict[str, Any]:
        """Convert to dict for OpenAI client compatibility."""
        return self.model_dump(exclude_none=True)


# Error handling
class ResponseTraceEvent(BaseModel):
    """Trace event for execution tracing."""

    type: Literal["trace_event"] = "trace_event"
    data: dict[str, Any]
    timestamp: str


class OpenAIError(BaseModel):
    """OpenAI standard error response model."""

    error: dict[str, Any]

    @classmethod
    def create(cls, message: str, type: str = "invalid_request_error", code: str | None = None) -> OpenAIError:
        """Create a standard OpenAI error response."""
        error_data = {"message": message, "type": type, "code": code}
        return cls(error=error_data)

    def to_dict(self) -> dict[str, Any]:
        """Return the error payload as a plain mapping."""
        return {"error": dict(self.error)}

    def to_json(self) -> str:
        """Return the error payload serialized to JSON."""
        return self.model_dump_json()


# Export all custom types
__all__ = [
    "AgentFrameworkRequest",
    "OpenAIError",
    "ResponseFunctionResultComplete",
    "ResponseFunctionResultDelta",
    "ResponseTraceEvent",
    "ResponseTraceEventComplete",
    "ResponseTraceEventDelta",
    "ResponseUsageEventComplete",
    "ResponseUsageEventDelta",
    "ResponseWorkflowEventComplete",
    "ResponseWorkflowEventDelta",
]
