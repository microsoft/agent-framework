# Copyright (c) Microsoft. All rights reserved.

"""Durable agent state management conforming to the durable-agent-entity-state.json schema.

This module provides classes for managing conversation state in Azure Durable Functions agents.
It implements the versioned schema that defines how agent conversations are persisted and restored
across invocations, enabling stateful, long-running agent sessions.

The module includes:
- DurableAgentState: Root state container with schema version and conversation history
- DurableAgentStateEntry and subclasses: Request and response entries in conversation history
- DurableAgentStateMessage: Individual messages with role, content items, and metadata
- Content type classes: Specialized types for text, function calls, errors, and other content
- Serialization/deserialization: Conversion between Python objects and JSON schema format

The state structure follows this hierarchy:
    DurableAgentState
    └── DurableAgentStateData
        └── conversationHistory: List[DurableAgentStateEntry]
            ├── DurableAgentStateRequest (user/system messages)
            └── DurableAgentStateResponse (assistant messages with usage stats)
                └── messages: List[DurableAgentStateMessage]
                    └── contents: List[DurableAgentStateContent subclasses]

All classes support bidirectional conversion between:
- Durable state format (JSON with camelCase, $type discriminators)
- Agent framework objects (Python objects with snake_case)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

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

from ._models import RunRequest, serialize_response_format

logger = get_logger("agent_framework.azurefunctions.durable_agent_state")


def _parse_created_at(value: Any) -> datetime:
    """Normalize created_at values coming from persisted durable state."""
    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            parsed = date_parser.parse(value)
            if isinstance(parsed, datetime):
                return parsed
        except (ValueError, TypeError):
            pass

    return datetime.now(tz=timezone.utc)


class DurableAgentStateContent:
    """Base class for all content types in durable agent state messages.

    This abstract base class defines the interface for content items that can be
    stored in conversation history. Content types include text, function calls,
    function results, errors, and other specialized content types defined by the
    agent framework.

    Subclasses must implement to_dict() and to_ai_content() to handle conversion
    between the durable state representation and the agent framework's content objects.

    Attributes:
        extensionData: Optional additional metadata (not serialized per schema)
    """

    extensionData: dict[str, Any] | None = None
    type: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize this content to a dictionary for JSON storage.

        Returns:
            Dictionary representation including $type discriminator and content-specific fields

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError

    def to_ai_content(self) -> Any:
        """Convert this durable state content back to an agent framework content object.

        Returns:
            An agent framework content object (TextContent, FunctionCallContent, etc.)

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError

    @staticmethod
    def from_ai_content(content: Any) -> DurableAgentStateContent:
        """Create a durable state content object from an agent framework content object.

        This factory method maps agent framework content types (TextContent, FunctionCallContent,
        etc.) to their corresponding durable state representations. Unknown content types are
        wrapped in DurableAgentStateUnknownContent.

        Args:
            content: An agent framework content object (TextContent, FunctionCallContent, etc.)

        Returns:
            The corresponding DurableAgentStateContent subclass instance
        """
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


# Core state classes


