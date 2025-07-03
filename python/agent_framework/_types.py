# Copyright (c) Microsoft. All rights reserved.

import base64
import re
import sys
from collections.abc import AsyncIterable, Sequence
from typing import Annotated, Any, ClassVar, Generic, Literal, Protocol, TypeVar, overload, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from ._pydantic import AFBaseModel
from ._tools import AITool
from .guard_rails import InputGuardrail, OutputGuardrail

if sys.version_info >= (3, 12):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict
if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

# region: Constants and types
_T = TypeVar("_T")
TValue = TypeVar("TValue")
TInput = TypeVar("TInput")
TResponse = TypeVar("TResponse")
TChatResponse = TypeVar("TChatResponse", bound="ChatResponse")
TChatToolMode = TypeVar("TChatToolMode", bound="ChatToolMode")

CreatedAtT = str  # Use a datetimeoffset type? Or a more specific type like datetime.datetime?


URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$")

KNOWN_MEDIA_TYPES = [
    "application/json",
    "application/octet-stream",
    "application/pdf",
    "application/xml",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "image/apng",
    "image/avif",
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/svg+xml",
    "image/tiff",
    "image/webp",
    "text/css",
    "text/csv",
    "text/html",
    "text/javascript",
    "text/plain",
    "text/plain;charset=UTF-8",
    "text/xml",
]


class AdditionalCounts(TypedDict, total=False):
    """Represents well-known additional counts for usage. This is not an exhaustive list.

    Remarks:
        To make it possible to avoid colisions between similarly-named, but unrelated, additional counts
        between different AI services, any keys not explicitly defined here should be prefixed with the
        name of the AI service, e.g., "openai." or "azure.". The separator "." was chosen because it cannot
        be a legal character in a JSON key.

        Over time additional counts may be added to this class.
    """

    thought_token_count: int
    """The number of tokens used for thought processing."""
    image_token_count: int
    """The number of token equivalents used for image processing."""


class UsageDetails(AFBaseModel):
    """Provides usage details about a request/response."""

    input_token_count: int | None = None
    """The number of tokens in the input."""
    output_token_count: int | None = None
    """The number of tokens in the output."""
    total_token_count: int | None = None
    """The total number of tokens used to produce the response."""
    additional_counts: AdditionalCounts | None = None
    """A dictionary of additional usage counts."""

    def __add__(self, other: "UsageDetails") -> "UsageDetails":
        """Combines two `UsageDetails` instances."""
        if not isinstance(other, UsageDetails):
            return NotImplemented

        additional_counts: AdditionalCounts = self.additional_counts or AdditionalCounts()
        if other.additional_counts:
            for key, value in other.additional_counts.items():
                # Do our best to do the right thing here.
                if isinstance(value, (int, str, float)):
                    additional_counts[key] = int(additional_counts.get(key, 0)) + int(value or 0)

        return UsageDetails(
            input_token_count=(self.input_token_count or 0) + (other.input_token_count or 0),
            output_token_count=(self.output_token_count or 0) + (other.output_token_count or 0),
            total_token_count=(self.total_token_count or 0) + (other.total_token_count or 0),
            additional_counts=additional_counts,
        )


def _process_update(response: "ChatResponse", update: "ChatResponseUpdate") -> None:
    """Processes a single update and modifies the response in place."""
    is_new_message = False
    if not response.messages or (update.message_id and response.messages[-1].message_id != update.message_id):
        is_new_message = True

    if is_new_message:
        message = ChatMessage(role=ChatRole.ASSISTANT, contents=[])
        response.messages.append(message)
    else:
        message = response.messages[-1]
    # Incorporate the update's properties into the message.
    if update.author_name is not None:
        message.author_name = update.author_name
    if update.role is not None:
        message.role = update.role
    if update.message_id:
        message.message_id = update.message_id
    for content in update.contents:
        if isinstance(content, UsageContent):
            if response.usage_details is None:
                response.usage_details = UsageDetails()
            response.usage_details += content.details
        else:
            message.contents.append(content)
    # Incorporate the update's properties into the response.
    if update.response_id:
        response.response_id = update.response_id
    if update.conversation_id is not None:
        response.conversation_id = update.conversation_id
    if update.created_at is not None:
        response.created_at = update.created_at
    if update.finish_reason is not None:
        response.finish_reason = update.finish_reason
    if update.ai_model_id is not None:
        response.ai_model_id = update.ai_model_id
    if update.additional_properties is not None:
        if response.additional_properties is None:
            response.additional_properties = {}
        response.additional_properties.update(update.additional_properties)


