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
from typing import Any, cast

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

from ._constants import ApiResponseFields, ContentTypes, DurableStateFields
from ._models import RunRequest, serialize_response_format

logger = get_logger("agent_framework.azurefunctions.durable_agent_state")


class DurableAgentStateEntryJsonType(str, Enum):
    """Enum for conversation history entry types.

    Discriminator values for the $type field in DurableAgentStateEntry objects.
    """

    REQUEST = "request"
    RESPONSE = "response"


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

    logger.warning("Invalid or missing created_at value in durable agent state; defaulting to current UTC time.")
    return datetime.now(tz=timezone.utc)


def _parse_messages(data: dict[str, Any]) -> list[DurableAgentStateMessage]:
    """Parse messages from a dictionary, converting dicts to DurableAgentStateMessage objects.

    Args:
        data: Dictionary containing a 'messages' key with a list of message data

    Returns:
        List of DurableAgentStateMessage objects
    """
    messages: list[DurableAgentStateMessage] = []
    raw_messages: list[Any] = data.get(DurableStateFields.MESSAGES, [])
    for raw_msg in raw_messages:
        if isinstance(raw_msg, dict):
            messages.append(DurableAgentStateMessage.from_dict(cast(dict[str, Any], raw_msg)))
        elif isinstance(raw_msg, DurableAgentStateMessage):
            messages.append(raw_msg)
    return messages


def _parse_history_entries(data_dict: dict[str, Any]) -> list[DurableAgentStateEntry]:
    """Parse conversation history entries from a dictionary.

    Args:
        data_dict: Dictionary containing a 'conversationHistory' key with a list of entry data

    Returns:
        List of DurableAgentStateEntry objects (requests and responses)
    """
    history_data: list[Any] = data_dict.get(DurableStateFields.CONVERSATION_HISTORY, [])
    deserialized_history: list[DurableAgentStateEntry] = []
    for raw_entry in history_data:
        if isinstance(raw_entry, dict):
            entry_dict = cast(dict[str, Any], raw_entry)
            entry_type = entry_dict.get(DurableStateFields.TYPE_DISCRIMINATOR) or entry_dict.get(
                DurableStateFields.JSON_TYPE
            )
            if entry_type == DurableAgentStateEntryJsonType.RESPONSE:
                deserialized_history.append(DurableAgentStateResponse.from_dict(entry_dict))
            elif entry_type == DurableAgentStateEntryJsonType.REQUEST:
                deserialized_history.append(DurableAgentStateRequest.from_dict(entry_dict))
            else:
                deserialized_history.append(DurableAgentStateEntry.from_dict(entry_dict))
        elif isinstance(raw_entry, DurableAgentStateEntry):
            deserialized_history.append(raw_entry)
    return deserialized_history


