# Copyright (c) Microsoft. All rights reserved.

"""Custom OpenAI-compatible event types for Agent Framework extensions.

These are custom event types that extend beyond the standard OpenAI Responses API
to support Agent Framework specific features like workflows, traces, and function results.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

# Custom Agent Framework OpenAI event types for structured data


class ResponseWorkflowEventDelta(BaseModel):
    """Structured workflow event with completion tracking."""
    type: Literal["response.workflow_event.delta"] = "response.workflow_event.delta"
    delta: Dict[str, Any]
    executor_id: Optional[str] = None
    is_complete: bool = False  # Track if this is the final part
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseWorkflowEventComplete(BaseModel):
    """Complete workflow event data."""
    type: Literal["response.workflow_event.complete"] = "response.workflow_event.complete"
    data: Dict[str, Any]  # Complete event data, not delta
    executor_id: Optional[str] = None
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseFunctionResultDelta(BaseModel):
    """Structured function result with completion tracking."""
    type: Literal["response.function_result.delta"] = "response.function_result.delta"
    delta: Dict[str, Any]
    call_id: str
    is_complete: bool = False
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseFunctionResultComplete(BaseModel):
    """Complete function result data."""
    type: Literal["response.function_result.complete"] = "response.function_result.complete"
    data: Dict[str, Any]  # Complete function result data, not delta
    call_id: str
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseTraceEventDelta(BaseModel):
    """Structured trace event with completion tracking."""
    type: Literal["response.trace.delta"] = "response.trace.delta"
    delta: Dict[str, Any]
    span_id: Optional[str] = None
    is_complete: bool = False
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseTraceEventComplete(BaseModel):
    """Complete trace event data."""
    type: Literal["response.trace.complete"] = "response.trace.complete"
    data: Dict[str, Any]  # Complete trace data, not delta
    span_id: Optional[str] = None
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseUsageEventDelta(BaseModel):
    """Structured usage event with completion tracking."""
    type: Literal["response.usage.delta"] = "response.usage.delta"
    delta: Dict[str, Any]
    is_complete: bool = False
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseUsageEventComplete(BaseModel):
    """Complete usage event data."""
    type: Literal["response.usage.complete"] = "response.usage.complete"
    data: Dict[str, Any]  # Complete usage data, not delta
    item_id: str
    output_index: int = 0
    sequence_number: int


# Agent Framework Request Model
class AgentFrameworkRequest(BaseModel):
    """Extended OpenAI Responses API request with Agent Framework routing."""

    # Core OpenAI Responses API fields (match schema exactly)
    model: str  # Using str instead of ResponsesModel for simplicity
    input: str  # Simplified from ResponseInputParam
    stream: Optional[bool] = False

    # Optional OpenAI fields we want to support
    instructions: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # Simplified from Metadata type
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None  # Simplified from ToolParam

    # Agent Framework extension for entity routing
    extra_body: Optional[Dict[str, Any]] = None
    entity_id: Optional[str] = None  # Allow entity_id as top-level field

    def get_entity_id(self) -> Optional[str]:
        """Get entity_id from either top-level field or extra_body."""
        # Priority 1: Top-level entity_id field
        if self.entity_id:
            return self.entity_id

        # Priority 2: entity_id in extra_body
        if self.extra_body and "entity_id" in self.extra_body:
            entity_id = self.extra_body["entity_id"]
            return str(entity_id) if entity_id is not None else None

        return None

    def to_openai_params(self) -> Dict[str, Any]:
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
    data: Dict[str, Any]
    timestamp: str


class OpenAIError(BaseModel):
    """OpenAI standard error response model."""

    error: Dict[str, Any]

    @classmethod
    def create(cls, message: str, type: str = "invalid_request_error", code: Optional[str] = None) -> "OpenAIError":
        """Create a standard OpenAI error response."""
        error_data = {
            "message": message,
            "type": type,
            "code": code
        }
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
    "ResponseWorkflowEventDelta"
]
