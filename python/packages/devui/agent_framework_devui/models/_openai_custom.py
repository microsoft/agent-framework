# Copyright (c) Microsoft. All rights reserved.

"""Custom OpenAI-compatible event types for Agent Framework extensions.

These are custom event types that extend beyond the standard OpenAI Responses API
to support Agent Framework specific features like workflows, traces, and function results.
"""

from typing import Any, Literal

from pydantic import BaseModel

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


# Agent Framework Request Model
class AgentFrameworkRequest(BaseModel):
    """Extended OpenAI Responses API request with Agent Framework routing."""

    # Core OpenAI Responses API fields (match schema exactly)
    model: str  # Using str instead of ResponsesModel for simplicity
    input: str  # Simplified from ResponseInputParam
    stream: bool | None = False

    # Optional OpenAI fields we want to support
    instructions: str | None = None
    metadata: dict[str, Any] | None = None  # Simplified from Metadata type
    temperature: float | None = None
    max_output_tokens: int | None = None
    tools: list[dict[str, Any]] | None = None  # Simplified from ToolParam

    # Agent Framework extension for entity routing
    extra_body: dict[str, Any] | None = None
    entity_id: str | None = None  # Allow entity_id as top-level field

    def get_entity_id(self) -> str | None:
        """Get entity_id from either top-level field or extra_body."""
        # Priority 1: Top-level entity_id field
        if self.entity_id:
            return self.entity_id

        # Priority 2: entity_id in extra_body
        if self.extra_body and "entity_id" in self.extra_body:
            entity_id = self.extra_body["entity_id"]
            return str(entity_id) if entity_id is not None else None

        return None

    def to_openai_params(self) -> dict[str, Any]:
        """Convert to dict for OpenAI client compatibility."""
        data = self.model_dump(exclude={"extra_body", "entity_id"}, exclude_none=True)
        if self.extra_body:
            # Don't merge extra_body into main params to keep them separate
            data["extra_body"] = self.extra_body
        return data


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
    def create(cls, message: str, type: str = "invalid_request_error", code: str | None = None) -> "OpenAIError":
        """Create a standard OpenAI error response."""
        error_data = {"message": message, "type": type, "code": code}
        return cls(error=error_data)


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