def _parse_contents(data: dict[str, Any]) -> list[DurableAgentStateContent]:
    """Parse content items from a dictionary.

    Args:
        data: Dictionary containing a 'contents' key with a list of content data

    Returns:
        List of DurableAgentStateContent objects
    """
    contents: list[DurableAgentStateContent] = []
    raw_contents: list[Any] = data.get(DurableStateFields.CONTENTS, [])
    for raw_content in raw_contents:
        if isinstance(raw_content, DurableAgentStateContent):
            contents.append(raw_content)

        elif isinstance(raw_content, dict):
            content_dict = cast(dict[str, Any], raw_content)
            content_type: str | None = content_dict.get(DurableStateFields.TYPE_DISCRIMINATOR)

            match content_type:
                case ContentTypes.TEXT:
                    contents.append(DurableAgentStateTextContent(text=content_dict.get(DurableStateFields.TEXT)))

                case ContentTypes.DATA:
                    contents.append(
                        DurableAgentStateDataContent(
                            uri=str(content_dict.get(DurableStateFields.URI, "")),
                            media_type=content_dict.get(DurableStateFields.MEDIA_TYPE),
                        )
                    )

                case ContentTypes.ERROR:
                    contents.append(
                        DurableAgentStateErrorContent(
                            message=content_dict.get(DurableStateFields.MESSAGE),
                            error_code=content_dict.get(DurableStateFields.ERROR_CODE),
                            details=content_dict.get(DurableStateFields.DETAILS),
                        )
                    )

                case ContentTypes.FUNCTION_CALL:
                    contents.append(
                        DurableAgentStateFunctionCallContent(
                            call_id=str(content_dict.get(DurableStateFields.CALL_ID, "")),
                            name=str(content_dict.get(DurableStateFields.NAME, "")),
                            arguments=content_dict.get(DurableStateFields.ARGUMENTS, {}),
                        )
                    )

                case ContentTypes.FUNCTION_RESULT:
                    contents.append(
                        DurableAgentStateFunctionResultContent(
                            call_id=str(content_dict.get(DurableStateFields.CALL_ID, "")),
                            result=content_dict.get(DurableStateFields.RESULT),
                        )
                    )

                case ContentTypes.HOSTED_FILE:
                    contents.append(
                        DurableAgentStateHostedFileContent(
                            file_id=str(content_dict.get(DurableStateFields.FILE_ID, ""))
                        )
                    )

                case ContentTypes.HOSTED_VECTOR_STORE:
                    contents.append(
                        DurableAgentStateHostedVectorStoreContent(
                            vector_store_id=str(content_dict.get(DurableStateFields.VECTOR_STORE_ID, ""))
                        )
                    )

                case ContentTypes.REASONING:
                    contents.append(
                        DurableAgentStateTextReasoningContent(text=content_dict.get(DurableStateFields.TEXT))
                    )

                case ContentTypes.URI:
                    contents.append(
                        DurableAgentStateUriContent(
                            uri=str(content_dict.get(DurableStateFields.URI, "")),
                            media_type=str(content_dict.get(DurableStateFields.MEDIA_TYPE, "")),
                        )
                    )

                case ContentTypes.USAGE:
                    usage_data = content_dict.get(DurableStateFields.USAGE)
                    if usage_data and isinstance(usage_data, dict):
                        contents.append(
                            DurableAgentStateUsageContent(
                                usage=DurableAgentStateUsage.from_dict(cast(dict[str, Any], usage_data))
                            )
                        )

                case ContentTypes.UNKNOWN | _:
                    # Handle UNKNOWN type or any unexpected content types (including None)
                    contents.append(
                        DurableAgentStateUnknownContent(content=content_dict.get(DurableStateFields.CONTENT, {}))
                    )

    return contents


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
            DurableStateFields.CONVERSATION_HISTORY: [entry.to_dict() for entry in self.conversation_history],
        }
        if self.extension_data is not None:
            result[DurableStateFields.EXTENSION_DATA] = self.extension_data
        return result

    @classmethod
    def from_dict(cls, data_dict: dict[str, Any]) -> DurableAgentStateData:
        return cls(
            conversation_history=_parse_history_entries(data_dict),
            extension_data=data_dict.get(DurableStateFields.EXTENSION_DATA),
        )