def _coalesce_text_content(
    contents: list["AIContents"], type: type["TextContent"] | type["TextReasoningContent"]
) -> None:
    """Take any subsequence Text or TextReasoningContent items and coalesce them into a single item."""
    if not contents:
        return
    coalesced_contents = []
    current_texts = []
    first_new_content = None
    for i, content in enumerate(contents):
        if isinstance(content, type):
            current_texts.append(content.text)
            if first_new_content is None:
                first_new_content = i
        else:
            if first_new_content is not None:
                new_content = type(text="\n".join(current_texts))
                new_content.raw_representation = contents[first_new_content].raw_representation
                new_content.additional_properties = contents[first_new_content].additional_properties
                # Store the replacement node. We inherit the properties of the first text node. We don't
                # currently propagate additional properties from the subsequent nodes. If we ever need to,
                # we can add that here.
                coalesced_contents.append(new_content)
                current_texts = []
                first_new_content = None
            coalesced_contents.append(content)
    if current_texts:
        coalesced_contents.append(type(text="\n".join(current_texts)))
    contents.clear()
    contents.extend(coalesced_contents)


def _finalize_response(response: "ChatResponse") -> None:
    """Finalizes the chat response by performing any necessary post-processing."""
    for msg in response.messages:
        _coalesce_text_content(msg.contents, TextContent)
        _coalesce_text_content(msg.contents, TextReasoningContent)


# region: AIContent


class AIContent(AFBaseModel):
    """Represents content used by AI services.

    Attributes:
        type: The type of content, which is always "ai" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content from an underlying implementation.

    """

    type: Literal["ai"] = "ai"
    additional_properties: dict[str, Any] | None = None
    """Additional properties for the content."""
    raw_representation: Any | None = Field(default=None, repr=False)
    """The raw representation of the content from an underlying implementation."""


class TextContent(AIContent):
    """Represents text content in a chat.

    Attributes:
        text: The text content represented by this instance.
        type: The type of content, which is always "text" for this class.
        raw_representation: Optional raw representation of the content.
        additional_properties: Optional additional properties associated with the content.
    """

    text: str
    type: Literal["text"] = "text"  # type: ignore[assignment]

    def __init__(
        self, text: str, *, raw_representation: Any | None = None, additional_properties: dict[str, Any] | None = None
    ):
        """Initializes a TextContent instance.

        Args:
            text: The text content represented by this instance.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """
        super().__init__(
            text=text,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )


class TextReasoningContent(AIContent):
    """Represents text reasoning content in a chat.

    Remarks:
        This class and `TextContent` are superficially similar, but distinct.

    Attributes:
        text: The text content represented by this instance.
        type: The type of content, which is always "text_reasoning" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.


    """  # TODO(): Should we merge these two classes, and use a property to distinguish them?

    text: str
    type: Literal["text_reasoning"] = "text_reasoning"  # type: ignore[assignment]

    def __init__(
        self, text: str, *, raw_representation: Any | None = None, additional_properties: dict[str, Any] | None = None
    ):
        """Initializes a TextReasoningContent instance.

        Args:
            text: The text content represented by this instance.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """
        super().__init__(
            text=text,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )


