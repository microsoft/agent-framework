# Copyright (c) Microsoft. All rights reserved.

"""Durable agent state management for Azure Durable Functions agents.

Implements the versioned durable-agent-entity-state.json schema using Pydantic models
for automatic serialization (to_dict) and deserialization (from_dict).

Key Features:
- Pydantic-based models with automatic camelCase ↔ snake_case conversion
- Polymorphic content types via $type discriminators
- Bidirectional conversion between durable state JSON and agent framework objects

State Hierarchy:
    DurableAgentState (root)
    └── DurableAgentStateData
        └── conversationHistory: List[DurableAgentStateEntry]
            ├── DurableAgentStateRequest (user/system messages)
            └── DurableAgentStateResponse (assistant messages + usage)
                └── messages: List[DurableAgentStateMessage]
                    └── contents: List[DurableAgentStateContent]
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any, ClassVar, Literal, Self

from agent_framework import (
    AgentRunResponse,
    BaseContent,
    ChatMessage,
    DataContent,
    ErrorContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedFileContent,
    HostedVectorStoreContent,
    TextContent,
    TextReasoningContent,
    UriContent,
    UsageContent,
    UsageDetails,
    get_logger,
)
from dateutil import parser as date_parser
from pydantic import BaseModel, ConfigDict, Field, Tag, field_validator
from pydantic.alias_generators import to_camel

from ._constants import ApiResponseFields
from ._models import RunRequest, serialize_response_format

logger = get_logger("agent_framework.azurefunctions.durable_agent_state")


def _parse_created_at(value: Any) -> datetime:
    """Normalize created_at values coming from persisted durable state."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        try:
            parsed = date_parser.parse(value)
            if isinstance(parsed, datetime):
                return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError):
            pass

    return datetime.now(tz=timezone.utc)


