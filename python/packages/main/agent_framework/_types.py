# Copyright (c) Microsoft. All rights reserved.

import base64
import json
import re
import sys
from collections.abc import (
    AsyncIterable,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from typing import Annotated, Any, ClassVar, Generic, Literal, TypeVar, overload

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from ._pydantic import AFBaseModel
from ._tools import AITool, ai_function
from .exceptions import AgentFrameworkException

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

# region: Constants and types
_T = TypeVar("_T")
TValue = TypeVar("TValue")
TEmbedding = TypeVar("TEmbedding")
TChatResponse = TypeVar("TChatResponse", bound="ChatResponse")
TChatToolMode = TypeVar("TChatToolMode", bound="ChatToolMode")
TAgentRunResponse = TypeVar("TAgentRunResponse", bound="AgentRunResponse")

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


__all__ = [
    "AIContent",
    "AIContents",
    "AITool",
    "AgentRunResponse",
    "AgentRunResponseUpdate",
    "ChatFinishReason",
    "ChatMessage",
    "ChatOptions",
    "ChatResponse",
    "ChatResponseUpdate",
    "ChatRole",
    "ChatToolMode",
    "DataContent",
    "ErrorContent",
    "FunctionCallContent",
    "FunctionResultContent",
    "GeneratedEmbeddings",
    "SpeechToTextOptions",
    "StructuredResponse",
    "TextContent",
    "TextReasoningContent",
    "TextToSpeechOptions",
    "UriContent",
    "UsageContent",
    "UsageDetails",
]


class UsageDetails(AFBaseModel):
    """Provides usage details about a request/response.

    Attributes:
        input_token_count: The number of tokens in the input.
        output_token_count: The number of tokens in the output.
        total_token_count: The total number of tokens used to produce the response.
        additional_counts: A dictionary of additional token counts, can be set by passing kwargs.
    """

    model_config = ConfigDict(
        populate_by_name=True, arbitrary_types_allowed=True, validate_assignment=True, extra="allow"
    )
    __pydantic_extra__: dict[str, int]  # type: ignore[reportIncompatibleVariableOverride]
    """Overriding the default extras type, to make sure all extras are integers."""

    input_token_count: int | None = None
    """The number of tokens in the input."""
    output_token_count: int | None = None
    """The number of tokens in the output."""
    total_token_count: int | None = None
    """The total number of tokens used to produce the response."""

    def __init__(
        self,
        input_token_count: int | None = None,
        output_token_count: int | None = None,
        total_token_count: int | None = None,
        **kwargs: int,
    ) -> None:
        """Initializes the UsageDetails instance.

        Args:
            input_token_count: The number of tokens in the input.
            output_token_count: The number of tokens in the output.
            total_token_count: The total number of tokens used to produce the response.
            **kwargs: Additional token counts, can be set by passing keyword arguments.
                They can be retrieved through the `additional_counts` property.
        """
        super().__init__(
            input_token_count=input_token_count,  # type: ignore[reportCallIssue]
            output_token_count=output_token_count,  # type: ignore[reportCallIssue]
            total_token_count=total_token_count,  # type: ignore[reportCallIssue]
            **kwargs,
        )

    @property
    def additional_counts(self) -> dict[str, int]:
        """Represents well-known additional counts for usage. This is not an exhaustive list.

        Remarks:
            To make it possible to avoid collisions between similarly-named, but unrelated, additional counts
            between different AI services, any keys not explicitly defined here should be prefixed with the
            name of the AI service, e.g., "openai." or "azure.". The separator "." was chosen because it cannot
            be a legal character in a JSON key.

            Over time additional counts may be added to the base class.
        """
        return self.model_extra or {}

    def __add__(self, other: "UsageDetails | None") -> "UsageDetails":
        """Combines two `UsageDetails` instances."""
        if not other:
            return self
        if not isinstance(other, UsageDetails):
            raise ValueError("Can only add two usage details objects together.")

        additional_counts = self.additional_counts or {}
        if other.additional_counts:
            for key, value in other.additional_counts.items():
                additional_counts[key] = additional_counts.get(key, 0) + (value or 0)

        return UsageDetails(
            input_token_count=(self.input_token_count or 0) + (other.input_token_count or 0),
            output_token_count=(self.output_token_count or 0) + (other.output_token_count or 0),
            total_token_count=(self.total_token_count or 0) + (other.total_token_count or 0),
            **additional_counts,
        )

    def __iadd__(self, other: "UsageDetails | None") -> Self:
        if not other:
            return self
        if not isinstance(other, UsageDetails):
            raise ValueError("Can only add usage details objects together.")

        self.input_token_count = (self.input_token_count or 0) + (other.input_token_count or 0)
        self.output_token_count = (self.output_token_count or 0) + (other.output_token_count or 0)
        self.total_token_count = (self.total_token_count or 0) + (other.total_token_count or 0)

        for key, value in other.additional_counts.items():
            self.additional_counts[key] = self.additional_counts.get(key, 0) + (value or 0)

        return self


def _process_update(
    response: "ChatResponse | AgentRunResponse", update: "ChatResponseUpdate | AgentRunResponseUpdate"
) -> None:
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
        if (
            isinstance(content, FunctionCallContent)
            and len(message.contents) > 0
            and isinstance(message.contents[-1], FunctionCallContent)
        ):
            try:
                message.contents[-1] += content
            except AgentFrameworkException:
                message.contents.append(content)
        elif isinstance(content, UsageContent):
            if response.usage_details is None:
                response.usage_details = UsageDetails()
            response.usage_details += content.details
        else:
            message.contents.append(content)
    # Incorporate the update's properties into the response.
    if update.response_id:
        response.response_id = update.response_id
    if update.created_at is not None:
        response.created_at = update.created_at
    if update.additional_properties is not None:
        if response.additional_properties is None:
            response.additional_properties = {}
        response.additional_properties.update(update.additional_properties)

    if isinstance(response, ChatResponse) and isinstance(update, ChatResponseUpdate):
        if update.conversation_id is not None:
            response.conversation_id = update.conversation_id
        if update.finish_reason is not None:
            response.finish_reason = update.finish_reason
        if update.ai_model_id is not None:
            response.ai_model_id = update.ai_model_id


def _coalesce_text_content(
    contents: list["AIContents"], type_: type["TextContent"] | type["TextReasoningContent"]
) -> None:
    """Take any subsequence Text or TextReasoningContent items and coalesce them into a single item."""
    if not contents:
        return
    coalesced_contents: list["AIContents"] = []
    current_texts: list[str] = []
    first_new_content = None
    for i, content in enumerate(contents):
        if isinstance(content, type_):
            current_texts.append(content.text)  # type: ignore[union-attr]
            if first_new_content is None:
                first_new_content = i
        else:
            if first_new_content is not None:
                new_content = type_(text="".join(current_texts))
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
        coalesced_contents.append(type_(text="".join(current_texts)))
    contents.clear()
    contents.extend(coalesced_contents)


def _finalize_response(response: "ChatResponse | AgentRunResponse") -> None:
    """Finalizes the response by performing any necessary post-processing."""
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
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.
    """

    text: str
    type: Literal["text"] = "text"  # type: ignore[assignment]

    def __init__(
        self,
        text: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ):
        """Initializes a TextContent instance.

        Args:
            text: The text content represented by this instance.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            text=text,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,
            additional_properties=additional_properties,
            **kwargs,
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
        self,
        text: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ):
        """Initializes a TextReasoningContent instance.

        Args:
            text: The text content represented by this instance.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            text=text,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,
            additional_properties=additional_properties,
            **kwargs,
        )


class DataContent(AIContent):
    """Represents binary data content with an associated media type (also known as a MIME type).

    Attributes:
        uri: The URI of the data represented by this instance, typically in the form of a data URI.
            Should be in the form: "data:{media_type};base64,{base64_data}".
        type: The type of content, which is always "data" for this class.
        media_type: The media type of the data.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["data"] = "data"  # type: ignore[assignment]
    uri: str
    media_type: str | None = None

    @overload
    def __init__(
        self,
        *,
        uri: str,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a DataContent instance with a URI.

        Remarks:
            This is for binary data that is represented as a data URI, not for online resources.
            Use `UriContent` for online resources.

        Args:
            uri: The URI of the data represented by this instance.
                Should be in the form: "data:{media_type};base64,{base64_data}".
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """

    @overload
    def __init__(
        self,
        *,
        data: bytes,
        media_type: str,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a DataContent instance with binary data.

        Remarks:
            This is for binary data that is represented as a data URI, not for online resources.
            Use `UriContent` for online resources.

        Args:
            data: The binary data represented by this instance.
                The data is transformed into a base64-encoded data URI.
            media_type: The media type of the data.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """

    def __init__(
        self,
        *,
        uri: str | None = None,
        data: bytes | None = None,
        media_type: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a DataContent instance.

        Remarks:
            This is for binary data that is represented as a data URI, not for online resources.
            Use `UriContent` for online resources.

        Args:
            uri: The URI of the data represented by this instance.
                Should be in the form: "data:{media_type};base64,{base64_data}".
            data: The binary data represented by this instance.
                The data is transformed into a base64-encoded data URI.
            media_type: The media type of the data.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        if uri is None:
            if data is None or media_type is None:
                raise ValueError("Either 'data' and 'media_type' or 'uri' must be provided.")
            uri = f"data:{media_type};base64,{base64.b64encode(data).decode('utf-8')}"
        super().__init__(
            uri=uri,  # type: ignore[reportCallIssue]
            media_type=media_type,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,
            additional_properties=additional_properties,
            **kwargs,
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

    def has_top_level_media_type(self, top_level_media_type: str) -> bool:
        return _has_top_level_media_type(self.media_type, top_level_media_type)


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
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a UriContent instance.

        Remarks:
            This is used for content that is identified by a URI, such as an image or a file.
            For (binary) data URIs, use `DataContent` instead.

        Args:
            uri: The URI of the content.
            media_type: The media type of the content.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            uri=uri,  # type: ignore[reportCallIssue]
            media_type=media_type,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )

    def has_top_level_media_type(self, top_level_media_type: str) -> bool:
        return _has_top_level_media_type(self.media_type, top_level_media_type)


def _has_top_level_media_type(media_type: str | None, top_level_media_type: str) -> bool:
    if media_type is None:
        return False

    slash_index = media_type.find("/")
    span = media_type[:slash_index] if slash_index >= 0 else media_type
    span = span.strip()
    return span.lower() == top_level_media_type.lower()


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
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes an ErrorContent instance.

        Args:
            message: The error message.
            error_code: The error code associated with the error.
            details: Additional details about the error.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            message=message,  # type: ignore[reportCallIssue]
            error_code=error_code,  # type: ignore[reportCallIssue]
            details=details,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
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
    arguments: str | dict[str, Any | None] | None = None
    """The arguments requested to be provided to the function."""
    exception: Exception | None = None
    """Any exception that occurred while mapping the original function call data to this representation."""

    def __init__(
        self,
        *,
        call_id: str,
        name: str,
        arguments: str | dict[str, Any | None] | None = None,
        exception: Exception | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionCallContent instance.

        Args:
            call_id: The function call identifier.
            name: The name of the function requested.
            arguments: The arguments requested to be provided to the function,
                can be a string to allow gradual completion of the args.
            exception: Any exception that occurred while mapping the original function call data to this representation.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            call_id=call_id,  # type: ignore[reportCallIssue]
            name=name,  # type: ignore[reportCallIssue]
            arguments=arguments,  # type: ignore[reportCallIssue]
            exception=exception,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,
            additional_properties=additional_properties,
            **kwargs,
        )

    def parse_arguments(self) -> dict[str, Any | None] | None:
        if isinstance(self.arguments, str):
            # If arguments are a string, try to parse it as JSON
            try:
                loaded = json.loads(self.arguments)
                if isinstance(loaded, dict):
                    return loaded  # type:ignore
                return {"raw": loaded}
            except (json.JSONDecodeError, TypeError):
                return {"raw": self.arguments}
        return self.arguments

    def __add__(self, other: "FunctionCallContent") -> "FunctionCallContent":
        if not isinstance(other, FunctionCallContent):
            raise TypeError("Incompatible type")
        if other.call_id and self.call_id != other.call_id:
            raise AgentFrameworkException("Incompatible function call contents")
        if not self.arguments:
            arguments = other.arguments
        elif not other.arguments:
            arguments = self.arguments
        elif isinstance(self.arguments, str) and isinstance(other.arguments, str):
            arguments = self.arguments + other.arguments
        elif isinstance(self.arguments, dict) and isinstance(other.arguments, dict):
            arguments = {**self.arguments, **other.arguments}
        else:
            raise TypeError("Incompatible argument types")
        return FunctionCallContent(
            call_id=self.call_id,
            name=self.name,
            arguments=arguments,
            exception=self.exception or other.exception,
            additional_properties={**(self.additional_properties or {}), **(other.additional_properties or {})},
            raw_representation=self.raw_representation or other.raw_representation,
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
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionResultContent instance.

        Args:
            call_id: The identifier of the function call for which this is the result.
            result: The result of the function call, or a generic error message if the function call failed.
            exception: An exception that occurred if the function call failed.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            call_id=call_id,  # type: ignore[reportCallIssue]
            result=result,  # type: ignore[reportCallIssue]
            exception=exception,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,
            additional_properties=additional_properties,
            **kwargs,
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
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a UsageContent instance.

        Args:
            details: The usage information.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            details=details,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,
            additional_properties=additional_properties,
            **kwargs,
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
        additional_properties: Any additional properties associated with the chat message.
        raw_representation: The raw representation of the chat message from an underlying implementation.

    """

    role: ChatRole
    """The role of the author of the message."""
    contents: list[AIContents]
    """The chat message content items."""
    author_name: str | None
    """The name of the author of the message."""
    message_id: str | None
    """The ID of the chat message."""
    additional_properties: dict[str, Any] | None = None
    """Any additional properties associated with the chat message."""
    raw_representation: Any | None = None
    """The raw representation of the chat message from an underlying implementation."""

    @overload
    def __init__(
        self,
        role: ChatRole | Literal["system", "user", "assistant", "tool"],
        *,
        text: str,
        author_name: str | None = None,
        message_id: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatMessage with a role and text content.

        Args:
            role: The role of the author of the message.
            text: The text content of the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
            raw_representation: Optional raw representation of the chat message.
        """

    @overload
    def __init__(
        self,
        role: ChatRole | Literal["system", "user", "assistant", "tool"],
        *,
        contents: MutableSequence[AIContents],
        author_name: str | None = None,
        message_id: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatMessage with a role and optional contents.

        Args:
            role: The role of the author of the message.
            contents: Optional list of AIContent items to include in the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
            raw_representation: Optional raw representation of the chat message.
        """

    def __init__(
        self,
        role: ChatRole | Literal["system", "user", "assistant", "tool"],
        *,
        text: str | None = None,
        contents: MutableSequence[AIContents] | None = None,
        author_name: str | None = None,
        message_id: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        if contents is None:
            contents = []
        if text is not None:
            contents.append(TextContent(text=text))
        if isinstance(role, str):
            role = ChatRole(value=role)
        super().__init__(
            role=role,  # type: ignore[reportCallIssue]
            contents=contents,  # type: ignore[reportCallIssue]
            author_name=author_name,  # type: ignore[reportCallIssue]
            message_id=message_id,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,  # type: ignore[reportCallIssue]
        )

    @property
    def text(self) -> str:
        """Returns the text content of the message.

        Remarks:
            This property concatenates the text of all TextContent objects in Contents.
        """
        return " ".join(content.text for content in self.contents if isinstance(content, TextContent))


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

    @overload
    def __init__(
        self,
        *,
        messages: ChatMessage | MutableSequence[ChatMessage],
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
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
            **kwargs: Any additional keyword arguments.
        """

    @overload
    def __init__(
        self,
        *,
        text: TextContent | str,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
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
            **kwargs: Any additional keyword arguments.

        """

    def __init__(
        self,
        *,
        messages: ChatMessage | MutableSequence[ChatMessage] | None = None,
        text: TextContent | str | None = None,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a ChatResponse with the provided parameters."""
        if messages is None:
            messages = []
        elif not isinstance(messages, MutableSequence):
            messages = [messages]
        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            messages.append(ChatMessage(role=ChatRole.ASSISTANT, contents=[text]))

        super().__init__(
            messages=messages,  # type: ignore[reportCallIssue]
            response_id=response_id,  # type: ignore[reportCallIssue]
            conversation_id=conversation_id,  # type: ignore[reportCallIssue]
            ai_model_id=model_id,  # type: ignore[reportCallIssue]
            created_at=created_at,  # type: ignore[reportCallIssue]
            finish_reason=finish_reason,  # type: ignore[reportCallIssue]
            usage_details=usage_details,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,  # type: ignore[reportCallIssue]
            **kwargs,
        )

    @classmethod
    def from_chat_response_updates(cls: type[TChatResponse], updates: Sequence["ChatResponseUpdate"]) -> TChatResponse:
        """Joins multiple updates into a single ChatResponse."""
        msg = cls(messages=[])
        for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        return msg

    @classmethod
    async def from_chat_response_generator(
        cls: type[TChatResponse], updates: AsyncIterable["ChatResponseUpdate"]
    ) -> TChatResponse:
        """Joins multiple updates into a single ChatResponse."""
        msg = cls(messages=[])
        async for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        return msg

    @property
    def text(self) -> str:
        """Returns the concatenated text of all messages in the response."""
        return ("\n".join(message.text for message in self.messages if isinstance(message, ChatMessage))).strip()

    def __str__(self) -> str:
        return self.text


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
        messages: ChatMessage | MutableSequence[ChatMessage],
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a StructuredResponse with the provided parameters."""

    @overload
    def __init__(
        self,
        value: TValue,
        *,
        text: TextContent | str,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a StructuredResponse with the provided parameters."""

    def __init__(
        self,
        value: TValue,
        *,
        messages: ChatMessage | MutableSequence[ChatMessage] | None = None,
        text: TextContent | str | None = None,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        usage_details: UsageDetails | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a StructuredResponse with the provided parameters."""
        if messages is None:
            messages = []
        elif isinstance(messages, ChatMessage):
            messages = [messages]
        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            messages.append(ChatMessage(role=ChatRole.ASSISTANT, contents=[text]))

        super().__init__(
            value=value,
            messages=messages,
            conversation_id=conversation_id,
            created_at=created_at,
            finish_reason=finish_reason,
            model_id=model_id,
            response_id=response_id,
            usage_details=usage_details,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
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
        *,
        contents: list[AIContents],
        role: ChatRole | Literal["system", "user", "assistant", "tool"] | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        conversation_id: str | None = None,
        ai_model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""

    @overload
    def __init__(
        self,
        *,
        text: TextContent | str,
        role: ChatRole | Literal["system", "user", "assistant", "tool"] | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        conversation_id: str | None = None,
        ai_model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""

    def __init__(
        self,
        *,
        contents: list[AIContents] | None = None,
        text: TextContent | str | None = None,
        role: ChatRole | Literal["system", "user", "assistant", "tool"] | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        conversation_id: str | None = None,
        ai_model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: ChatFinishReason | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""
        if contents is None:
            contents = []
        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            contents.append(text)
        if role and isinstance(role, str):
            role = ChatRole(value=role)
        super().__init__(
            contents=contents,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,  # type: ignore[reportCallIssue]
            author_name=author_name,  # type: ignore[reportCallIssue]
            conversation_id=conversation_id,  # type: ignore[reportCallIssue]
            created_at=created_at,  # type: ignore[reportCallIssue]
            finish_reason=finish_reason,  # type: ignore[reportCallIssue]
            message_id=message_id,  # type: ignore[reportCallIssue]
            ai_model_id=ai_model_id,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,  # type: ignore[reportCallIssue]
            response_id=response_id,  # type: ignore[reportCallIssue]
            role=role,  # type: ignore[reportCallIssue]
        )

    @property
    def text(self) -> str:
        """Returns the concatenated text of all contents in the update."""
        return "".join(content.text for content in self.contents if isinstance(content, TextContent))

    def __str__(self) -> str:
        return self.text

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

    def __eq__(self, other: object) -> bool:
        """Checks equality with another ChatToolMode or string."""
        if isinstance(other, str):
            return self.mode == other
        if isinstance(other, ChatToolMode):
            return self.mode == other.mode and self.required_function_name == other.required_function_name
        return False

    @model_serializer
    def serialize_model(self) -> str:
        """Serializes the ChatToolMode to just the mode string."""
        return self.mode


ChatToolMode.AUTO = ChatToolMode(mode="auto")  # type: ignore[assignment]
ChatToolMode.REQUIRED_ANY = ChatToolMode(mode="required")  # type: ignore[assignment]
ChatToolMode.NONE = ChatToolMode(mode="none")  # type: ignore[assignment]


class ChatOptions(AFBaseModel):
    """Common request settings for AI services."""

    additional_properties: MutableMapping[str, Any] = Field(
        default_factory=dict, description="Provider-specific additional properties."
    )
    ai_model_id: Annotated[str | None, Field(serialization_alias="model")] = None
    allow_multiple_tool_calls: bool | None = None
    conversation_id: str | None = None
    frequency_penalty: Annotated[float | None, Field(ge=-2.0, le=2.0)] = None
    logit_bias: MutableMapping[str | int, float] | None = None
    max_tokens: Annotated[int | None, Field(gt=0)] = None
    metadata: MutableMapping[str, str] | None = None
    presence_penalty: Annotated[float | None, Field(ge=-2.0, le=2.0)] = None
    response_format: type[BaseModel] | None = Field(
        default=None, description="Structured output response format schema. Must be a valid Pydantic model."
    )
    seed: int | None = None
    stop: str | Sequence[str] | None = None
    store: bool | None = None
    temperature: Annotated[float | None, Field(ge=0.0, le=2.0)] = None
    tool_choice: ChatToolMode | Literal["auto", "required", "none"] | Mapping[str, Any] | None = None
    tools: list[AITool | MutableMapping[str, Any]] | None = None
    top_p: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    user: str | None = None
    _ai_tools: list[AITool | MutableMapping[str, Any]] | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _copy_to_ai_tools(self) -> Self:
        if self.tools and not self._ai_tools:
            self._ai_tools = self.tools
        return self

    @field_validator("tools", mode="before")
    @classmethod
    def _validate_tools(
        cls,
        tools: (
            AITool
            | list[AITool]
            | Callable[..., Any]
            | list[Callable[..., Any]]
            | MutableMapping[str, Any]
            | list[MutableMapping[str, Any]]
            | None
        ),
    ) -> list[AITool | MutableMapping[str, Any]] | None:
        """Parse the tools field.

        All tools are stored in both tools and _ai_tools.
        """
        if not tools:
            return None
        if not isinstance(tools, list):
            tools = [tools]  # type: ignore[reportAssignmentType, assignment]
        for idx, tool in enumerate(tools):  # type: ignore[reportArgumentType, arg-type]
            if not isinstance(tool, (AITool, MutableMapping)):
                # Convert to AITool if it's a function or callable
                tools[idx] = ai_function(tool)  # type: ignore[reportIndexIssues, reportCallIssue, reportArgumentType, index, call-overload, arg-type]
        return tools  # type: ignore[reportReturnType, return-value]

    @field_validator("tool_choice", mode="before")
    @classmethod
    def _validate_tool_mode(
        cls, tool_choice: ChatToolMode | Literal["auto", "required", "none"] | Mapping[str, Any] | None
    ) -> ChatToolMode | None:
        """Validates the tool_choice field to ensure it is a valid ChatToolMode."""
        if not tool_choice:
            return None
        if isinstance(tool_choice, str):
            match tool_choice:
                case "auto":
                    return ChatToolMode.AUTO
                case "required":
                    return ChatToolMode.REQUIRED_ANY
                case "none":
                    return ChatToolMode.NONE
                case _:
                    raise ValidationError(f"Invalid tool choice: {tool_choice}")
        if isinstance(tool_choice, (dict, Mapping)):
            return ChatToolMode.model_validate(tool_choice)
        return tool_choice

    def to_provider_settings(self, by_alias: bool = True, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert the ChatOptions to a dictionary suitable for provider requests.

        Args:
            by_alias: Use alias names for fields if True.
            exclude: Additional keys to exclude from the output.

        Returns:
            Dictionary of settings for provider.
        """
        default_exclude = {"additional_properties"}
        # No tool choice if no tools are defined
        if self.tools is None or len(self.tools) == 0:
            default_exclude.add("tool_choice")
        merged_exclude = default_exclude if exclude is None else default_exclude | set(exclude)

        settings = self.model_dump(exclude_none=True, by_alias=by_alias, exclude=merged_exclude)
        settings = {k: v for k, v in settings.items() if v}
        settings.update(self.additional_properties)
        for key in merged_exclude:
            settings.pop(key, None)
        return settings

    def __and__(self, other: object) -> Self:
        """Combines two ChatOptions instances.

        The values from the other ChatOptions take precedence.
        List and dicts are combined.
        """
        if not isinstance(other, ChatOptions):
            return self
        ai_tools = other._ai_tools
        updated_values = other.model_dump(exclude_none=True)
        updated_values.pop("tools", [])
        logit_bias = updated_values.pop("logit_bias", {})
        metadata = updated_values.pop("metadata", {})
        additional_properties = updated_values.pop("additional_properties", {})
        combined = self.model_copy(update=updated_values)
        if ai_tools:
            if not combined._ai_tools:
                combined._ai_tools = []
            for tool in ai_tools:
                if tool not in combined._ai_tools:
                    combined._ai_tools.append(tool)
        combined.logit_bias = {**(combined.logit_bias or {}), **logit_bias}
        combined.metadata = {**(combined.metadata or {}), **metadata}
        combined.additional_properties = {**(combined.additional_properties or {}), **additional_properties}
        return combined


# region: GeneratedEmbeddings


class GeneratedEmbeddings(AFBaseModel, MutableSequence[TEmbedding], Generic[TEmbedding]):
    """A model representing generated embeddings."""

    embeddings: list[TEmbedding] = Field(default_factory=list, kw_only=False)  # type: ignore[ReportUnknownVariableType]
    usage: UsageDetails | None = None
    additional_properties: dict[str, Any] = Field(default_factory=dict)

    def __contains__(self, value: object) -> bool:
        return value in self.embeddings

    def __iter__(self) -> Iterator[TEmbedding]:  # type: ignore[override] # overrides a method in BaseModel, ignoring
        return iter(self.embeddings)

    def __len__(self) -> int:
        return len(self.embeddings)

    def __reversed__(self) -> Iterator[TEmbedding]:
        return self.embeddings.__reversed__()

    def index(self, value: TEmbedding, start: int = 0, stop: int | None = None) -> int:
        if start > 0:
            if stop is not None:
                return self.embeddings.index(value, start, stop)
            return self.embeddings.index(value, start)
        return self.embeddings.index(value)

    def count(self, value: TEmbedding) -> int:
        return self.embeddings.count(value)

    @overload
    def __getitem__(self, index: int) -> TEmbedding: ...

    @overload
    def __getitem__(self, index: slice) -> MutableSequence[TEmbedding]: ...

    def __getitem__(self, index: int | slice) -> TEmbedding | MutableSequence[TEmbedding]:
        return self.embeddings[index]

    @overload
    def __setitem__(self, index: int, value: TEmbedding) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[TEmbedding]) -> None: ...

    def __setitem__(self, index: int | slice, value: TEmbedding | Iterable[TEmbedding]) -> None:
        if isinstance(index, int):
            if isinstance(value, Iterable):
                raise TypeError("Value must be an iterable when setting a slice.")
            self.embeddings[index] = value
            return
        if not isinstance(value, Iterable):
            raise TypeError("Value must be an iterable when setting a slice.")
        self.embeddings[index] = value

    @overload
    def __delitem__(self, index: int) -> None: ...

    @overload
    def __delitem__(self, index: slice) -> None: ...

    def __delitem__(self, index: int | slice) -> None:
        del self.embeddings[index]

    def insert(self, index: int, value: TEmbedding) -> None:
        self.embeddings.insert(index, value)

    def append(self, value: TEmbedding) -> None:
        self.embeddings.append(value)

    def clear(self) -> None:
        self.embeddings.clear()
        self.usage = None
        self.additional_properties = {}

    def reverse(self) -> None:
        self.embeddings.reverse()

    def extend(self, values: Iterable[TEmbedding]) -> None:
        self.embeddings.extend(values)

    def pop(self, index: int = -1) -> TEmbedding:
        return self.embeddings.pop(index)

    def remove(self, value: TEmbedding) -> None:
        self.embeddings.remove(value)

    def __iadd__(self, values: Iterable[TEmbedding] | Self) -> Self:
        if isinstance(values, GeneratedEmbeddings):
            self.embeddings += values.embeddings
            if not self.usage:
                self.usage = values.usage
            else:
                self.usage += values.usage
            self.additional_properties.update(values.additional_properties)
        else:
            self.embeddings += values
        return self


# region AgentRunResponse


class AgentRunResponse(AFBaseModel):
    """Represents the response to an Agent run request.

    Provides one or more response messages and metadata about the response.
    A typical response will contain a single message, but may contain multiple
    messages in scenarios involving function calls, RAG retrievals, or complex logic.
    """

    messages: list[ChatMessage] = Field(default_factory=list[ChatMessage])
    response_id: str | None = None
    created_at: CreatedAtT | None = None  # use a datetimeoffset type?
    usage_details: UsageDetails | None = None
    raw_representation: Any | None = None
    additional_properties: dict[str, Any] | None = None

    def __init__(
        self,
        messages: ChatMessage | list[ChatMessage] | None = None,
        response_id: str | None = None,
        created_at: CreatedAtT | None = None,
        usage_details: UsageDetails | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an AgentRunResponse.

        Attributes:
        messages: The list of chat messages in the response.
        response_id: The ID of the chat response.
        created_at: A timestamp for the chat response.
        usage_details: The usage details for the chat response.
        additional_properties: Any additional properties associated with the chat response.
        raw_representation: The raw representation of the chat response from an underlying implementation.
        **kwargs: Additional properties to set on the response.
        """
        processed_messages: list[ChatMessage] = []
        if messages is not None:
            if isinstance(messages, ChatMessage):
                processed_messages.append(messages)
            elif isinstance(messages, list):
                processed_messages.extend(messages)

        super().__init__(
            messages=processed_messages,  # type: ignore[reportCallIssue]
            response_id=response_id,  # type: ignore[reportCallIssue]
            created_at=created_at,  # type: ignore[reportCallIssue]
            usage_details=usage_details,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,  # type: ignore[reportCallIssue]
            **kwargs,
        )

    @property
    def text(self) -> str:
        """Get the concatenated text of all messages."""
        return "".join(msg.text for msg in self.messages) if self.messages else ""

    @classmethod
    def from_agent_run_response_updates(
        cls: type[TAgentRunResponse], updates: Sequence["AgentRunResponseUpdate"]
    ) -> TAgentRunResponse:
        """Joins multiple updates into a single AgentRunResponse."""
        msg = cls(messages=[])
        for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        return msg

    @classmethod
    async def from_agent_response_generator(
        cls: type[TAgentRunResponse], updates: AsyncIterable["AgentRunResponseUpdate"]
    ) -> TAgentRunResponse:
        """Joins multiple updates into a single AgentRunResponse."""
        msg = cls(messages=[])
        async for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        return msg

    def __str__(self) -> str:
        return self.text


# region AgentRunResponseUpdate


class AgentRunResponseUpdate(AFBaseModel):
    """Represents a single streaming response chunk from an Agent."""

    contents: list[AIContents] = Field(default_factory=list[AIContents])
    role: ChatRole | None = None
    author_name: str | None = None
    response_id: str | None = None
    message_id: str | None = None
    created_at: CreatedAtT | None = None  # use a datetimeoffset type?
    additional_properties: dict[str, Any] | None = None
    raw_representation: Any | None = None

    @property
    def text(self) -> str:
        """Get the concatenated text of all TextContent objects in contents."""
        return (
            "".join(content.text for content in self.contents if isinstance(content, TextContent))
            if self.contents
            else ""
        )

    def __str__(self) -> str:
        return self.text


# region: SpeechToTextOptions


class SpeechToTextOptions(AFBaseModel):
    """Common request settings for Speech to Text AI services."""

    ai_model_id: Annotated[str | None, Field(serialization_alias="model")] = None
    speech_language: Annotated[str | None, Field(description="Language of the input speech.")] = None
    text_language: Annotated[str | None, Field(description="Language of the output text.")] = None
    speech_sample_rate: Annotated[int | None, Field(description="Sample rate of the input speech.")] = None
    additional_properties: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific additional properties."
    )

    def to_provider_settings(self, by_alias: bool = True, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert the SpeechToTextOptions to a dictionary suitable for provider requests.

        Args:
            by_alias: Use alias names for fields if True.
            exclude: Additional keys to exclude from the output.

        Returns:
            Dictionary of settings for provider.
        """
        default_exclude = {"additional_properties"}
        merged_exclude = default_exclude if exclude is None else default_exclude | set(exclude)

        settings: dict[str, Any] = self.model_dump(exclude_none=True, by_alias=by_alias, exclude=merged_exclude)
        settings = {k: v for k, v in settings.items() if not (isinstance(v, dict) and not v)}
        settings.update(self.additional_properties)
        for key in merged_exclude:
            settings.pop(key, None)
        return settings


# region: TextToSpeechOptions


class TextToSpeechOptions(AFBaseModel):
    """Request settings for text to speech services.

    Tailor this to be more general as more models (aside from OpenAI) are added.
    """

    ai_model_id: str | None = Field(None, serialization_alias="model")
    voice: Literal["alloy", "ash", "ballad", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"] = "alloy"
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] | None = None
    speed: Annotated[float | None, Field(ge=0.25, le=4.0)] = None
    additional_properties: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific additional properties."
    )

    def to_provider_settings(self, by_alias: bool = True, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert the SpeechToTextOptions to a dictionary suitable for provider requests.

        Args:
            by_alias: Use alias names for fields if True.
            exclude: Additional keys to exclude from the output.

        Returns:
            Dictionary of settings for provider.
        """
        default_exclude = {"additional_properties"}
        merged_exclude = default_exclude if exclude is None else default_exclude | set(exclude)

        settings: dict[str, Any] = self.model_dump(exclude_none=True, by_alias=by_alias, exclude=merged_exclude)
        settings = {k: v for k, v in settings.items() if not (isinstance(v, dict) and not v)}
        settings.update(self.additional_properties)
        for key in merged_exclude:
            settings.pop(key, None)
        return settings


# endregion


# endregion
