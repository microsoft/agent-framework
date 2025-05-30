# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, ClassVar, Dict, Generic, List, Self, Sequence, TypeVar

from pydantic import BaseModel
from pydantic.generics import GenericModel

from agent_framework.model_client import AIContent, TextContent, UsageDetails


class ChatRole(BaseModel):
    """Describes the intended purpose of a message within a chat interaction."""
    value: str

    SYSTEM: ClassVar[Self]  # type: ignore[assignment]
    """The role that instructs or sets the behaviour of the AI system."""
    USER: ClassVar[Self]  # type: ignore[assignment]
    """The role that provides user input for chat interactions."""
    ASSISTANT: ClassVar[Self]  # type: ignore[assignment]
    """The role that provides responses to system-instructed, user-prompted input."""
    TOOL: ClassVar[Self]  # type: ignore[assignment]
    """The role that provides additional information and references in response to tool use requests."""

    def __str__(self) -> str:
        """Returns the string representation of the role."""
        return self.value

    def __repr__(self) -> str:
        """Returns the string representation of the role."""
        return f"ChatRole(value={self.value!r})"


# Note: ClassVar is used to indicate that these are class-level constants, not instance attributes.
# The type: ignore[assignment] is used to suppress the type checker warning about assigning to a ClassVar,
# it gets assigned immediately after the class definition.
ChatRole.SYSTEM = ChatRole(value="system")
ChatRole.USER = ChatRole(value="user")
ChatRole.ASSISTANT = ChatRole(value="assistant")
ChatRole.TOOL = ChatRole(value="tool")
# We want to avoid using an enum here, as it could cause problems when unexpected values are returned from
# the underlying API (in a future version, for example).


class ChatMessage(BaseModel):
    """Represents a chat message used by a `ModelClient`."""
    author_name: str | None
    """The name of the author of the message"""
    contents: List[AIContent]
    """The chat message content items."""
    message_id: str | None
    """The ID of the chat message."""
    raw_representation: Any | None = None
    """The raw representation of the chat message from an underlying implementation."""
    role: ChatRole
    """The role of the author of the message."""
    additional_properties: Dict[str, Any] | None = None
    """Any additional properties associated with the chat message."""

    @property
    def text(self) -> str:
        """Returns the text content of the message.

        Remarks:
            This property concatenates the text of all TextContent objects in Contents.
        """
        return "\n".join(content.text for content in self.contents if isinstance(content, TextContent))


TValue = TypeVar("TValue")


class ChatFinishReason(BaseModel):
    """Represents the reason a chat response completed."""
    value: str

    CONTENT_FILTER: ClassVar[Self]  # type: ignore[assignment]
    """A ChatFinishReason representing the model filtering content, whether for safety, prohibited content,
    sensitive content, or other such issues."""
    LENGTH: ClassVar[Self]  # type: ignore[assignment]
    """A ChatFinishReason representing the model reaching the maximum length allowed for the request and/or
    response (typically in terms of tokens)."""
    STOP: ClassVar[Self]  # type: ignore[assignment]
    """A ChatFinishReason representing the model encountering a natural stop point or provided stop sequence."""
    TOOL_CALLS: ClassVar[Self]  # type: ignore[assignment]
    """A ChatFinishReason representing the model requesting the use of a tool that was defined in the request."""


# Note: ClassVar is used to indicate that these are class-level constants, not instance attributes.
# The type: ignore[assignment] is used to suppress the type checker warning about assigning to a ClassVar,
# it gets assigned immediately after the class definition.
ChatFinishReason.CONTENT_FILTER = ChatFinishReason(value="content_filter")
ChatFinishReason.LENGTH = ChatFinishReason(value="length")
ChatFinishReason.STOP = ChatFinishReason(value="stop")
ChatFinishReason.TOOL_CALLS = ChatFinishReason(value="tool_calls")
# We want to avoid using an enum here, as it could cause problems when unexpected values are returned from
# the underlying API (in a future version, for example).


CreatedAtT = str  # Use a datetimeoffset type? Or a more specific type like datetime.datetime?


