# Copyright (c) Microsoft. All rights reserved.

"""Custom OpenAI-compatible event types for Agent Framework extensions.

These are custom event types that extend beyond the standard OpenAI Responses API
to support Agent Framework specific features like workflows and traces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# Custom Agent Framework OpenAI event types for structured data


# Agent lifecycle events - simple and clear
class AgentStartedEvent:
    """Event emitted when an agent starts execution."""

    pass


class AgentCompletedEvent:
    """Event emitted when an agent completes execution successfully."""

    pass


@dataclass
class AgentFailedEvent:
    """Event emitted when an agent fails during execution."""

    error: Exception | None = None


class ExecutorActionItem(BaseModel):
    """Custom item type for workflow executor actions.

    This is a DevUI-specific extension to represent workflow executors as output items.
    Since OpenAI's ResponseOutputItemAddedEvent only accepts specific item types,
    and executor actions are not part of the standard, we need this custom type.
    """

    type: Literal["executor_action"] = "executor_action"
    id: str
    executor_id: str
    status: Literal["in_progress", "completed", "failed", "cancelled"] = "in_progress"
    metadata: dict[str, Any] | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None


class CustomResponseOutputItemAddedEvent(BaseModel):
    """Custom version of ResponseOutputItemAddedEvent that accepts any item type.

    This allows us to emit executor action items while maintaining the same
    event structure as OpenAI's standard.
    """

    type: Literal["response.output_item.added"] = "response.output_item.added"
    output_index: int
    sequence_number: int
    item: dict[str, Any] | ExecutorActionItem | Any  # Flexible item type


class CustomResponseOutputItemDoneEvent(BaseModel):
    """Custom version of ResponseOutputItemDoneEvent that accepts any item type.

    This allows us to emit executor action items while maintaining the same
    event structure as OpenAI's standard.
    """

    type: Literal["response.output_item.done"] = "response.output_item.done"
    output_index: int
    sequence_number: int
    item: dict[str, Any] | ExecutorActionItem | Any  # Flexible item type


class ResponseWorkflowEventComplete(BaseModel):
    """Complete workflow event data.

    DevUI extension for workflow execution events (debugging/observability).
    Uses past-tense 'completed' to follow OpenAI's event naming pattern.

    Workflow events are shown in the debug panel for monitoring execution flow,
    not in main chat. Use response.output_item.added for user-facing content.
    """

    type: Literal["response.workflow_event.completed"] = "response.workflow_event.completed"
    data: dict[str, Any]  # Complete event data, not delta
    executor_id: str | None = None
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseTraceEventComplete(BaseModel):
    """Complete trace event data.

    DevUI extension for non-displayable debugging/metadata events.
    Uses past-tense 'completed' to follow OpenAI's event naming pattern
    (e.g., response.completed, response.output_item.added).

    Trace events are shown in the Traces debug panel, not in main chat.
    Use response.output_item.added for user-facing content.
    """

    type: Literal["response.trace.completed"] = "response.trace.completed"
    data: dict[str, Any]  # Complete trace data, not delta
    span_id: str | None = None
    item_id: str
    output_index: int = 0
    sequence_number: int


class ResponseFunctionResultComplete(BaseModel):
    """DevUI extension: Stream function execution results.

    This is a DevUI extension because:
    - OpenAI Responses API doesn't stream function results (clients execute functions)
    - Agent Framework executes functions server-side, so we stream results for debugging visibility
    - ResponseFunctionToolCallOutputItem exists in OpenAI SDK but isn't in ResponseOutputItem union
      (it's for Conversations API input, not Responses API streaming output)

    This event provides the same structure as OpenAI's function output items but wrapped
    in a custom event type since standard events don't support streaming function results.
    """

    type: Literal["response.function_result.complete"] = "response.function_result.complete"
    call_id: str
    output: str
    status: Literal["in_progress", "completed", "incomplete"]
    item_id: str
    output_index: int = 0
    sequence_number: int
    timestamp: str | None = None  # Optional timestamp for UI display


class ResponseRequestInfoEvent(BaseModel):
    """DevUI extension: Workflow requests human input.

    This is a DevUI extension because:
    - OpenAI Responses API doesn't have a concept of workflow human-in-the-loop pausing
    - Agent Framework workflows can pause via RequestInfoExecutor to collect external information
    - Clients need to render forms and submit responses to continue workflow execution

    When a workflow emits this event, it enters IDLE_WITH_PENDING_REQUESTS state.
    Client should render a form based on request_schema and submit responses via
    a new request with workflow_hil_response content type.
    """

    type: Literal["response.request_info.requested"] = "response.request_info.requested"
    request_id: str
    """Unique identifier for correlating this request with the response."""

    source_executor_id: str
    """ID of the executor that is waiting for this response."""

    request_type: str
    """Fully qualified type name of the request (e.g., 'module.path:ClassName')."""

    request_data: dict[str, Any]
    """Current data from the RequestInfoMessage (may contain defaults/context)."""

    request_schema: dict[str, Any]
    """JSON schema describing the request data structure (what the workflow is asking about)."""

    response_schema: dict[str, Any] | None = None
    """JSON schema describing the expected response structure for form rendering (what user should provide)."""

    item_id: str
    """OpenAI item ID for correlation."""

    output_index: int = 0
    """Output index for OpenAI compatibility."""

    sequence_number: int
    """Sequence number for ordering events."""

    timestamp: str
    """ISO timestamp when the request was made."""


# DevUI Output Content Types - for agent-generated media/data
# These extend ResponseOutputItem to support rich content outputs that OpenAI's API doesn't natively support


class ResponseOutputImage(BaseModel):
    """DevUI extension: Agent-generated image output.

    This is a DevUI extension because:
    - OpenAI Responses API only supports text output in ResponseOutputMessage.content
    - ImageGenerationCall exists but is for tool calls (generating images), not returning existing images
    - Agent Framework agents can return images via DataContent/UriContent that need proper display

    This type allows images to be displayed inline in chat rather than hidden in trace logs.
    """

    id: str
    """The unique ID of the image output."""

    image_url: str
    """The URL or data URI of the image (e.g., data:image/png;base64,...)"""

    type: Literal["output_image"] = "output_image"
    """The type of the output. Always `output_image`."""

    alt_text: str | None = None
    """Optional alt text for accessibility."""

    mime_type: str = "image/png"
    """The MIME type of the image (e.g., image/png, image/jpeg)."""


class ResponseOutputFile(BaseModel):
    """DevUI extension: Agent-generated file output.

    This is a DevUI extension because:
    - OpenAI Responses API only supports text output in ResponseOutputMessage.content
    - Agent Framework agents can return files via DataContent/UriContent that need proper display
    - Supports PDFs, audio files, and other media types

    This type allows files to be displayed inline in chat with appropriate renderers.
    """

    id: str
    """The unique ID of the file output."""

    filename: str
    """The filename (used to determine rendering and download)."""

    type: Literal["output_file"] = "output_file"
    """The type of the output. Always `output_file`."""

    file_url: str | None = None
    """Optional URL to the file."""

    file_data: str | None = None
    """Optional base64-encoded file data."""

    mime_type: str = "application/octet-stream"
    """The MIME type of the file (e.g., application/pdf, audio/mp3)."""


class ResponseOutputData(BaseModel):
    """DevUI extension: Agent-generated generic data output.

    This is a DevUI extension because:
    - OpenAI Responses API only supports text output in ResponseOutputMessage.content
    - Agent Framework agents can return arbitrary structured data that needs display
    - Useful for debugging and displaying non-text content

    This type allows generic data to be displayed inline in chat.
    """

    id: str
    """The unique ID of the data output."""

    data: str
    """The data payload (string representation)."""

    type: Literal["output_data"] = "output_data"
    """The type of the output. Always `output_data`."""

    mime_type: str
    """The MIME type of the data."""

    description: str | None = None
    """Optional description of the data."""


# Agent Framework extension fields
class AgentFrameworkExtraBody(BaseModel):
    """Agent Framework specific routing fields for OpenAI requests."""

    entity_id: str
    # input_data removed - now using standard input field for all data

    model_config = ConfigDict(extra="allow")


# Agent Framework Request Model - Extending real OpenAI types
class AgentFrameworkRequest(BaseModel):
    """OpenAI ResponseCreateParams with Agent Framework routing.

    This properly extends the real OpenAI API request format.
    - Uses 'model' field as entity_id (agent/workflow name)
    - Uses 'conversation' field for conversation context (OpenAI standard)
    """

    # All OpenAI fields from ResponseCreateParams
    model: str | None = None
    input: str | list[Any] | dict[str, Any]  # ResponseInputParam + dict for workflow structured input
    stream: bool | None = False

    # OpenAI conversation parameter (standard!)
    conversation: str | dict[str, Any] | None = None  # Union[str, {"id": str}]

    # Common OpenAI optional fields
    instructions: str | None = None
    metadata: dict[str, Any] | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    tools: list[dict[str, Any]] | None = None

    # Reasoning parameters (for o-series models)
    reasoning: dict[str, Any] | None = None  # {"effort": "low" | "medium" | "high" | "minimal"}

    # Optional extra_body for advanced use cases
    extra_body: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    def get_entity_id(self) -> str | None:
        """Get entity_id from metadata.entity_id.

        In DevUI, entity_id is specified in metadata for routing.
        """
        if self.metadata:
            return self.metadata.get("entity_id")
        return None

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


class MetaResponse(BaseModel):
    """Server metadata response for /meta endpoint.

    Provides information about the DevUI server configuration and capabilities.
    """

    ui_mode: Literal["developer", "user"] = "developer"
    """UI interface mode - 'developer' shows debug tools, 'user' shows simplified interface."""

    version: str
    """DevUI version string."""

    framework: str = "agent_framework"
    """Backend framework identifier."""

    runtime: Literal["python", "dotnet"] = "python"
    """Backend runtime/language - 'python' or 'dotnet' for deployment guides and feature availability."""

    capabilities: dict[str, bool] = {}
    """Server capabilities (e.g., tracing, openai_proxy)."""

    auth_required: bool = False
    """Whether the server requires Bearer token authentication."""


# Export all custom types
__all__ = [
    "AgentFrameworkRequest",
    "MetaResponse",
    "OpenAIError",
    "ResponseFunctionResultComplete",
    "ResponseOutputData",
    "ResponseOutputFile",
    "ResponseOutputImage",
    "ResponseTraceEvent",
    "ResponseTraceEventComplete",
    "ResponseWorkflowEventComplete",
]