class DurableAgentStateModel(BaseModel):
    """Base Pydantic model for durable agent state classes.

    Provides:
    - Automatic camelCase ↔ snake_case field conversion
    - Forward compatibility (ignores unknown fields)
    - Inherited to_dict/from_dict methods
    """

    model_config = ConfigDict(
        alias_generator=to_camel,  # Auto-convert snake_case fields to camelCase in JSON
        populate_by_name=True,  # Allow using snake_case names in constructor
        extra="ignore",  # Ignore unknown fields for forward compatibility
        use_enum_values=True,  # Serialize enums as their values, not names
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict with camelCase keys, excluding None values."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from dict."""
        return cls.model_validate(data)


class DurableAgentStateContent(DurableAgentStateModel):
    """Base class for message content types.

    Subclasses must override `type` with a Literal value for $type discrimination.
    """

    type: str = Field(alias="$type")

    def to_ai_content(self) -> Any:
        """Convert to agent framework content object. Must be implemented by subclasses."""
        raise NotImplementedError

    @staticmethod
    def from_ai_content(content: Any) -> DurableAgentStateContent:
        """Factory: convert agent framework content to durable state content."""
        # Map AI content type to appropriate DurableAgentStateContent subclass
        if isinstance(content, DataContent):
            return DurableAgentStateDataContent.from_data_content(content)
        if isinstance(content, ErrorContent):
            return DurableAgentStateErrorContent.from_error_content(content)
        if isinstance(content, FunctionCallContent):
            return DurableAgentStateFunctionCallContent.from_function_call_content(content)
        if isinstance(content, FunctionResultContent):
            return DurableAgentStateFunctionResultContent.from_function_result_content(content)
        if isinstance(content, HostedFileContent):
            return DurableAgentStateHostedFileContent.from_hosted_file_content(content)
        if isinstance(content, HostedVectorStoreContent):
            return DurableAgentStateHostedVectorStoreContent.from_hosted_vector_store_content(content)
        if isinstance(content, TextContent):
            return DurableAgentStateTextContent.from_text_content(content)
        if isinstance(content, TextReasoningContent):
            return DurableAgentStateTextReasoningContent.from_text_reasoning_content(content)
        if isinstance(content, UriContent):
            return DurableAgentStateUriContent.from_uri_content(content)
        if isinstance(content, UsageContent):
            return DurableAgentStateUsageContent.from_usage_content(content)
        return DurableAgentStateUnknownContent.from_unknown_content(content)


class DurableAgentStateData(DurableAgentStateModel):
    """Container for conversation history and extension data within DurableAgentState."""

    conversation_history: list[
        Annotated[
            (
                Annotated[DurableAgentStateRequest, Tag("request")]
                | Annotated[DurableAgentStateResponse, Tag("response")]
            ),
            Field(discriminator="type"),
        ]
    ] = Field(default_factory=list)
    extension_data: dict[str, Any] | None = None


class DurableAgentState(DurableAgentStateModel):
    """Root container for durable agent state, persisted in Azure Durable Entities.

    Serializes to: {"schemaVersion": "...", "data": {"conversationHistory": [...]}}
    """

    # Durable Agent Schema version (ClassVar to prevent Pydantic from treating it as a field)
    SCHEMA_VERSION: ClassVar[str] = "1.1.0"

    schema_version: str = Field(default=SCHEMA_VERSION)
    data: DurableAgentStateData = Field(default_factory=DurableAgentStateData)

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> Self:
        """Restore state from dict. Returns empty state if schema version is missing."""
        schema_version = state.get("schemaVersion")
        if schema_version is None:
            logger.warning("Resetting state as it is incompatible with the current schema, all history will be lost")
            return cls()

        return super().from_dict(state)

    @property
    def message_count(self) -> int:
        """Get the count of conversation entries (requests + responses)."""
        return len(self.data.conversation_history)

    def try_get_agent_response(self, correlation_id: str) -> dict[str, Any] | None:
        """Find response by correlation_id. Returns API-formatted dict or None."""
        # Search through conversation history for a response with this correlationId
        for entry in self.data.conversation_history:
            if entry.correlation_id == correlation_id and isinstance(entry, DurableAgentStateResponse):
                # Found the entry, extract response data
                # Get the text content from assistant messages only
                content = "\n".join(message.text for message in entry.messages if message.text)

                return {
                    ApiResponseFields.CONTENT: content,
                    ApiResponseFields.MESSAGE_COUNT: self.message_count,
                    ApiResponseFields.CORRELATION_ID: correlation_id,
                }
        return None


class DurableAgentStateEntry(DurableAgentStateModel):
    """Base class for conversation history entries. Discriminated by $type field."""

    type: str = Field(alias="$type")
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    messages: list[DurableAgentStateMessage] = Field(default_factory=list)
    extension_data: dict[str, Any] | None = None

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_datetime(cls, v: Any) -> datetime:
        """Parse datetime from string or return existing datetime."""
        return _parse_created_at(v)


class DurableAgentStateRequest(DurableAgentStateEntry):
    """Request entry: user/system messages with optional response format specs."""

    type: Literal["request"] = Field(default="request", alias="$type")
    response_type: str | None = None
    response_schema: dict[str, Any] | None = None
    orchestration_id: str | None = None

    @staticmethod
    def from_run_request(request: RunRequest) -> DurableAgentStateRequest:
        """Create a DurableAgentStateRequest from a RunRequest."""
        return DurableAgentStateRequest(
            correlation_id=request.correlation_id,
            messages=[DurableAgentStateMessage.from_run_request(request)],
            created_at=datetime.now(tz=timezone.utc),
            response_type=request.request_response_format,
            response_schema=serialize_response_format(request.response_format),
            orchestration_id=request.orchestration_id,
        )


class DurableAgentStateResponse(DurableAgentStateEntry):
    """Response entry: assistant messages with token usage statistics."""

    type: Literal["response"] = Field(default="response", alias="$type")
    usage: DurableAgentStateUsage | None = None
    is_error: bool = False

    @staticmethod
    def from_run_response(correlation_id: str, response: AgentRunResponse) -> DurableAgentStateResponse:
        """Create a DurableAgentStateResponse from an AgentRunResponse."""
        logger.warning("Received Agent Run Response response: %s", json.dumps(response.to_dict(), indent=2))
        return DurableAgentStateResponse(
            correlation_id=correlation_id,
            created_at=_parse_created_at(response.created_at),
            messages=[DurableAgentStateMessage.from_chat_message(m) for m in response.messages],
            usage=DurableAgentStateUsage.from_usage(response.usage_details),
        )

    def to_run_response(self) -> Any:
        """Convert this DurableAgentStateResponse back to an AgentRunResponse."""
        return AgentRunResponse(
            created_at=self.created_at.isoformat() if self.created_at else None,
            messages=[m.to_chat_message() for m in self.messages],
            usage=self.usage.to_usage_details() if self.usage else None,
        )


class DurableAgentStateMessage(DurableAgentStateModel):
    """A message with role, content items, and optional metadata."""

    role: str
    contents: list[
        (
            DurableAgentStateTextContent
            | DurableAgentStateDataContent
            | DurableAgentStateErrorContent
            | DurableAgentStateFunctionCallContent
            | DurableAgentStateFunctionResultContent
            | DurableAgentStateHostedFileContent
            | DurableAgentStateHostedVectorStoreContent
            | DurableAgentStateTextReasoningContent
            | DurableAgentStateUriContent
            | DurableAgentStateUsageContent
            | DurableAgentStateUnknownContent
        )
    ]
    author_name: str | None = None
    created_at: datetime | None = None
    extension_data: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        """Extract text from the contents list."""
        text_parts: list[str] = []
        for content in self.contents:
            if isinstance(content, DurableAgentStateTextContent):
                text_parts.append(content.text or "")
        return "".join(text_parts)

    @staticmethod
    def from_run_request(request: RunRequest) -> DurableAgentStateMessage:
        """Convert RunRequest to DurableAgentStateMessage."""
        return DurableAgentStateMessage(
            role=request.role.value,
            contents=[DurableAgentStateTextContent(text=request.message)],
            created_at=_parse_created_at(request.created_at),
        )

    @staticmethod
    def from_chat_message(chat_message: ChatMessage) -> DurableAgentStateMessage:
        """Convert ChatMessage to DurableAgentStateMessage."""
        contents_list: list[DurableAgentStateContent] = [
            DurableAgentStateContent.from_ai_content(c) for c in chat_message.contents
        ]

        return DurableAgentStateMessage(
            role=chat_message.role.value,
            contents=contents_list,
            author_name=chat_message.author_name,
            extension_data=dict(chat_message.additional_properties) if chat_message.additional_properties else None,
        )

    def to_chat_message(self) -> Any:
        """Convert to agent framework ChatMessage."""
        # Convert DurableAgentStateContent objects back to agent_framework content objects
        ai_contents = [c.to_ai_content() for c in self.contents]

        # Build kwargs for ChatMessage
        kwargs: dict[str, Any] = {
            "role": self.role,
            "contents": ai_contents,
        }

        if self.author_name is not None:
            kwargs["author_name"] = self.author_name

        if self.extension_data is not None:
            kwargs["additional_properties"] = self.extension_data

        return ChatMessage(**kwargs)


class DurableAgentStateDataContent(DurableAgentStateContent):
    """Data content referencing a URI with optional media type."""

    type: Literal["data"] = Field(default="data", alias="$type")
    uri: str = ""
    media_type: str | None = None

    @staticmethod
    def from_data_content(content: DataContent) -> DurableAgentStateDataContent:
        return DurableAgentStateDataContent(uri=content.uri, media_type=content.media_type)

    def to_ai_content(self) -> DataContent:
        return DataContent(uri=self.uri, media_type=self.media_type)


class DurableAgentStateErrorContent(DurableAgentStateContent):
    """Error content with message, code, and details."""

    type: Literal["error"] = Field(default="error", alias="$type")
    message: str | None = None
    error_code: str | None = None
    details: str | None = None

    @staticmethod
    def from_error_content(content: ErrorContent) -> DurableAgentStateErrorContent:
        return DurableAgentStateErrorContent(
            message=content.message, error_code=content.error_code, details=content.details
        )

    def to_ai_content(self) -> ErrorContent:
        return ErrorContent(message=self.message, error_code=self.error_code, details=self.details)


class DurableAgentStateFunctionCallContent(DurableAgentStateContent):
    """Function/tool call with call_id, name, and arguments."""

    type: Literal["functionCall"] = Field(default="functionCall", alias="$type")
    call_id: str
    name: str
    arguments: dict[str, Any]

    @staticmethod
    def from_function_call_content(content: FunctionCallContent) -> DurableAgentStateFunctionCallContent:
        # Ensure arguments is a dict; parse string if needed
        arguments: dict[str, Any] = {}
        if content.arguments:
            if isinstance(content.arguments, dict):
                arguments = content.arguments
            elif isinstance(content.arguments, str):
                # Parse JSON string to dict
                try:
                    arguments = json.loads(content.arguments)
                except json.JSONDecodeError:
                    arguments = {}

        return DurableAgentStateFunctionCallContent(call_id=content.call_id, name=content.name, arguments=arguments)

    def to_ai_content(self) -> FunctionCallContent:
        return FunctionCallContent(call_id=self.call_id, name=self.name, arguments=self.arguments)


class DurableAgentStateFunctionResultContent(DurableAgentStateContent):
    """Function/tool result linked to original call via call_id."""

    type: Literal["functionResult"] = Field(default="functionResult", alias="$type")
    call_id: str
    result: object | None = None

    @staticmethod
    def from_function_result_content(content: FunctionResultContent) -> DurableAgentStateFunctionResultContent:
        return DurableAgentStateFunctionResultContent(call_id=content.call_id, result=content.result)

    def to_ai_content(self) -> FunctionResultContent:
        return FunctionResultContent(call_id=self.call_id, result=self.result)


class DurableAgentStateHostedFileContent(DurableAgentStateContent):
    """Reference to a hosted file by file_id."""

    type: Literal["hostedFile"] = Field(default="hostedFile", alias="$type")
    file_id: str

    @staticmethod
    def from_hosted_file_content(content: HostedFileContent) -> DurableAgentStateHostedFileContent:
        return DurableAgentStateHostedFileContent(file_id=content.file_id)

    def to_ai_content(self) -> HostedFileContent:
        return HostedFileContent(file_id=self.file_id)


class DurableAgentStateHostedVectorStoreContent(DurableAgentStateContent):
    """Reference to a hosted vector store by vector_store_id."""

    type: Literal["hostedVectorStore"] = Field(default="hostedVectorStore", alias="$type")
    vector_store_id: str

    @staticmethod
    def from_hosted_vector_store_content(
        content: HostedVectorStoreContent,
    ) -> DurableAgentStateHostedVectorStoreContent:
        return DurableAgentStateHostedVectorStoreContent(vector_store_id=content.vector_store_id)

    def to_ai_content(self) -> HostedVectorStoreContent:
        return HostedVectorStoreContent(vector_store_id=self.vector_store_id)


class DurableAgentStateTextContent(DurableAgentStateContent):
    """Plain text content."""

    type: Literal["text"] = Field(default="text", alias="$type")
    text: str | None = None

    @staticmethod
    def from_text_content(content: TextContent) -> DurableAgentStateTextContent:
        return DurableAgentStateTextContent(text=content.text)

    def to_ai_content(self) -> TextContent:
        return TextContent(text=self.text or "")


class DurableAgentStateTextReasoningContent(DurableAgentStateContent):
    """Agent reasoning/chain-of-thought text, separate from final response."""

    type: Literal["reasoning"] = Field(default="reasoning", alias="$type")
    text: str | None = None

    @staticmethod
    def from_text_reasoning_content(content: TextReasoningContent) -> DurableAgentStateTextReasoningContent:
        return DurableAgentStateTextReasoningContent(text=content.text)

    def to_ai_content(self) -> TextReasoningContent:
        return TextReasoningContent(text=self.text or "")


class DurableAgentStateUriContent(DurableAgentStateContent):
    """URI content with required media type."""

    type: Literal["uri"] = Field(default="uri", alias="$type")
    uri: str
    media_type: str

    @staticmethod
    def from_uri_content(content: UriContent) -> DurableAgentStateUriContent:
        return DurableAgentStateUriContent(uri=content.uri, media_type=content.media_type)

    def to_ai_content(self) -> UriContent:
        return UriContent(uri=self.uri, media_type=self.media_type)


class DurableAgentStateUsage(DurableAgentStateModel):
    """Token usage statistics: input, output, and total counts."""

    input_token_count: int | None = None
    output_token_count: int | None = None
    total_token_count: int | None = None
    extension_data: dict[str, Any] | None = None

    @staticmethod
    def from_usage(usage: UsageDetails | None) -> DurableAgentStateUsage | None:
        if usage is None:
            return None
        return DurableAgentStateUsage(
            input_token_count=usage.input_token_count,
            output_token_count=usage.output_token_count,
            total_token_count=usage.total_token_count,
        )

    def to_usage_details(self) -> UsageDetails:
        # Convert back to AI SDK UsageDetails
        return UsageDetails(
            input_token_count=self.input_token_count,
            output_token_count=self.output_token_count,
            total_token_count=self.total_token_count,
        )


class DurableAgentStateUsageContent(DurableAgentStateContent):
    """Token usage as message content."""

    type: Literal["usage"] = Field(default="usage", alias="$type")
    usage: DurableAgentStateUsage = DurableAgentStateUsage()

    @staticmethod
    def from_usage_content(content: UsageContent) -> DurableAgentStateUsageContent:
        return DurableAgentStateUsageContent(usage=DurableAgentStateUsage.from_usage(content.details))

    def to_ai_content(self) -> UsageContent:
        return UsageContent(details=self.usage.to_usage_details())


class DurableAgentStateUnknownContent(DurableAgentStateContent):
    """Fallback for unrecognized content types. Preserves original content."""

    type: Literal["unknown"] = Field(default="unknown", alias="$type")
    content: Any

    @staticmethod
    def from_unknown_content(content: Any) -> DurableAgentStateUnknownContent:
        return DurableAgentStateUnknownContent(content=content)

    def to_ai_content(self) -> BaseContent:
        if not self.content:
            raise Exception("The content is missing and cannot be converted to valid AI content.")
        return BaseContent(content=self.content)