class DurableAgentState:
    """Manages durable agent state conforming to the durable-agent-entity-state.json schema.

    This class provides the root container for agent conversation state that can be persisted
    in Azure Durable Entities. It maintains the conversation history as a sequence of request
    and response entries, each with their messages, timestamps, and metadata.

    The state follows a versioned schema (see SCHEMA_VERSION class constant) that defines the structure for:
    - Request entries: User/system messages with optional response format specifications
    - Response entries: Assistant messages with token usage information
    - Messages: Individual chat messages with role, content items, and timestamps
    - Content items: Text, function calls, function results, errors, and other content types

    State is serialized to JSON with this structure:
    {
        "schemaVersion": "<SCHEMA_VERSION>",
        "data": {
            "conversationHistory": [
                {"$type": "request", "correlationId": "...", "createdAt": "...", "messages": [...]},
                {"$type": "response", "correlationId": "...", "createdAt": "...", "messages": [...], "usage": {...}}
            ]
        }
    }

    Attributes:
        data: Container for conversation history and optional extension data
        schema_version: Schema version string (defaults to SCHEMA_VERSION)
    """

    # Durable Agent Schema version
    SCHEMA_VERSION: str = "1.1.0"

    data: DurableAgentStateData
    schema_version: str = SCHEMA_VERSION

    def __init__(self, schema_version: str = SCHEMA_VERSION):
        """Initialize a new durable agent state.

        Args:
            schema_version: Schema version to use (defaults to SCHEMA_VERSION)
        """
        self.data = DurableAgentStateData()
        self.schema_version = schema_version

    def to_dict(self) -> dict[str, Any]:

        return {
            DurableStateFields.SCHEMA_VERSION: self.schema_version,
            DurableStateFields.DATA: self.data.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, state: dict[str, Any]) -> DurableAgentState:
        """Restore state from a dictionary.

        Args:
            state: Dictionary containing schemaVersion and data (full state structure)
        """
        schema_version = state.get(DurableStateFields.SCHEMA_VERSION)
        if schema_version is None:
            logger.warning("Resetting state as it is incompatible with the current schema, all history will be lost")
            return cls()

        instance = cls(schema_version=state.get(DurableStateFields.SCHEMA_VERSION, DurableAgentState.SCHEMA_VERSION))
        instance.data = DurableAgentStateData.from_dict(state.get(DurableStateFields.DATA, {}))

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
                content = "\n".join(message.text for message in entry.messages if message.text)

                return {
                    ApiResponseFields.CONTENT: content,
                    ApiResponseFields.MESSAGE_COUNT: self.message_count,
                    ApiResponseFields.CORRELATION_ID: correlation_id,
                }
        return None


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
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.json_type,
            DurableStateFields.CORRELATION_ID: self.correlation_id,
            DurableStateFields.CREATED_AT: self.created_at.isoformat(),
            DurableStateFields.MESSAGES: [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateEntry:
        created_at = _parse_created_at(data.get(DurableStateFields.CREATED_AT))
        messages = _parse_messages(data)

        return cls(
            json_type=DurableAgentStateEntryJsonType(data.get(DurableStateFields.TYPE_DISCRIMINATOR)),
            correlation_id=data.get(DurableStateFields.CORRELATION_ID),
            created_at=created_at,
            messages=messages,
            extension_data=data.get(DurableStateFields.EXTENSION_DATA),
        )


class DurableAgentStateRequest(DurableAgentStateEntry):
    """Represents a request entry in the durable agent conversation history.

    A request entry captures a user or system message sent to the agent, along with
    optional response format specifications. Each request is stored as a separate
    entry in the conversation history with a unique correlation ID.

    Attributes:
        response_type: Expected response type ("text" or "json")
        response_schema: JSON schema for structured responses (when response_type is "json")
        orchestration_id: ID of the orchestration that initiated this request (if any)
        correlationId: Unique identifier linking this request to its response
        created_at: Timestamp when the request was created
        messages: List of messages included in this request
        json_type: Always "request" for this class
    """

    response_type: str | None = None
    response_schema: dict[str, Any] | None = None
    orchestration_id: str | None = None

    def __init__(
        self,
        correlation_id: str | None,
        created_at: datetime,
        messages: list[DurableAgentStateMessage],
        extension_data: dict[str, Any] | None = None,
        response_type: str | None = None,
        response_schema: dict[str, Any] | None = None,
        orchestration_id: str | None = None,
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
        self.orchestration_id = orchestration_id

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self.orchestration_id is not None:
            data[DurableStateFields.ORCHESTRATION_ID] = self.orchestration_id
        if self.response_type is not None:
            data[DurableStateFields.RESPONSE_TYPE] = self.response_type
        if self.response_schema is not None:
            data[DurableStateFields.RESPONSE_SCHEMA] = self.response_schema
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateRequest:
        created_at = _parse_created_at(data.get(DurableStateFields.CREATED_AT))
        messages = _parse_messages(data)

        return cls(
            correlation_id=data.get(DurableStateFields.CORRELATION_ID),
            created_at=created_at,
            messages=messages,
            extension_data=data.get(DurableStateFields.EXTENSION_DATA),
            response_type=data.get(DurableStateFields.RESPONSE_TYPE),
            response_schema=data.get(DurableStateFields.RESPONSE_SCHEMA),
            orchestration_id=data.get(DurableStateFields.ORCHESTRATION_ID),
        )

    @staticmethod
    def from_run_request(request: RunRequest) -> DurableAgentStateRequest:
        # Determine response_type based on response_format
        return DurableAgentStateRequest(
            correlation_id=request.correlation_id,
            messages=[DurableAgentStateMessage.from_run_request(request)],
            created_at=_parse_created_at(request.created_at),
            response_type=request.request_response_format,
            response_schema=serialize_response_format(request.response_format),
            orchestration_id=request.orchestration_id,
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
        correlation_id: str | None,
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
            data[DurableStateFields.USAGE] = self.usage.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateResponse:
        created_at = _parse_created_at(data.get(DurableStateFields.CREATED_AT))
        messages = _parse_messages(data)

        usage_dict = data.get(DurableStateFields.USAGE)
        usage: DurableAgentStateUsage | None = None
        if usage_dict and isinstance(usage_dict, dict):
            usage = DurableAgentStateUsage.from_dict(cast(dict[str, Any], usage_dict))

        return cls(
            correlation_id=data.get(DurableStateFields.CORRELATION_ID),
            created_at=created_at,
            messages=messages,
            extension_data=data.get(DurableStateFields.EXTENSION_DATA),
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
            DurableStateFields.ROLE: self.role,
            DurableStateFields.CONTENTS: [
                {
                    DurableStateFields.TYPE_DISCRIMINATOR: c.to_dict().get(
                        DurableStateFields.TYPE_INTERNAL, ContentTypes.TEXT
                    ),
                    **{k: v for k, v in c.to_dict().items() if k != DurableStateFields.TYPE_INTERNAL},
                }
                for c in self.contents
            ],
        }
        # Only include optional fields if they have values
        if self.created_at is not None:
            result[DurableStateFields.CREATED_AT] = self.created_at.isoformat()
        if self.author_name is not None:
            result[DurableStateFields.AUTHOR_NAME] = self.author_name
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateMessage:
        data_created_at = data.get(DurableStateFields.CREATED_AT)
        created_at = _parse_created_at(data_created_at) if data_created_at else None

        return cls(
            role=data.get(DurableStateFields.ROLE, ""),
            contents=_parse_contents(data),
            author_name=data.get(DurableStateFields.AUTHOR_NAME),
            created_at=created_at,
            extension_data=data.get(DurableStateFields.EXTENSION_DATA),
        )

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
        """Converts a RunRequest from the agent framework to a DurableAgentStateMessage.

        Args:
            request: RunRequest object with role, message/contents, and metadata
        Returns:
            DurableAgentStateMessage with converted content items and metadata
        """
        return DurableAgentStateMessage(
            role=request.role.value,
            contents=[DurableAgentStateTextContent(text=request.message)],
            created_at=_parse_created_at(request.created_at) if request.created_at else None,
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
    type: str = ContentTypes.DATA

    def __init__(self, uri: str, media_type: str | None = None) -> None:
        self.uri = uri
        self.media_type = media_type

    def to_dict(self) -> dict[str, Any]:
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.type,
            DurableStateFields.URI: self.uri,
            DurableStateFields.MEDIA_TYPE: self.media_type,
        }

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

    type: str = ContentTypes.ERROR

    def __init__(self, message: str | None = None, error_code: str | None = None, details: str | None = None) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.type,
            DurableStateFields.MESSAGE: self.message,
            DurableStateFields.ERROR_CODE: self.error_code,
            DurableStateFields.DETAILS: self.details,
        }

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

    type: str = ContentTypes.FUNCTION_CALL

    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        self.call_id = call_id
        self.name = name
        self.arguments = arguments

    def to_dict(self) -> dict[str, Any]:
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.type,
            DurableStateFields.CALL_ID: self.call_id,
            DurableStateFields.NAME: self.name,
            DurableStateFields.ARGUMENTS: self.arguments,
        }

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

    type: str = ContentTypes.FUNCTION_RESULT

    def __init__(self, call_id: str, result: Any | None = None) -> None:
        self.call_id = call_id
        self.result = result

    def to_dict(self) -> dict[str, Any]:
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.type,
            DurableStateFields.CALL_ID: self.call_id,
            DurableStateFields.RESULT: self.result,
        }

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

    type: str = ContentTypes.HOSTED_FILE

    def __init__(self, file_id: str) -> None:
        self.file_id = file_id

    def to_dict(self) -> dict[str, Any]:
        return {DurableStateFields.TYPE_DISCRIMINATOR: self.type, DurableStateFields.FILE_ID: self.file_id}

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

    type: str = ContentTypes.HOSTED_VECTOR_STORE

    def __init__(self, vector_store_id: str) -> None:
        self.vector_store_id = vector_store_id

    def to_dict(self) -> dict[str, Any]:
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.type,
            DurableStateFields.VECTOR_STORE_ID: self.vector_store_id,
        }

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

    type: str = ContentTypes.TEXT

    def __init__(self, text: str | None) -> None:
        self.text = text

    def to_dict(self) -> dict[str, Any]:
        return {DurableStateFields.TYPE_DISCRIMINATOR: self.type, DurableStateFields.TEXT: self.text}

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

    type: str = ContentTypes.REASONING

    def __init__(self, text: str | None) -> None:
        self.text = text

    def to_dict(self) -> dict[str, Any]:
        return {DurableStateFields.TYPE_DISCRIMINATOR: self.type, DurableStateFields.TEXT: self.text}

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

    type: str = ContentTypes.URI

    def __init__(self, uri: str, media_type: str) -> None:
        self.uri = uri
        self.media_type = media_type

    def to_dict(self) -> dict[str, Any]:
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.type,
            DurableStateFields.URI: self.uri,
            DurableStateFields.MEDIA_TYPE: self.media_type,
        }

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
            DurableStateFields.INPUT_TOKEN_COUNT: self.input_token_count,
            DurableStateFields.OUTPUT_TOKEN_COUNT: self.output_token_count,
            DurableStateFields.TOTAL_TOKEN_COUNT: self.total_token_count,
        }
        if self.extensionData is not None:
            result[DurableStateFields.EXTENSION_DATA] = self.extensionData
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DurableAgentStateUsage:
        return cls(
            input_token_count=data.get(DurableStateFields.INPUT_TOKEN_COUNT),
            output_token_count=data.get(DurableStateFields.OUTPUT_TOKEN_COUNT),
            total_token_count=data.get(DurableStateFields.TOTAL_TOKEN_COUNT),
            extensionData=data.get(DurableStateFields.EXTENSION_DATA),
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

    type: str = ContentTypes.USAGE

    def __init__(self, usage: DurableAgentStateUsage | None) -> None:
        self.usage = usage if usage is not None else DurableAgentStateUsage()

    def to_dict(self) -> dict[str, Any]:
        return {
            DurableStateFields.TYPE_DISCRIMINATOR: self.type,
            DurableStateFields.USAGE: self.usage.to_dict(),
        }

    @staticmethod
    def from_usage_content(content: UsageContent) -> DurableAgentStateUsageContent:
        return DurableAgentStateUsageContent(usage=DurableAgentStateUsage.from_usage(content.details))

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

    type: str = ContentTypes.UNKNOWN

    def __init__(self, content: Any) -> None:
        self.content = content

    def to_dict(self) -> dict[str, Any]:
        return {DurableStateFields.TYPE_DISCRIMINATOR: self.type, DurableStateFields.CONTENT: self.content}

    @staticmethod
    def from_unknown_content(content: Any) -> DurableAgentStateUnknownContent:
        return DurableAgentStateUnknownContent(content=content)

    def to_ai_content(self) -> BaseContent:
        if not self.content:
            raise Exception("The content is missing and cannot be converted to valid AI content.")
        return BaseContent(content=self.content)
