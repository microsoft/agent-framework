# Copyright (c) Microsoft. All rights reserved.

"""Exact copies of OpenAI types for compatibility without OpenAI dependency.

Types copied from openai==1.107.1 (2025-01-15) to avoid heavy dependency.
These are exact copies to maintain compatibility with OpenAI Responses API.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

# Base types and utilities


class ResponseTextDeltaEvent(BaseModel):
    """Response text delta event."""
    type: Literal["response.output_text.delta"] = "response.output_text.delta"
    item_id: str
    output_index: int
    content_index: int
    delta: str
    sequence_number: int
    logprobs: Optional[List[Any]] = None


class ResponseReasoningTextDeltaEvent(BaseModel):
    """Response reasoning text delta event."""
    type: Literal["response.reasoning_text.delta"] = "response.reasoning_text.delta"
    item_id: str
    output_index: int
    content_index: int
    delta: str
    sequence_number: int


class ResponseFunctionCallArgumentsDeltaEvent(BaseModel):
    """Response function call arguments delta event."""
    type: Literal["response.function_call_arguments.delta"] = "response.function_call_arguments.delta"
    item_id: str
    output_index: int
    delta: str
    sequence_number: int


class ResponseErrorEvent(BaseModel):
    """Response error event."""
    type: Literal["error"] = "error"
    message: str
    code: Optional[str] = None
    param: Optional[str] = None
    sequence_number: int


class ResponseOutputText(BaseModel):
    """Response output text."""
    type: Literal["output_text"] = "output_text"
    text: str
    annotations: List[Any] = Field(default_factory=list)


class ResponseOutputMessage(BaseModel):
    """Response output message."""
    type: Literal["message"] = "message"
    role: str
    content: List[ResponseOutputText]
    id: str
    status: str


class InputTokensDetails(BaseModel):
    """Input tokens details."""
    cached_tokens: int = 0


class OutputTokensDetails(BaseModel):
    """Output tokens details."""
    reasoning_tokens: int = 0


class ResponseUsage(BaseModel):
    """Response usage information."""
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_tokens_details: InputTokensDetails
    output_tokens_details: OutputTokensDetails


class Response(BaseModel):
    """OpenAI Response object."""
    id: str
    object: Literal["response"] = "response"
    created_at: float
    model: str
    output: List[ResponseOutputMessage]
    usage: ResponseUsage
    parallel_tool_calls: bool = False
    tool_choice: str = "none"
    tools: List[Any] = Field(default_factory=list)


# Type aliases for compatibility
OpenAIResponse = Response

# Union types for streaming
ResponseStreamEvent = Union[
    ResponseTextDeltaEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseErrorEvent
]


# Additional parameter types
class ResponseInputParam(BaseModel):
    """Response input parameter."""
    type: str
    value: Any


class ResponsesModel(BaseModel):
    """Responses model configuration."""
    model: str


class Metadata(BaseModel):
    """Metadata for responses."""
    data: Dict[str, Any] = Field(default_factory=dict)


class ToolParam(BaseModel):
    """Tool parameter configuration."""
    type: str
    function: Optional[Dict[str, Any]] = None


# Export all types
__all__ = [
    "InputTokensDetails",
    "Metadata",
    "OpenAIResponse",
    "OutputTokensDetails",
    "Response",
    "ResponseErrorEvent",
    "ResponseFunctionCallArgumentsDeltaEvent",
    "ResponseInputParam",
    "ResponseOutputMessage",
    "ResponseOutputText",
    "ResponseReasoningTextDeltaEvent",
    "ResponseStreamEvent",
    "ResponseTextDeltaEvent",
    "ResponseUsage",
    "ResponsesModel",
    "ToolParam"
]