class DurableAgentStateData:
    """Container for the core data within durable agent state.

    This class holds the primary data structures for agent conversation state,
    including the conversation history (a sequence of request and response entries)
    and optional extension data for custom metadata.

    The data structure is nested within DurableAgentState under the "data" property,
    conforming to the durable-agent-entity-state.json schema structure.

    Attributes:
        conversation_history: Ordered list of conversation entries (requests and responses)
        extension_data: Optional dictionary for custom metadata (not part of core schema)
    """

    conversation_history: list[DurableAgentStateEntry]
    extension_data: dict[str, Any] | None

    def __init__(
        self,
        conversation_history: list[DurableAgentStateEntry] | None = None,
        extension_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the data container.

        Args:
            conversation_history: Initial conversation history (defaults to empty list)
            extension_data: Optional custom metadata
        """
        self.conversation_history = conversation_history or []
        self.extension_data = extension_data

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "conversationHistory": [entry.to_dict() for entry in self.conversation_history],
        }
        if self.extension_data is not None:
            result["extensionData"] = self.extension_data
        return result

    @classmethod
    def from_dict(cls, data_dict: dict[str, Any]) -> DurableAgentStateData:
        # Restore the conversation history - deserialize entries from dicts to objects
        history_data = data_dict.get("conversationHistory", [])
        deserialized_history: list[DurableAgentStateEntry] = []
        for entry_dict in history_data:
            if isinstance(entry_dict, dict):
                # Deserialize based on $type discriminator
                entry_type = entry_dict.get("$type") or entry_dict.get("json_type")
                if entry_type == DurableAgentStateEntryJsonType.RESPONSE:
                    deserialized_history.append(DurableAgentStateResponse.from_dict(entry_dict))
                elif entry_type == DurableAgentStateEntryJsonType.REQUEST:
                    deserialized_history.append(DurableAgentStateRequest.from_dict(entry_dict))
                else:
                    deserialized_history.append(DurableAgentStateEntry.from_dict(entry_dict))
            else:
                # Already an object
                deserialized_history.append(entry_dict)

        return cls(
            conversation_history=deserialized_history,
            extension_data=data_dict.get("extensionData"),
        )


class DurableAgentState:
    """Manages durable agent state conforming to the durable-agent-entity-state.json schema.

    This class provides the root container for agent conversation state that can be persisted
    in Azure Durable Entities. It maintains the conversation history as a sequence of request
    and response entries, each with their messages, timestamps, and metadata.

    The state follows a versioned schema (currently 1.0.0) that defines the structure for:
    - Request entries: User/system messages with optional response format specifications
    - Response entries: Assistant messages with token usage information
    - Messages: Individual chat messages with role, content items, and timestamps
    - Content items: Text, function calls, function results, errors, and other content types

    State is serialized to JSON with this structure:
    {
        "schemaVersion": "1.0.0",
        "data": {
            "conversationHistory": [
                {"$type": "request", "correlationId": "...", "createdAt": "...", "messages": [...]},
                {"$type": "response", "correlationId": "...", "createdAt": "...", "messages": [...], "usage": {...}}
            ]
        }
    }

    Attributes:
        data: Container for conversation history and optional extension data
        schema_version: Schema version string (defaults to "1.0.0")
    """

    data: DurableAgentStateData
    schema_version: str = "1.0.0"

    def __init__(self, schema_version: str = "1.0.0"):
        """Initialize a new durable agent state.

        Args:
            schema_version: Schema version to use (defaults to "1.0.0")
        """
        self.data = DurableAgentStateData()
        self.schema_version = schema_version

    def to_dict(self) -> dict[str, Any]:

        return {
            "schemaVersion": self.schema_version,
            "data": self.data.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> DurableAgentState:
        """Restore state from a dictionary.

        Args:
            state: Dictionary containing schemaVersion and data (full state structure)
        """
        schema_version = state.get("schemaVersion")
        if schema_version is None:
            logger.warning("Resetting state as it is incompatible with the current schema, all history will be lost")
            return cls()

        instance = cls(schema_version=state.get("schemaVersion", "1.0.0"))
        instance.data = DurableAgentStateData.from_dict(state.get("data", {}))

        return instance

    @classmethod
    def from_json(cls, json_str: str) -> DurableAgentState:
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError("The durable agent state is not valid JSON.") from e

        return cls.from_dict(obj)

    @property
    def message_count(self) -> int:
        """Get the count of conversation entries (requests + responses)."""
        return len(self.data.conversation_history)

    def try_get_agent_response(self, correlation_id: str) -> dict[str, Any] | None:
        """Try to get an agent response by correlation ID.

        This method searches the conversation history for a response entry matching the given
        correlation ID and returns a dictionary suitable for HTTP API responses.

        Note: The returned dictionary includes computed properties (message_count) that are
        NOT part of the persisted state schema. These are derived values included for backward
        compatibility with the HTTP API response format and should not be considered part of
        the durable state structure.

        Args:
            correlation_id: The correlation ID to search for

        Returns:
            Response data dict with 'content', 'message_count', and 'correlationId' if found,
            None otherwise
        """
        # Search through conversation history for a response with this correlationId
        for entry in self.data.conversation_history:
            if entry.correlation_id == correlation_id and isinstance(entry, DurableAgentStateResponse):
                # Found the entry, extract response data
                # Get the text content from assistant messages only
                content = "\n".join(message.text for message in entry.messages if message.text is not None)

                return {"content": content, "message_count": self.message_count, "correlationId": correlation_id}
        return None


class DurableAgentStateEntryJsonType(str, Enum):
    """Enum for conversation history entry types.

    Discriminator values for the $type field in DurableAgentStateEntry objects.
    """

    REQUEST = "request"
    RESPONSE = "response"


class DurableAgentStateEntry:
    """Base class for conversation history entries (requests and responses).

    This class represents a single entry in the conversation history. Each entry can be
    either a request (user/system messages sent to the agent) or a response (assistant
    messages from the agent). The $type discriminator field determines which type of entry
    it represents.

    Entries are linked together using correlation IDs, allowing responses to be matched
    with their originating requests.

    Common Attributes:
        json_type: Discriminator for entry type ("request" or "response")
        correlationId: Unique identifier linking requests and responses
        created_at: Timestamp when the entry was created
        messages: List of messages in this entry
        extensionData: Optional additional metadata (not serialized per schema)

    Request-only Attributes:
        responseType: Expected response type ("text" or "json") - only for request entries
        responseSchema: JSON schema for structured responses - only for request entries

    Response-only Attributes:
        usage: Token usage statistics - only for response entries
    """

    json_type: DurableAgentStateEntryJsonType
    correlation_id: str | None
    created_at: datetime
    messages: list[DurableAgentStateMessage]
    extension_data: dict[str, Any] | None

    def __init__(
        self,
        json_type: DurableAgentStateEntryJsonType,
        correlation_id: str | None,
        created_at: datetime,
        messages: list[DurableAgentStateMessage],
        extension_data: dict[str, Any] | None = None,
    ) -> None:
        self.json_type = json_type
        self.correlation_id = correlation_id
        self.created_at = created_at
        self.messages = messages
        self.extension_data = extension_data

    def to_dict(self) -> dict[str, Any]:
        # Ensure createdAt is never null
        created_at_value = self.created_at
        if created_at_value is None:
            created_at_value = datetime.now(tz=timezone.utc)

        return {
            "$type": self.json_type,
            "correlationId": self.correlation_id,
            "createdAt": created_at_value.isoformat() if isinstance(created_at_value, datetime) else created_at_value,
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateEntry:
        created_at = _parse_created_at(data.get("created_at"))

        messages = []
        for msg_dict in data.get("messages", []):
            if isinstance(msg_dict, dict):
                messages.append(DurableAgentStateMessage.from_dict(msg_dict))
            else:
                messages.append(msg_dict)

        return cls(
            json_type=DurableAgentStateEntryJsonType(data.get("$type", "entry")),
            correlation_id=data.get("correlationId", ""),
            created_at=created_at,
            messages=messages,
            extension_data=data.get("extensionData"),
        )


class DurableAgentStateRequest(DurableAgentStateEntry):
    """Represents a request entry in the durable agent conversation history.

    A request entry captures a user or system message sent to the agent, along with
    optional response format specifications. Each request is stored as a separate
    entry in the conversation history with a unique correlation ID.

    Attributes:
        response_type: Expected response type ("text" or "json")
        response_schema: JSON schema for structured responses (when response_type is "json")
        correlationId: Unique identifier linking this request to its response
        created_at: Timestamp when the request was created
        messages: List of messages included in this request
        json_type: Always "request" for this class
    """

    response_type: str | None = None
    response_schema: dict[str, Any] | None = None

    def __init__(
        self,
        correlation_id: str | None,
        created_at: datetime,
        messages: list[DurableAgentStateMessage],
        extension_data: dict[str, Any] | None = None,
        response_type: str | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            json_type=DurableAgentStateEntryJsonType.REQUEST,
            correlation_id=correlation_id,
            created_at=created_at,
            messages=messages,
            extension_data=extension_data,
        )
        self.response_type = response_type
        self.response_schema = response_schema

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self.response_type is not None:
            data["responseType"] = self.response_type
        if self.response_schema is not None:
            data["responseSchema"] = self.response_schema
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateRequest:
        created_at = _parse_created_at(data.get("created_at"))

        messages = []
        for msg_dict in data.get("messages", []):
            if isinstance(msg_dict, dict):
                messages.append(DurableAgentStateMessage.from_dict(msg_dict))
            else:
                messages.append(msg_dict)

        return cls(
            correlation_id=data.get("correlationId", ""),
            created_at=created_at,
            messages=messages,
            extension_data=data.get("extensionData"),
            response_type=data.get("responseType"),
            response_schema=data.get("responseSchema"),
        )

    @staticmethod
    def from_run_request(request: RunRequest) -> DurableAgentStateRequest:
        # Determine response_type based on response_format
        return DurableAgentStateRequest(
            correlation_id=request.correlation_id,
            messages=[DurableAgentStateMessage.from_run_request(request)],
            created_at=datetime.now(tz=timezone.utc),
            response_type=request.request_response_format,
            response_schema=serialize_response_format(request.response_format),
        )


class DurableAgentStateResponse(DurableAgentStateEntry):
    """Represents a response entry in the durable agent conversation history.

    A response entry captures the agent's reply to a user request, including any
    assistant messages, tool calls, and token usage information. Each response is
    linked to its originating request via a correlation ID.

    Attributes:
        usage: Token usage statistics for this response (input, output, and total tokens)
        is_error: Flag indicating if this response represents an error (not persisted in schema)
        correlation_id: Unique identifier linking this response to its request
        created_at: Timestamp when the response was created
        messages: List of assistant messages in this response
        json_type: Always "response" for this class
    """

    usage: DurableAgentStateUsage | None = None
    is_error: bool = False

    def __init__(
        self,
        correlation_id: str,
        created_at: datetime,
        messages: list[DurableAgentStateMessage],
        extension_data: dict[str, Any] | None = None,
        usage: DurableAgentStateUsage | None = None,
        is_error: bool = False,
    ) -> None:
        super().__init__(
            json_type=DurableAgentStateEntryJsonType.RESPONSE,
            correlation_id=correlation_id,
            created_at=created_at,
            messages=messages,
            extension_data=extension_data,
        )
        self.usage = usage
        self.is_error = is_error

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self.usage is not None:
            data["usage"] = self.usage.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateResponse:
        created_at = _parse_created_at(data.get("created_at"))

        messages = []
        for msg_dict in data.get("messages", []):
            if isinstance(msg_dict, dict):
                messages.append(DurableAgentStateMessage.from_dict(msg_dict))
            else:
                messages.append(msg_dict)

        usage_dict = data.get("usage")
        usage = None
        if usage_dict and isinstance(usage_dict, dict):
            usage = DurableAgentStateUsage.from_dict(usage_dict)
        elif usage_dict:
            usage = usage_dict

        return cls(
            correlation_id=data.get("correlationId", ""),
            created_at=created_at,
            messages=messages,
            extension_data=data.get("extensionData"),
            usage=usage,
        )

    @staticmethod
    def from_run_response(correlation_id: str, response: AgentRunResponse) -> DurableAgentStateResponse:
        """Creates a DurableAgentStateResponse from an AgentRunResponse."""
        return DurableAgentStateResponse(
            correlation_id=correlation_id,
            created_at=_parse_created_at(response.created_at),
            messages=[DurableAgentStateMessage.from_chat_message(m) for m in response.messages],
            usage=DurableAgentStateUsage.from_usage(response.usage_details),
        )

    def to_run_response(self) -> Any:
        """Converts this DurableAgentStateResponse back to an AgentRunResponse."""
        return AgentRunResponse(
            created_at=self.created_at.isoformat() if self.created_at else None,
            messages=[m.to_chat_message() for m in self.messages],
            usage=self.usage.to_usage_details() if self.usage else None,
        )


class DurableAgentStateMessage:
    """Represents a message within a conversation history entry.

    A message contains the role (user, assistant, system), content items (text, function calls,
    tool results, etc.), and optional metadata. Messages are the building blocks of both
    request and response entries in the conversation history.

    Attributes:
        role: The sender role ("user", "assistant", or "system")
        contents: List of content items (text, function calls, errors, etc.)
        author_name: Optional name of the message author (typically set for assistant messages)
        created_at: Optional timestamp when the message was created
        extension_data: Optional additional metadata (not serialized per schema)
    """

    role: str
    contents: list[DurableAgentStateContent]
    author_name: str | None = None
    created_at: datetime | None = None
    extension_data: dict[str, Any] | None = None

    def __init__(
        self,
        role: str,
        contents: list[DurableAgentStateContent],
        author_name: str | None = None,
        created_at: datetime | None = None,
        extension_data: dict[str, Any] | None = None,
    ) -> None:
        self.role = role
        self.contents = contents
        self.author_name = author_name
        self.created_at = created_at
        self.extension_data = extension_data

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "role": self.role,
            "contents": [
                {"$type": c.to_dict().get("type", "text"), **{k: v for k, v in c.to_dict().items() if k != "type"}}
                for c in self.contents
            ],
        }
        # Only include optional fields if they have values
        if self.created_at is not None:
            result["createdAt"] = self.created_at.isoformat()
        if self.author_name is not None:
            result["authorName"] = self.author_name
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateMessage:
        contents: list[DurableAgentStateContent] = []
        for content_dict in data.get("contents", []):
            if isinstance(content_dict, dict):
                content_type = content_dict.get("$type")
                if content_type == DurableAgentStateTextContent.type:
                    contents.append(DurableAgentStateTextContent(text=content_dict.get("text")))
                elif content_type == DurableAgentStateDataContent.type:
                    contents.append(
                        DurableAgentStateDataContent(
                            uri=content_dict.get("uri", ""), media_type=content_dict.get("mediaType")
                        )
                    )
                elif content_type == DurableAgentStateErrorContent.type:
                    contents.append(
                        DurableAgentStateErrorContent(
                            message=content_dict.get("message"),
                            error_code=content_dict.get("errorCode"),
                            details=content_dict.get("details"),
                        )
                    )
                elif content_type == DurableAgentStateFunctionCallContent.type:
                    contents.append(
                        DurableAgentStateFunctionCallContent(
                            call_id=content_dict.get("callId", ""),
                            name=content_dict.get("name", ""),
                            arguments=content_dict.get("arguments", {}),
                        )
                    )
                elif content_type == DurableAgentStateFunctionResultContent.type:
                    contents.append(
                        DurableAgentStateFunctionResultContent(
                            call_id=content_dict.get("callId", ""), result=content_dict.get("result")
                        )
                    )
                elif content_type == DurableAgentStateHostedFileContent.type:
                    contents.append(DurableAgentStateHostedFileContent(file_id=content_dict.get("fileId", "")))
                elif content_type == DurableAgentStateHostedVectorStoreContent.type:
                    contents.append(
                        DurableAgentStateHostedVectorStoreContent(vector_store_id=content_dict.get("vectorStoreId", ""))
                    )
                elif content_type == DurableAgentStateTextReasoningContent.type:
                    contents.append(DurableAgentStateTextReasoningContent(text=content_dict.get("text")))
                elif content_type == DurableAgentStateUriContent.type:
                    contents.append(
                        DurableAgentStateUriContent(
                            uri=content_dict.get("uri", ""), media_type=content_dict.get("mediaType", "")
                        )
                    )
                elif content_type == DurableAgentStateUsageContent.type:
                    usage_data = content_dict.get("usage")
                    if usage_data and isinstance(usage_data, dict):
                        contents.append(
                            DurableAgentStateUsageContent(usage=DurableAgentStateUsage.from_dict(usage_data))
                        )
                elif content_type == DurableAgentStateUnknownContent.type:
                    contents.append(DurableAgentStateUnknownContent(content=content_dict.get("content", {})))
            else:
                contents.append(content_dict)  # type: ignore

        return cls(
            role=data.get("role", ""),
            contents=contents,
            author_name=data.get("authorName"),
            created_at=_parse_created_at(data.get("createdAt")),
            extension_data=data.get("extensionData"),
        )

    @property
    def text(self) -> str:
        """Extract text from the contents list."""
        text_parts = []
        for content in self.contents:
            if isinstance(content, DurableAgentStateTextContent):
                text_parts.append(content.text or "")
        return "".join(text_parts)

    @staticmethod
    def from_run_request(request: RunRequest) -> DurableAgentStateMessage:
        """Converts a RunRequest from the agent framework to a DurableAgentStateMessage.

        Args:
            request: RunRequest object with role, message/contents, and metadata
        Returns:
            DurableAgentStateMessage with converted content items and metadata
        """
        return DurableAgentStateMessage(
            role=request.role.value,
            contents=[DurableAgentStateTextContent(text=request.message)],
            created_at=_parse_created_at(request.created_at),
        )

    @staticmethod
    def from_chat_message(chat_message: ChatMessage) -> DurableAgentStateMessage:
        """Converts an Agent Framework chat message to a durable state message.

        Args:
            chat_message: ChatMessage object with role, contents, and metadata to convert

        Returns:
            DurableAgentStateMessage with converted content items and metadata
        """
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
        """Converts this DurableAgentStateMessage back to an agent framework ChatMessage.

        Returns:
            ChatMessage object with role, contents, and metadata converted back to agent framework types
        """
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
    """Represents data content with a URI reference.

    This content type is used to reference data stored at a specific URI location,
    optionally with a media type specification. Common use cases include referencing
    files, documents, or other data resources.

    Attributes:
        uri: URI pointing to the data resource
        media_type: Optional MIME type of the data (e.g., "application/json", "text/plain")
    """

    uri: str = ""
    media_type: str | None = None
    type: str = "data"

    def __init__(self, uri: str, media_type: str | None = None) -> None:
        self.uri = uri
        self.media_type = media_type

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "uri": self.uri, "mediaType": self.media_type}

    @staticmethod
    def from_data_content(content: DataContent) -> DurableAgentStateDataContent:
        return DurableAgentStateDataContent(uri=content.uri, media_type=content.media_type)

    def to_ai_content(self) -> DataContent:
        return DataContent(uri=self.uri, media_type=self.media_type)


class DurableAgentStateErrorContent(DurableAgentStateContent):
    """Represents error content in agent responses.

    This content type is used to communicate errors that occurred during agent execution,
    including error messages, error codes, and additional details for debugging.

    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code or exception type
        details: Additional error details or stack trace information
    """

    message: str | None = None
    error_code: str | None = None
    details: str | None = None

    type: str = "error"

    def __init__(self, message: str | None = None, error_code: str | None = None, details: str | None = None) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "message": self.message, "errorCode": self.error_code, "details": self.details}

    @staticmethod
    def from_error_content(content: ErrorContent) -> DurableAgentStateErrorContent:
        return DurableAgentStateErrorContent(
            message=content.message, error_code=content.error_code, details=content.details
        )

    def to_ai_content(self) -> ErrorContent:
        return ErrorContent(message=self.message, error_code=self.error_code, details=self.details)


class DurableAgentStateFunctionCallContent(DurableAgentStateContent):
    """Represents a function/tool call request from the agent.

    This content type is used when the agent requests execution of a function or tool,
    including the function name, arguments, and a unique call identifier for tracking
    the call-result pair.

    Attributes:
        call_id: Unique identifier for this function call (used to match with results)
        name: Name of the function/tool to execute
        arguments: Dictionary of argument names to values for the function call
    """

    call_id: str
    name: str
    arguments: dict[str, Any]

    type: str = "functionCall"

    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        self.call_id = call_id
        self.name = name
        self.arguments = arguments

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "callId": self.call_id, "name": self.name, "arguments": self.arguments}

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
    """Represents the result of a function/tool call execution.

    This content type is used to communicate the result of executing a function or tool
    that was previously requested by the agent. The call_id links this result back to
    the original function call request.

    Attributes:
        call_id: Unique identifier matching the original function call
        result: The return value from the function execution (can be any serializable type)
    """

    call_id: str
    result: object | None = None

    type: str = "functionResult"

    def __init__(self, call_id: str, result: Any | None = None) -> None:
        self.call_id = call_id
        self.result = result

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "callId": self.call_id, "result": self.result}

    @staticmethod
    def from_function_result_content(content: FunctionResultContent) -> DurableAgentStateFunctionResultContent:
        return DurableAgentStateFunctionResultContent(call_id=content.call_id, result=content.result)

    def to_ai_content(self) -> FunctionResultContent:
        return FunctionResultContent(call_id=self.call_id, result=self.result)


class DurableAgentStateHostedFileContent(DurableAgentStateContent):
    """Represents a reference to a hosted file resource.

    This content type is used to reference files that are hosted by the agent platform
    or a file storage service, identified by a unique file ID.

    Attributes:
        file_id: Unique identifier for the hosted file
    """

    file_id: str

    type: str = "hostedFile"

    def __init__(self, file_id: str) -> None:
        self.file_id = file_id

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "fileId": self.file_id}

    @staticmethod
    def from_hosted_file_content(content: HostedFileContent) -> DurableAgentStateHostedFileContent:
        return DurableAgentStateHostedFileContent(file_id=content.file_id)

    def to_ai_content(self) -> HostedFileContent:
        return HostedFileContent(file_id=self.file_id)


class DurableAgentStateHostedVectorStoreContent(DurableAgentStateContent):
    """Represents a reference to a hosted vector store resource.

    This content type is used to reference vector stores (used for semantic search
    and retrieval-augmented generation) that are hosted by the agent platform,
    identified by a unique vector store ID.

    Attributes:
        vector_store_id: Unique identifier for the hosted vector store
    """

    vector_store_id: str

    type: str = "hostedVectorStore"

    def __init__(self, vector_store_id: str) -> None:
        self.vector_store_id = vector_store_id

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "vectorStoreId": self.vector_store_id}

    @staticmethod
    def from_hosted_vector_store_content(
        content: HostedVectorStoreContent,
    ) -> DurableAgentStateHostedVectorStoreContent:
        return DurableAgentStateHostedVectorStoreContent(vector_store_id=content.vector_store_id)

    def to_ai_content(self) -> HostedVectorStoreContent:
        return HostedVectorStoreContent(vector_store_id=self.vector_store_id)


class DurableAgentStateTextContent(DurableAgentStateContent):
    """Represents plain text content in messages.

    This is the most common content type, used for regular text messages from users
    and text responses from the agent.

    Attributes:
        text: The text content of the message
    """

    type: str = "text"

    def __init__(self, text: str | None) -> None:
        self.text = text

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "text": self.text}

    @staticmethod
    def from_text_content(content: TextContent) -> DurableAgentStateTextContent:
        return DurableAgentStateTextContent(text=content.text)

    def to_ai_content(self) -> TextContent:
        return TextContent(text=self.text or "")


class DurableAgentStateTextReasoningContent(DurableAgentStateContent):
    """Represents reasoning or thought process text from the agent.

    This content type is used to capture the agent's internal reasoning, chain of thought,
    or explanation of its decision-making process, separate from the final response text.

    Attributes:
        text: The reasoning or thought process text
    """

    type: str = "reasoning"

    def __init__(self, text: str | None) -> None:
        self.text = text

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "text": self.text}

    @staticmethod
    def from_text_reasoning_content(content: TextReasoningContent) -> DurableAgentStateTextReasoningContent:
        return DurableAgentStateTextReasoningContent(text=content.text)

    def to_ai_content(self) -> TextReasoningContent:
        return TextReasoningContent(text=self.text or "")


class DurableAgentStateUriContent(DurableAgentStateContent):
    """Represents content referenced by a URI with media type.

    This content type is used to reference external content via a URI, with an associated
    media type to indicate how the content should be interpreted.

    Attributes:
        uri: URI pointing to the content resource
        media_type: MIME type of the content (e.g., "image/png", "application/pdf")
    """

    uri: str
    media_type: str

    type: str = "uri"

    def __init__(self, uri: str, media_type: str) -> None:
        self.uri = uri
        self.media_type = media_type

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "uri": self.uri, "mediaType": self.media_type}

    @staticmethod
    def from_uri_content(content: UriContent) -> DurableAgentStateUriContent:
        return DurableAgentStateUriContent(uri=content.uri, media_type=content.media_type)

    def to_ai_content(self) -> UriContent:
        return UriContent(uri=self.uri, media_type=self.media_type)


class DurableAgentStateUsage:
    """Represents token usage statistics for agent responses.

    This class tracks the number of tokens consumed during agent execution,
    including input tokens (from the request), output tokens (in the response),
    and the total token count.

    Attributes:
        input_token_count: Number of tokens in the input/request
        output_token_count: Number of tokens in the output/response
        total_token_count: Total number of tokens consumed (input + output)
        extensionData: Optional additional metadata
    """

    input_token_count: int | None = None
    output_token_count: int | None = None
    total_token_count: int | None = None
    extensionData: dict[str, Any] | None = None

    def __init__(
        self,
        input_token_count: int | None = None,
        output_token_count: int | None = None,
        total_token_count: int | None = None,
        extensionData: dict[str, Any] | None = None,
    ) -> None:
        self.input_token_count = input_token_count
        self.output_token_count = output_token_count
        self.total_token_count = total_token_count
        self.extensionData = extensionData

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "inputTokenCount": self.input_token_count,
            "outputTokenCount": self.output_token_count,
            "totalTokenCount": self.total_token_count,
        }
        if self.extensionData is not None:
            result["extensionData"] = self.extensionData
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateUsage:
        return cls(
            input_token_count=data.get("inputTokenCount"),
            output_token_count=data.get("outputTokenCount"),
            total_token_count=data.get("totalTokenCount"),
            extensionData=data.get("extensionData"),
        )

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
    """Represents token usage information as message content.

    This content type is used to communicate token usage statistics as part of
    message content, allowing usage information to be tracked alongside other
    content types in the conversation history.

    Attributes:
        usage: DurableAgentStateUsage object containing token counts
    """

    usage: DurableAgentStateUsage = DurableAgentStateUsage()

    type: str = "usage"

    def __init__(self, usage: DurableAgentStateUsage) -> None:
        self.usage = usage

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "usage": self.usage.to_dict() if hasattr(self.usage, "to_dict") else self.usage}

    @staticmethod
    def from_usage_content(content: UsageContent) -> DurableAgentStateUsageContent:
        return DurableAgentStateUsageContent(usage=DurableAgentStateUsage.from_usage(content.details))  # type: ignore

    def to_ai_content(self) -> UsageContent:
        return UsageContent(details=self.usage.to_usage_details())


class DurableAgentStateUnknownContent(DurableAgentStateContent):
    """Represents unknown or unrecognized content types.

    This content type serves as a fallback for content that doesn't match any of the
    known content type classes. It preserves the original content object for later
    inspection or processing.

    Attributes:
        content: The unknown content object
    """

    content: Any

    type: str = "unknown"

    def __init__(self, content: Any) -> None:
        self.content = content

    def to_dict(self) -> dict[str, Any]:
        return {"$type": self.type, "content": self.content}

    @staticmethod
    def from_unknown_content(content: Any) -> DurableAgentStateUnknownContent:
        return DurableAgentStateUnknownContent(content=content)

    def to_ai_content(self) -> BaseContent:
        if not self.content:
            raise Exception("The content is missing and cannot be converted to valid AI content.")
        return BaseContent(content=self.content)