class DataContent(AIContent):
    """Represents binary data content with an associated media type (also known as a MIME type).

    Attributes:
        uri: The URI of the data represented by this instance, typically in the form of a data URI.
            Should be in the form: "data:{media_type};base64,{base64_data}".
        type: The type of content, which is always "data" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["data"] = "data"  # type: ignore[assignment]
    uri: str

    @overload
    def __init__(
        self,
        uri: str,
        *,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a DataContent instance with a URI.

        Remarks:
            This is for binary data that is represented as a data URI, not for online resources.
            Use `UriContent` for online resources.

        Args:
            uri: The URI of the data represented by this instance.
                Should be in the form: "data:{media_type};base64,{base64_data}".
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """

    @overload
    def __init__(
        self,
        data: bytes,
        media_type: str,
        *,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a DataContent instance with binary data.

        Remarks:
            This is for binary data that is represented as a data URI, not for online resources.
            Use `UriContent` for online resources.

        Args:
            data: The binary data represented by this instance.
                The data is transformed into a base64-encoded data URI.
            media_type: The media type of the data.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """

    def __init__(
        self,
        uri=None,
        data=None,
        media_type=None,
        *,
        raw_representation=None,
        additional_properties=None,
    ) -> None:
        """Initializes a DataContent instance.

        Remarks:
            This is for binary data that is represented as a data URI, not for online resources.
            Use `UriContent` for online resources.
        """
        if uri is None:
            if data is None or media_type is None:
                raise ValueError("Either 'data' and 'media_type' or 'uri' must be provided.")
            uri = f"data:{media_type};base64,{base64.b64encode(data).decode('utf-8')}"
        super().__init__(
            uri=uri,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )

    @field_validator("uri", mode="after")
    @classmethod
    def _validate_uri(cls, uri: str) -> str:
        """Validates the URI format and extracts the media type.

        Minimal data URI parser based on RFC 2397: https://datatracker.ietf.org/doc/html/rfc2397.
        """
        match = URI_PATTERN.match(uri)
        if not match:
            raise ValueError(f"Invalid data URI format: {uri}")
        media_type = match.group("media_type")
        if media_type not in KNOWN_MEDIA_TYPES:
            raise ValueError(f"Unknown media type: {media_type}")
        return uri


class UriContent(AIContent):
    """Represents a URI content.

    Remarks:
        This is used for content that is identified by a URI, such as an image or a file.
        For (binary) data URIs, use `DataContent` instead.

    Attributes:
        uri: The URI of the content, e.g., 'https://example.com/image.png'.
        media_type: The media type of the content, e.g., 'image/png', 'application/json', etc.
        type: The type of content, which is always "uri" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["uri"] = "uri"  # type: ignore[assignment]
    uri: str
    """The URI of the content, e.g., 'https://example.com/image.png'."""
    media_type: str
    """The media type of the content, e.g., 'image/png', 'application/json', etc."""

    def __init__(
        self,
        uri: str,
        media_type: str,
        *,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a UriContent instance.

        Remarks:
            This is used for content that is identified by a URI, such as an image or a file.
            For (binary) data URIs, use `DataContent` instead.

        Args:
            uri: The URI of the content.
            media_type: The media type of the content.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """
        super().__init__(
            uri=uri,
            media_type=media_type,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )


class ErrorContent(AIContent):
    """Represents an error.

    Remarks:
        Typically used for non-fatal errors, where something went wrong as part of the operation,
        but the operation was still able to continue.

    Attributes:
        type: The type of content, which is always "error" for this class.
        error_code: The error code associated with the error.
        details: Additional details about the error.
        message: The error message.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.


    """

    type: Literal["error"] = "error"  # type: ignore[assignment]
    error_code: str | None = None
    """The error code associated with the error."""
    details: str | None = None
    """Additional details about the error."""
    message: str | None
    """The error message."""

    def __init__(
        self,
        *,
        message: str | None = None,
        error_code: str | None = None,
        details: str | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes an ErrorContent instance.

        Args:
            message: The error message.
            error_code: The error code associated with the error.
            details: Additional details about the error.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """
        super().__init__(
            message=message,
            error_code=error_code,
            details=details,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )

    def __str__(self) -> str:
        """Returns a string representation of the error."""
        return f"Error {self.error_code}: {self.message}" if self.error_code else self.message or "Unknown error"


class FunctionCallContent(AIContent):
    """Represents a function call request.

    Attributes:
        type: The type of content, which is always "function_call" for this class.
        call_id: The function call identifier.
        name: The name of the function requested.
        arguments: The arguments requested to be provided to the function.
        exception: Any exception that occurred while mapping the original function call data to this representation.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["function_call"] = "function_call"  # type: ignore[assignment]
    call_id: str
    """The function call identifier."""
    name: str
    """The name of the function requested."""
    arguments: dict[str, Any | None] | None = None
    """The arguments requested to be provided to the function."""
    exception: Exception | None = None
    """Any exception that occurred while mapping the original function call data to this representation."""

    def __init__(
        self,
        *,
        call_id: str,
        name: str,
        arguments: dict[str, Any | None] | None = None,
        exception: Exception | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a FunctionCallContent instance.

        Args:
            call_id: The function call identifier.
            name: The name of the function requested.
            arguments: The arguments requested to be provided to the function.
            exception: Any exception that occurred while mapping the original function call data to this representation.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """
        super().__init__(
            call_id=call_id,
            name=name,
            arguments=arguments,
            exception=exception,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )


class FunctionResultContent(AIContent):
    """Represents the result of a function call.

    Attributes:
        type: The type of content, which is always "function_result" for this class.
        call_id: The identifier of the function call for which this is the result.
        result: The result of the function call, or a generic error message if the function call failed.
        exception: An exception that occurred if the function call failed.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["function_result"] = "function_result"  # type: ignore[assignment]
    call_id: str
    """The identifier of the function call for which this is the result."""
    result: Any | None = None
    """The result of the function call, or a generic error message if the function call failed."""
    exception: Exception | None = None
    """An exception that occurred if the function call failed."""

    def __init__(
        self,
        *,
        call_id: str,
        result: Any | None = None,
        exception: Exception | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a FunctionResultContent instance.

        Args:
            call_id: The identifier of the function call for which this is the result.
            result: The result of the function call, or a generic error message if the function call failed.
            exception: An exception that occurred if the function call failed.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """
        super().__init__(
            call_id=call_id,
            result=result,
            exception=exception,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )


class UsageContent(AIContent):
    """Represents usage information associated with a chat request and response.

    Attributes:
        type: The type of content, which is always "usage" for this class.
        details: The usage information, including input and output token counts, and any additional counts.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["usage"] = "usage"  # type: ignore[assignment]
    details: UsageDetails
    """The usage information."""

    def __init__(
        self,
        details: UsageDetails,
        *,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a UsageContent instance.

        Args:
            details: The usage information.
            raw_representation: Optional raw representation of the content.
            additional_properties: Optional additional properties associated with the content.
        """
        super().__init__(
            type=self.type,
            details=details,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )


AIContents = Annotated[
    TextContent
    | DataContent
    | TextReasoningContent
    | UriContent
    | FunctionCallContent
    | FunctionResultContent
    | ErrorContent
    | UsageContent,
    Field(discriminator="type"),
]

# region: Chat Response constants


class ChatRole(AFBaseModel):
    """Describes the intended purpose of a message within a chat interaction.

    Attributes:
        value: The string representation of the role.

    Properties:
        SYSTEM: The role that instructs or sets the behaviour of the AI system.
        USER: The role that provides user input for chat interactions.
        ASSISTANT: The role that provides responses to system-instructed, user-prompted input.
        TOOL: The role that provides additional information and references in response to tool use requests.
    """

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
ChatRole.SYSTEM = ChatRole(value="system")  # type: ignore[assignment]
ChatRole.USER = ChatRole(value="user")  # type: ignore[assignment]
ChatRole.ASSISTANT = ChatRole(value="assistant")  # type: ignore[assignment]
ChatRole.TOOL = ChatRole(value="tool")  # type: ignore[assignment]


class ChatFinishReason(AFBaseModel):
    """Represents the reason a chat response completed.

    Attributes:
        value: The string representation of the finish reason.

    Properties:
        CONTENT_FILTER: The model filtered content, whether for safety, prohibited content, sensitive content,
            or other such issues.
        LENGTH: The model reached the maximum length allowed for the request and/or response (typically in
            terms of tokens).
        STOP: The model encountered a natural stop point or provided stop sequence.
        TOOL_CALLS: The model requested the use of a tool that was defined in the request.

    """

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


ChatFinishReason.CONTENT_FILTER = ChatFinishReason(value="content_filter")  # type: ignore[assignment]
ChatFinishReason.LENGTH = ChatFinishReason(value="length")  # type: ignore[assignment]
ChatFinishReason.STOP = ChatFinishReason(value="stop")  # type: ignore[assignment]
ChatFinishReason.TOOL_CALLS = ChatFinishReason(value="tool_calls")  # type: ignore[assignment]

# region: ChatMessage


class ChatMessage(AFBaseModel):
    """Represents a chat message used by a `ModelClient`.

    Attributes:
        role: The role of the author of the message.
        contents: The chat message content items.
        author_name: The name of the author of the message.
        message_id: The ID of the chat message.
        raw_representation: The raw representation of the chat message from an underlying implementation.
        additional_properties: Any additional properties associated with the chat message.

    """

    role: ChatRole
    """The role of the author of the message."""
    contents: list[AIContents]
    """The chat message content items."""
    author_name: str | None
    """The name of the author of the message."""
    message_id: str | None
    """The ID of the chat message."""
    raw_representation: Any | None = None
    """The raw representation of the chat message from an underlying implementation."""
    additional_properties: dict[str, Any] | None = None
    """Any additional properties associated with the chat message."""

    @property
    def text(self) -> str:
        """Returns the text content of the message.

        Remarks:
            This property concatenates the text of all TextContent objects in Contents.
        """
        return "\n".join(content.text for content in self.contents if isinstance(content, TextContent))

    @overload
    def __init__(
        self,
        role: ChatRole | Literal["system", "user", "assistant", "tool"],
        text: str,
        *,
        author_name: str | None = None,
        message_id: str | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a ChatMessage with a role and text content.

        Args:
            role: The role of the author of the message.
            text: The text content of the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            raw_representation: Optional raw representation of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
        """

    @overload
    def __init__(
        self,
        role: ChatRole | Literal["system", "user", "assistant", "tool"],
        contents: list[AIContents],
        *,
        author_name: str | None = None,
        message_id: str | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a ChatMessage with a role and optional contents.

        Args:
            role: The role of the author of the message.
            contents: Optional list of AIContent items to include in the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            raw_representation: Optional raw representation of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
        """

    def __init__(
        self,
        role,
        text=None,
        contents=None,
        *,
        author_name=None,
        message_id=None,
        raw_representation=None,
        additional_properties=None,
    ) -> None:
        if contents is None:
            contents: list[AIContents] = []
        if text is not None:
            contents.append(TextContent(text=text))
        if isinstance(role, str):
            role = ChatRole(value=role)
        super().__init__(
            role=role,
            contents=contents,
            author_name=author_name,
            message_id=message_id,
            raw_representation=raw_representation,
            additional_properties=additional_properties,
        )


# region: ChatResponse


class ChatResponse(AFBaseModel):
    """Represents the response to a chat request.

    Attributes:
        messages: The list of chat messages in the response.
        response_id: The ID of the chat response.
        conversation_id: An identifier for the state of the conversation.
        ai_model_id: The model ID used in the creation of the chat response.
        created_at: A timestamp for the chat response.
        finish_reason: The reason for the chat response.
        usage_details: The usage details for the chat response.
        additional_properties: Any additional properties associated with the chat response.
        raw_representation: The raw representation of the chat response from an underlying implementation.


    """

    messages: list[ChatMessage]
    """The chat response messages."""

    response_id: str | None = None
    """The ID of the chat response."""
    conversation_id: str | None = None
    """An identifier for the state of the conversation."""
    ai_model_id: str | None = Field(default=None, alias="model_id")
    """The model ID used in the creation of the chat response."""
    created_at: CreatedAtT | None = None  # use a datetimeoffset type?
    """A timestamp for the chat response."""
    finish_reason: ChatFinishReason | None = None
    """The reason for the chat response."""
    usage_details: UsageDetails | None = None
    """The usage details for the chat response."""
    additional_properties: dict[str, Any] | None = None
    """Any additional properties associated with the chat response."""
    raw_representation: Any | None = None
    """The raw representation of the chat response from an underlying implementation."""

    @property
    def text(self) -> str:
        """Returns the concatenated text of all messages in the response."""
        return "\n".join(message.text for message in self.messages if isinstance(message, ChatMessage))

    @overload
    def __init__(
        self,
        messages: ChatMessage | Sequence[ChatMessage],
        *,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatResponse with the provided parameters.

        Args:
            messages: A single ChatMessage or a sequence of ChatMessage objects to include in the response.
            response_id: Optional ID of the chat response.
            conversation_id: Optional identifier for the state of the conversation.
            model_id: Optional model ID used in the creation of the chat response.
            created_at: Optional timestamp for the chat response.
            finish_reason: Optional reason for the chat response.
            usage_details: Optional usage details for the chat response.
            messages: List of ChatMessage objects to include in the response.
            additional_properties: Optional additional properties associated with the chat response.
            raw_representation: Optional raw representation of the chat response from an underlying implementation.

        """

    @overload
    def __init__(
        self,
        text: TextContent | str,
        *,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatResponse with the provided parameters.

        Args:
            text: The text content to include in the response. If provided, it will be added as a ChatMessage.
            response_id: Optional ID of the chat response.
            conversation_id: Optional identifier for the state of the conversation.
            model_id: Optional model ID used in the creation of the chat response.
            created_at: Optional timestamp for the chat response.
            finish_reason: Optional reason for the chat response.
            usage_details: Optional usage details for the chat response.
            additional_properties: Optional additional properties associated with the chat response.
            raw_representation: Optional raw representation of the chat response from an underlying implementation.

        """

    def __init__(
        self,
        messages=None,
        text=None,
        *,
        response_id=None,
        conversation_id=None,
        model_id=None,
        created_at=None,
        finish_reason=None,
        usage_details=None,
        additional_properties=None,
        raw_representation=None,
    ) -> None:
        """Initializes a ChatResponse with the provided parameters."""
        if messages is None:
            messages = []
        if isinstance(messages, ChatMessage):
            messages = [messages]
        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            messages.append(ChatMessage(role=ChatRole.ASSISTANT, contents=[text]))

        super().__init__(
            messages=messages,
            response_id=response_id,
            conversation_id=conversation_id,
            ai_model_id=model_id,
            created_at=created_at,
            finish_reason=finish_reason,
            usage_details=usage_details,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_chat_response_updates(cls: type[_T], updates: Sequence["ChatResponseUpdate"]) -> _T:
        """Joins multiple updates into a single ChatResponse."""
        msg = cls(messages=[])
        for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        return msg

    @classmethod
    async def from_chat_response_generator(cls: type[_T], updates: AsyncIterable["ChatResponseUpdate"]) -> _T:
        """Joins multiple updates into a single ChatResponse."""
        msg = cls(messages=[])
        async for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        return msg


class StructuredResponse(ChatResponse, Generic[TValue]):
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

    @overload
    def __init__(
        self,
        value: TValue,
        *,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a StructuredResponse with the provided parameters."""

    @overload
    def __init__(
        self,
        text: TextContent | str,
        value: TValue,
        *,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a StructuredResponse with the provided parameters."""

    @overload
    def __init__(
        self,
        messages: Sequence[ChatMessage],
        value: TValue,
        *,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a StructuredResponse with the provided parameters."""

    def __init__(
        self,
        messages=None,
        text=None,
        value=None,
        *,
        response_id=None,
        conversation_id=None,
        model_id=None,
        created_at=None,
        finish_reason=None,
        usage_details=None,
        additional_properties=None,
        raw_representation=None,
    ) -> None:
        """Initializes a StructuredResponse with the provided parameters."""
        if messages is None:
            messages = []
        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            messages.append(ChatMessage(role=ChatRole.ASSISTANT, contents=[text]))

        if value is None:
            raise ValueError("value must be provided for StructuredResponse")
        super().__init__(
            value=value,
            messages=messages,
            additional_properties=additional_properties,
            conversation_id=conversation_id,
            created_at=created_at,
            finish_reason=finish_reason,
            ai_model_id=model_id,
            raw_representation=raw_representation,
            response_id=response_id,
            usage_details=usage_details,
        )


# region: ChatResponseUpdate


class ChatResponseUpdate(AFBaseModel):
    """Represents a single streaming response chunk from a `ModelClient`.

    Attributes:
        contents: The chat response update content items.
        role: The role of the author of the response update.
        author_name: The name of the author of the response update.
        response_id: The ID of the response of which this update is a part.
        message_id: The ID of the message of which this update is a part.
        conversation_id: An identifier for the state of the conversation of which this update is a part.
        ai_model_id: The model ID associated with this response update.
        created_at: A timestamp for the chat response update.
        finish_reason: The finish reason for the operation.
        additional_properties: Any additional properties associated with the chat response update.
        raw_representation: The raw representation of the chat response update from an underlying implementation.

    """

    contents: list[AIContents]
    """The chat response update content items."""

    role: ChatRole | None = None
    """The role of the author of the response update."""
    author_name: str | None = None
    """The name of the author of the response update."""
    response_id: str | None = None
    """The ID of the response of which this update is a part."""
    message_id: str | None = None
    """The ID of the message of which this update is a part."""

    conversation_id: str | None = None
    """An identifier for the state of the conversation of which this update is a part."""
    ai_model_id: str | None = Field(default=None, alias="model_id")
    """The model ID associated with this response update."""
    created_at: CreatedAtT | None = None  # use a datetimeoffset type?
    """A timestamp for the chat response update."""
    finish_reason: ChatFinishReason | None = None
    """The finish reason for the operation."""

    additional_properties: dict[str, Any] | None = None
    """Any additional properties associated with the chat response update."""
    raw_representation: Any | None = None
    """The raw representation of the chat response update from an underlying implementation."""

    @overload
    def __init__(
        self,
        contents: list[AIContent],
        *,
        additional_properties: dict[str, Any] | None = None,
        author_name: str | None = None,
        conversation_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        message_id: str | None = None,
        ai_model_id: str | None = None,
        raw_representation: Any | None = None,
        response_id: str | None = None,
        role: ChatRole | None = None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""

    @overload
    def __init__(
        self,
        text: TextContent | str,
        *,
        additional_properties: dict[str, Any] | None = None,
        author_name: str | None = None,
        conversation_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        message_id: str | None = None,
        ai_model_id: str | None = None,
        raw_representation: Any | None = None,
        response_id: str | None = None,
        role: ChatRole | None = None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""

    def __init__(
        self,
        contents=None,
        text=None,
        *,
        additional_properties=None,
        author_name=None,
        conversation_id=None,
        created_at=None,
        finish_reason=None,
        message_id=None,
        ai_model_id=None,
        raw_representation=None,
        response_id=None,
        role=None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""
        if contents is None:
            contents = []
        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            contents.append(text)

        super().__init__(
            contents=contents,
            additional_properties=additional_properties,
            author_name=author_name,
            conversation_id=conversation_id,
            created_at=created_at,
            finish_reason=finish_reason,
            message_id=message_id,
            ai_model_id=ai_model_id,
            raw_representation=raw_representation,
            response_id=response_id,
            role=role,
        )

    @property
    def text(self) -> str:
        """Returns the concatenated text of all contents in the update."""
        return "\n".join(content.text for content in self.contents if isinstance(content, TextContent))

    def with_(self, contents: list[AIContent] | None = None, message_id: str | None = None) -> Self:
        """Returns a new instance with the specified contents and message_id."""
        if contents is None:
            contents = []

        return self.model_copy(
            update={
                "contents": self.contents + contents,
                "message_id": message_id or self.message_id,
            }
        )


# region: ChatOptions


class ChatToolMode(AFBaseModel):
    """Defines if and how tools are used in a chat request."""

    mode: Literal["auto", "required", "none"] = "none"
    required_function_name: str | None = None

    AUTO: ClassVar[Self]  # type: ignore[assignment]
    REQUIRED_ANY: ClassVar[Self]  # type: ignore[assignment]
    NONE: ClassVar[Self]  # type: ignore[assignment]

    @classmethod
    def REQUIRED(cls: type[TChatToolMode], function_name: str | None = None) -> TChatToolMode:
        """Returns a ChatToolMode that requires the specified function to be called."""
        return cls(mode="required", required_function_name=function_name)


ChatToolMode.AUTO = ChatToolMode(mode="auto")  # type: ignore[assignment]
ChatToolMode.REQUIRED_ANY = ChatToolMode(mode="required")  # type: ignore[assignment]
ChatToolMode.NONE = ChatToolMode(mode="none")  # type: ignore[assignment]


class ChatOptions(AFBaseModel):
    """Common request settings for AI services."""

    ai_model_id: Annotated[str | None, Field(serialization_alias="model")] = None
    frequency_penalty: Annotated[float | None, Field(ge=-2.0, le=2.0)] = None
    logit_bias: dict[str | int, float] | None = None
    max_tokens: Annotated[int | None, Field(gt=0)] = None
    messages: list[dict[str, Any]] | None = Field(default=None, description="List of messages for the chat completion.")
    presence_penalty: Annotated[float | None, Field(ge=-2.0, le=2.0)] = None
    response_format: type[BaseModel] | None = Field(
        default=None, description="Structured output response format schema. Must be a valid Pydantic model."
    )
    seed: int | None = None
    stop: str | list[str] | None = None
    temperature: Annotated[float | None, Field(ge=0.0, le=2.0)] = None
    tool_choice: ChatToolMode | Literal["auto", "required", "none"] | dict[str, Any] | None = None
    tools: list[AITool] | None = None
    top_p: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    user: str | None = None
    store: bool | None = None
    metadata: dict[str, str] | None = None
    additional_properties: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific additional properties."
    )

    @field_validator("tool_choice", mode="before")
    @classmethod
    def _validate_tool_mode(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Validates the tool_choice field to ensure it is a valid ChatToolMode."""
        if isinstance(data, dict):
            tool_choice = data.get("tool_choice")
            if isinstance(tool_choice, str):
                if tool_choice == "auto":
                    data["tool_choice"] = ChatToolMode.AUTO
                elif tool_choice == "required":
                    data["tool_choice"] = ChatToolMode.REQUIRED_ANY
                elif tool_choice == "none":
                    data["tool_choice"] = ChatToolMode.NONE
                else:
                    raise ValueError(f"Invalid tool choice: {tool_choice}")
            elif isinstance(tool_choice, dict):
                data["tool_choice"] = ChatToolMode.model_validate(tool_choice)
        return data

    def to_provider_settings(self, by_alias: bool = True, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert the ChatOptions to a dictionary suitable for provider requests.

        Args:
            by_alias: Use alias names for fields if True.
            exclude: Additional keys to exclude from the output.

        Returns:
            Dictionary of settings for provider.
        """
        default_exclude = {"additional_properties"}
        merged_exclude = default_exclude if exclude is None else default_exclude | set(exclude)

        settings = self.model_dump(exclude_none=True, by_alias=by_alias, exclude=merged_exclude)
        settings = {k: v for k, v in settings.items() if v and not isinstance(v, dict)}
        settings.update(self.additional_properties)
        for key in merged_exclude:
            settings.pop(key, None)
        return settings


# region: ModelClient Protocol


@runtime_checkable
class ModelClient(Protocol, Generic[TInput, TResponse]):
    """A protocol for a model client that can generate responses."""

    async def get_response(
        self,
        messages: TInput | Sequence[TInput],
        **kwargs: Any,
    ) -> TResponse:
        """Sends input and returns the response.

        Args:
            messages: The sequence of input messages to send.
            **kwargs: Additional options for the request, such as ai_model_id, temperature, etc.
                       See `ChatOptions` for more details.

        Returns:
            The response messages generated by the client.

        Raises:
            ValueError: If the input message sequence is `None`.
        """
        ...

    async def get_streaming_response(
        self,
        messages: TInput | Sequence[TInput],
        **kwargs: Any,  # kwargs?
    ) -> AsyncIterable[TResponse]:
        """Sends input messages and streams the response.

        Args:
            messages: The sequence of input messages to send.
            **kwargs: Additional options for the request, such as ai_model_id, temperature, etc.
                       See `ChatOptions` for more details.

        Returns:
            An async iterable of chat response updates containing the content of the response messages
            generated by the client.

        Raises:
            ValueError: If the input message sequence is `None`.
        """
        ...

    def add_input_guardrails(self, guardrails: list[InputGuardrail[TInput]]) -> None:
        """Add input guardrails to the model client.

        Args:
            guardrails: The list of input guardrails to add.
        """
        ...

    def add_output_guardrails(self, guardrails: list[OutputGuardrail[TResponse | Sequence[TResponse]]]) -> None:
        """Add output guardrails to the model client.

        Args:
            guardrails: The list of output guardrails to add.
        """
        ...