class ChatResponse(BaseModel):
    """Represents the response to a chat request."""
    messages: List[ChatMessage]
    """The chat response messages."""

    additional_properties: Dict[str, Any] | None = None
    """Any additional properties associated with the chat response."""
    conversation_id: str | None = None
    """An identifier for the state of the conversation."""
    created_at: CreatedAtT | None = None  # use a datetimeoffset type?
    """A timestamp for the chat response."""
    finish_reason: ChatFinishReason | None = None
    """The reason for the chat response."""
    model_id: str | None = None
    """The model ID used in the creation of the chat response."""
    raw_representation: Any | None = None
    """The raw representation of the chat response from an underlying implementation."""
    response_id: str | None = None
    """The ID of the chat response."""
    usage_details: UsageDetails | None = None
    """The usage details for the chat response."""

    @property
    def text(self) -> str:
        """Returns the concatenated text of all messages in the response."""
        return "\n".join(message.text for message in self.messages if isinstance(message, ChatMessage))


class StructuredResponse(GenericModel, Generic[TValue], ChatResponse):
    """Represents a structured response to a chat request.

    Type Parameters:
        TValue: The type of the value contained in the structured response.
    """
    value: TValue
    """The result value of the chat response as an instance of `TValue`."""

    @property
    def text(self) -> str:
        """Returns the concatenated text of all messages in the response."""
        return "\n".join(message.text for message in self.messages)


class ChatResponseUpdate(BaseModel):
    """Represents a single streaming response chunk from a `ModelClient`."""
    contents: List[AIContent]
    """The chat response update content items."""

    additional_properties: Dict[str, Any] | None = None
    """Any additional properties associated with the chat response update."""
    author_name: str | None = None
    """The name of the author of the response update."""
    conversation_id: str | None = None
    """An identifier for the state of the conversation of which this update is a part."""
    created_at: CreatedAtT | None = None  # use a datetimeoffset type?
    """A timestamp for the chat response update."""
    finish_reason: ChatFinishReason | None = None
    """The finish reason for the operation."""
    message_id: str | None = None
    """The ID of the message of which this update is a part."""
    model_id: str | None = None
    """The model ID associated with this response update."""
    raw_representation: Any | None = None
    """The raw representation of the chat response update from an underlying implementation."""
    response_id: str | None = None
    """The ID of the response of which this update is a part."""
    role: ChatRole | None = None
    """The role of the author of the response update."""

    @property
    def text(self) -> str:
        """Returns the concatenated text of all contents in the update."""
        return "\n".join(content.text for content in self.contents if isinstance(content, TextContent))

    def with_(self, contents: List[AIContent] | None = None, message_id: str | None = None) -> Self:
        """Returns a new instance with the specified contents and message_id."""
        contents |= []
        return self.model_copy(update={
            "contents": self.contents + contents,
            "message_id": message_id or self.message_id,
        })

    @staticmethod
    def join(updates: Sequence[Self]) -> ChatResponse:
        """Joins multiple updates into a single ChatResponse."""
        if not updates:
            return ChatResponse(messages=[])

        conversation_id: str | None = None
        created_at: CreatedAtT | None = None
        finish_reason: ChatFinishReason | None = None
        model_id: str | None = None
        raw_representation: List[Any | None] = []
        additional_properties: Dict[str, Any] | None = None
        response_id: str | None = None
        role: ChatRole | None = None

        messages = []
        for update in updates:
            message = ChatMessage(
                author_name=update.author_name,
                contents=update.contents,
                message_id=update.message_id,
                role=ChatRole.ASSISTANT,  # Assuming the role is always ASSISTANT for updates
            )
            messages.append(message)
            conversation_id = update.conversation_id or conversation_id
            created_at = update.created_at or created_at
            finish_reason = update.finish_reason or finish_reason
            model_id = update.model_id or model_id
            role = update.role or role  # Assuming the role is always the same for updates

            raw_representation += [update.raw_representation]  # Collect raw representations
            # Do we really need to merge additional_properties? Should we do more than flat-merge?
            additional_properties = (additional_properties or {}) | (update.additional_properties or {})

        return ChatResponse(
          messages=messages,
          conversation_id=conversation_id,
          created_at=created_at,
          finish_reason=finish_reason,
          model_id=model_id,
          raw_representation=raw_representation,
          response_id=response_id,
          additional_properties=additional_properties)
