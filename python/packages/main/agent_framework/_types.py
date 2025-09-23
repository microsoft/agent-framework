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
from copy import deepcopy
from typing import Annotated, Any, ClassVar, Generic, Literal, TypeVar, overload

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_serializer,
)

from ._logging import get_logger
from ._pydantic import AFBaseModel
from ._tools import ToolProtocol, ai_function
from .exceptions import AdditionItemMismatch

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

logger = get_logger("agent_framework")

# region Constants and types
_T = TypeVar("_T")
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
    "audio/mp3",
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
    "AgentRunResponse",
    "AgentRunResponseUpdate",
    "AnnotatedRegions",
    "Annotations",
    "BaseAnnotation",
    "BaseContent",
    "ChatMessage",
    "ChatOptions",
    "ChatResponse",
    "ChatResponseUpdate",
    "ChatToolMode",
    "CitationAnnotation",
    "Contents",
    "DataContent",
    "ErrorContent",
    "FinishReason",
    "FunctionApprovalRequestContent",
    "FunctionApprovalResponseContent",
    "FunctionCallContent",
    "FunctionResultContent",
    "GeneratedEmbeddings",
    "HostedFileContent",
    "HostedVectorStoreContent",
    "Role",
    "SpeechToTextOptions",
    "TextContent",
    "TextReasoningContent",
    "TextSpanRegion",
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

    def __str__(self) -> str:
        """Returns a string representation of the usage details."""
        return self.model_dump_json(indent=4, exclude_none=True)

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

    def __setitem__(self, key: str, value: int) -> None:
        """Sets an additional count for the usage details."""
        if not isinstance(value, int):
            raise ValueError("Additional counts must be integers.")
        if self.model_extra is None:
            self.model_extra = {}  # type: ignore[reportAttributeAccessIssue, misc]
        self.model_extra[key] = value

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
    if (
        not response.messages
        or (
            update.message_id
            and response.messages[-1].message_id
            and response.messages[-1].message_id != update.message_id
        )
        or (update.role and response.messages[-1].role != update.role)
    ):
        is_new_message = True

    if is_new_message:
        message = ChatMessage(role=Role.ASSISTANT, contents=[])
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
            except AdditionItemMismatch:
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
    if response.raw_representation is None:
        response.raw_representation = []
    if not isinstance(response.raw_representation, list):
        response.raw_representation = [response.raw_representation]
    response.raw_representation.append(update.raw_representation)
    if isinstance(response, ChatResponse) and isinstance(update, ChatResponseUpdate):
        if update.conversation_id is not None:
            response.conversation_id = update.conversation_id
        if update.finish_reason is not None:
            response.finish_reason = update.finish_reason
        if update.ai_model_id is not None:
            response.ai_model_id = update.ai_model_id


def _coalesce_text_content(
    contents: list["Contents"], type_: type["TextContent"] | type["TextReasoningContent"]
) -> None:
    """Take any subsequence Text or TextReasoningContent items and coalesce them into a single item."""
    if not contents:
        return
    coalesced_contents: list["Contents"] = []
    first_new_content: Any | None = None
    for content in contents:
        if isinstance(content, type_):
            if first_new_content is None:
                first_new_content = deepcopy(content)
            else:
                first_new_content += content
        else:
            # skip this content, it is not of the right type
            # so write the existing one to the list and start a new one,
            # once the right type is found again
            if first_new_content:
                coalesced_contents.append(first_new_content)
            first_new_content = None
            # but keep the other content in the new list
            coalesced_contents.append(content)
    if first_new_content:
        coalesced_contents.append(first_new_content)
    contents.clear()
    contents.extend(coalesced_contents)


def _finalize_response(response: "ChatResponse | AgentRunResponse") -> None:
    """Finalizes the response by performing any necessary post-processing."""
    for msg in response.messages:
        _coalesce_text_content(msg.contents, TextContent)
        _coalesce_text_content(msg.contents, TextReasoningContent)


# region BaseAnnotation


class TextSpanRegion(AFBaseModel):
    """Represents a region of text that has been annotated."""

    type: Literal["text_span"] = "text_span"  # type: ignore[assignment]
    start_index: int | None = None
    end_index: int | None = None


AnnotatedRegions = Annotated[
    TextSpanRegion,
    Field(discriminator="type"),
]


class BaseAnnotation(AFBaseModel):
    """Base class for all AI Annotation types.

    Args:
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content from an underlying implementation.

    """

    annotated_regions: list[AnnotatedRegions] | None = None
    additional_properties: dict[str, Any] | None = None
    raw_representation: Any | None = Field(default=None, repr=False, exclude=True)


class CitationAnnotation(BaseAnnotation):
    """Represents a citation annotation.

    Attributes:
        type: The type of content, which is always "citation" for this class.
        title: The title of the cited content.
        url: The URL of the cited content.
        file_id: The file identifier of the cited content, if applicable.
        tool_name: The name of the tool that generated the citation, if applicable.
        snippet: A snippet of the cited content, if applicable.
        annotated_regions: A list of regions that have been annotated with this citation.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content from an underlying implementation.
    """

    type: Literal["citation"] = "citation"  # type: ignore[assignment]
    title: str | None = None
    url: str | None = None
    file_id: str | None = None
    tool_name: str | None = None
    snippet: str | None = None


Annotations = Annotated[
    CitationAnnotation,
    Field(discriminator="type"),
]


# region BaseContent


class BaseContent(AFBaseModel):
    """Represents content used by AI services.

    Attributes:
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content from an underlying implementation.

    """

    annotations: list[Annotations] | None = None
    additional_properties: dict[str, Any] | None = None
    raw_representation: Any | None = Field(default=None, repr=False, exclude=True)


class TextContent(BaseContent):
    """Represents text content in a chat.

    Attributes:
        text: The text content represented by this instance.
        type: The type of content, which is always "text" for this class.
        annotations: Optional annotations associated with the content.
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

    def __add__(self, other: "TextContent") -> "TextContent":
        """Concatenate two TextContent instances.

        The following things happen:
        The text is concatenated.
        The annotations are combined.
        The additional properties are merged, with the values of shared keys of the first instance taking precedence.
        The raw_representations are combined into a list of them, if they both have one.
        """
        if not isinstance(other, TextContent):
            raise TypeError("Incompatible type")
        if self.raw_representation is None:
            raw_representation = other.raw_representation
        elif other.raw_representation is None:
            raw_representation = self.raw_representation
        else:
            raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])
        if self.annotations is None:
            annotations = other.annotations
        elif other.annotations is None:
            annotations = self.annotations
        else:
            annotations = self.annotations + other.annotations
        return TextContent(
            text=self.text + other.text,
            annotations=annotations,
            additional_properties={
                **(other.additional_properties or {}),
                **(self.additional_properties or {}),
            },
            raw_representation=raw_representation,
        )

    def __iadd__(self, other: "TextContent") -> Self:
        """In-place concatenation of two TextContent instances.

        The following things happen:
        The text is concatenated.
        The annotations are combined.
        The additional properties are merged, with the values of shared keys of the first instance taking precedence.
        The raw_representations are combined into a list of them, if they both have one.
        """
        if not isinstance(other, TextContent):
            raise TypeError("Incompatible type")
        self.text += other.text
        if self.additional_properties is None:
            self.additional_properties = {}
        if other.additional_properties:
            self.additional_properties = {**other.additional_properties, **self.additional_properties}
        if self.raw_representation is None:
            self.raw_representation = other.raw_representation
        elif other.raw_representation is not None:
            self.raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])
        if other.annotations:
            if self.annotations is None:
                self.annotations = []
            self.annotations.extend(other.annotations)
        return self


class TextReasoningContent(BaseContent):
    """Represents text reasoning content in a chat.

    Remarks:
        This class and `TextContent` are superficially similar, but distinct.

    Attributes:
        text: The text content represented by this instance.
        type: The type of content, which is always "text_reasoning" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.
    """

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

    def __add__(self, other: "TextReasoningContent") -> "TextReasoningContent":
        """Concatenate two TextReasoningContent instances.

        The following things happen:
        The text is concatenated.
        The annotations are combined.
        The additional properties are merged, with the values of shared keys of the first instance taking precedence.
        The raw_representations are combined into a list of them, if they both have one.
        """
        if not isinstance(other, TextReasoningContent):
            raise TypeError("Incompatible type")
        if self.raw_representation is None:
            raw_representation = other.raw_representation
        elif other.raw_representation is None:
            raw_representation = self.raw_representation
        else:
            raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])
        if self.annotations is None:
            annotations = other.annotations
        elif other.annotations is None:
            annotations = self.annotations
        else:
            annotations = self.annotations + other.annotations
        return TextReasoningContent(
            text=self.text + other.text,
            annotations=annotations,
            additional_properties={**(self.additional_properties or {}), **(other.additional_properties or {})},
            raw_representation=raw_representation,
        )

    def __iadd__(self, other: "TextReasoningContent") -> Self:
        """In-place concatenation of two TextReasoningContent instances.

        The following things happen:
        The text is concatenated.
        The annotations are combined.
        The additional properties are merged, with the values of shared keys of the first instance taking precedence.
        The raw_representations are combined into a list of them, if they both have one.
        """
        if not isinstance(other, TextReasoningContent):
            raise TypeError("Incompatible type")
        self.text += other.text
        if self.additional_properties is None:
            self.additional_properties = {}
        if other.additional_properties:
            self.additional_properties.update(other.additional_properties)
        if self.raw_representation is None:
            self.raw_representation = other.raw_representation
        elif other.raw_representation is not None:
            self.raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])
        if other.annotations:
            if self.annotations is None:
                self.annotations = []
            self.annotations.extend(other.annotations)
        return self


class DataContent(BaseContent):
    """Represents binary data content with an associated media type (also known as a MIME type).

    Attributes:
        uri: The URI of the data represented by this instance, typically in the form of a data URI.
            Should be in the form: "data:{media_type};base64,{base64_data}".
        media_type: The media type of the data.
        type: The type of content, which is always "data" for this class.
        annotations: Optional annotations associated with the content.
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
        annotations: list[Annotations] | None = None,
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
            annotations: Optional annotations associated with the content.
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
        annotations: list[Annotations] | None = None,
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
            annotations: Optional annotations associated with the content.
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
        annotations: list[Annotations] | None = None,
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
            annotations: Optional annotations associated with the content.
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
            annotations=annotations,
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

    def has_top_level_media_type(self, top_level_media_type: Literal["application", "audio", "image", "text"]) -> bool:
        return _has_top_level_media_type(self.media_type, top_level_media_type)


class UriContent(BaseContent):
    """Represents a URI content.

    Remarks:
        This is used for content that is identified by a URI, such as an image or a file.
        For (binary) data URIs, use `DataContent` instead.

    Attributes:
        uri: The URI of the content, e.g., 'https://example.com/image.png'.
        media_type: The media type of the content, e.g., 'image/png', 'application/json', etc.
        type: The type of content, which is always "uri" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["uri"] = "uri"  # type: ignore[assignment]
    uri: str
    media_type: str

    def __init__(
        self,
        uri: str,
        media_type: str,
        *,
        annotations: list[Annotations] | None = None,
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
            annotations: Optional annotations associated with the content.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            uri=uri,  # type: ignore[reportCallIssue]
            media_type=media_type,  # type: ignore[reportCallIssue]
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )

    def has_top_level_media_type(self, top_level_media_type: Literal["application", "audio", "image", "text"]) -> bool:
        return _has_top_level_media_type(self.media_type, top_level_media_type)


def _has_top_level_media_type(
    media_type: str | None, top_level_media_type: Literal["application", "audio", "image", "text"]
) -> bool:
    if media_type is None:
        return False

    slash_index = media_type.find("/")
    span = media_type[:slash_index] if slash_index >= 0 else media_type
    span = span.strip()
    return span.lower() == top_level_media_type.lower()


class ErrorContent(BaseContent):
    """Represents an error.

    Remarks:
        Typically used for non-fatal errors, where something went wrong as part of the operation,
        but the operation was still able to continue.

    Attributes:
        error_code: The error code associated with the error.
        details: Additional details about the error.
        message: The error message.
        type: The type of content, which is always "error" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.


    """

    type: Literal["error"] = "error"  # type: ignore[assignment]
    error_code: str | None = None
    details: str | None = None
    message: str | None

    def __init__(
        self,
        *,
        message: str | None = None,
        error_code: str | None = None,
        details: str | None = None,
        annotations: list[Annotations] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes an ErrorContent instance.

        Args:
            message: The error message.
            error_code: The error code associated with the error.
            details: Additional details about the error.
            annotations: Optional annotations associated with the content.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            message=message,  # type: ignore[reportCallIssue]
            error_code=error_code,  # type: ignore[reportCallIssue]
            details=details,  # type: ignore[reportCallIssue]
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )

    def __str__(self) -> str:
        """Returns a string representation of the error."""
        return f"Error {self.error_code}: {self.message}" if self.error_code else self.message or "Unknown error"


class FunctionCallContent(BaseContent):
    """Represents a function call request.

    Attributes:
        call_id: The function call identifier.
        name: The name of the function requested.
        arguments: The arguments requested to be provided to the function.
        exception: Any exception that occurred while mapping the original function call data to this representation.
        type: The type of content, which is always "function_call" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["function_call"] = "function_call"  # type: ignore[assignment]
    call_id: str
    name: str
    arguments: str | dict[str, Any | None] | None = None
    exception: Exception | None = None

    def __init__(
        self,
        *,
        call_id: str,
        name: str,
        arguments: str | dict[str, Any | None] | None = None,
        exception: Exception | None = None,
        annotations: list[Annotations] | None = None,
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
            annotations: Optional annotations associated with the content.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            call_id=call_id,  # type: ignore[reportCallIssue]
            name=name,  # type: ignore[reportCallIssue]
            arguments=arguments,  # type: ignore[reportCallIssue]
            exception=exception,  # type: ignore[reportCallIssue]
            annotations=annotations,
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
            raise AdditionItemMismatch("", log_level=None)
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


class FunctionResultContent(BaseContent):
    """Represents the result of a function call.

    Attributes:
        call_id: The identifier of the function call for which this is the result.
        result: The result of the function call, or a generic error message if the function call failed.
        exception: An exception that occurred if the function call failed.
        type: The type of content, which is always "function_result" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["function_result"] = "function_result"  # type: ignore[assignment]
    call_id: str
    result: Any | None = None
    exception: Exception | None = None

    def __init__(
        self,
        *,
        call_id: str,
        result: Any | None = None,
        exception: Exception | None = None,
        annotations: list[Annotations] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionResultContent instance.

        Args:
            call_id: The identifier of the function call for which this is the result.
            result: The result of the function call, or a generic error message if the function call failed.
            exception: An exception that occurred if the function call failed.
            annotations: Optional annotations associated with the content.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            call_id=call_id,  # type: ignore[reportCallIssue]
            result=result,  # type: ignore[reportCallIssue]
            exception=exception,  # type: ignore[reportCallIssue]
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )


class UsageContent(BaseContent):
    """Represents usage information associated with a chat request and response.

    Attributes:
        details: The usage information, including input and output token counts, and any additional counts.
        type: The type of content, which is always "usage" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["usage"] = "usage"  # type: ignore[assignment]
    details: UsageDetails

    def __init__(
        self,
        details: UsageDetails,
        *,
        annotations: list[Annotations] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a UsageContent instance."""
        super().__init__(
            details=details,  # type: ignore[reportCallIssue]
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )


class HostedFileContent(BaseContent):
    """Represents a hosted file content.

    Attributes:
        file_id: The identifier of the hosted file.
        type: The type of content, which is always "hosted_file" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["hosted_file"] = "hosted_file"  # type: ignore[assignment]
    file_id: str

    def __init__(
        self,
        file_id: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a HostedFileContent instance."""
        super().__init__(
            file_id=file_id,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )


class HostedVectorStoreContent(BaseContent):
    """Represents a hosted vector store content.

    Attributes:
        vector_store_id: The identifier of the hosted vector store.
        type: The type of content, which is always "hosted_vector_store" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    type: Literal["hosted_vector_store"] = "hosted_vector_store"  # type: ignore[assignment]
    vector_store_id: str

    def __init__(
        self,
        vector_store_id: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a HostedVectorStoreContent instance."""
        super().__init__(
            vector_store_id=vector_store_id,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )


class BaseUserInputRequest(BaseContent):
    """Base class for all user requests."""

    type: Literal["user_input_request"] = "user_input_request"  # type: ignore[assignment]
    id: Annotated[str, Field(..., min_length=1)]


class BaseUserInputResponse(BaseContent):
    """Base class for all user responses."""

    type: Literal["user_input_response"] = "user_input_response"  # type: ignore[assignment]
    id: Annotated[str, Field(..., min_length=1)]


class FunctionApprovalResponseContent(BaseUserInputResponse):
    """Represents a response for user approval of a function call."""

    type: Literal["function_approval_response"] = "function_approval_response"  # type: ignore[assignment]
    approved: bool
    function_call: FunctionCallContent

    def __init__(
        self,
        approved: bool,
        *,
        id: str,
        function_call: FunctionCallContent,
        annotations: list[Annotations] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionApprovalResponseContent instance.

        Args:
            approved: Whether the function call was approved.
            id: The unique identifier for the request.
            function_call: The function call content to be approved.
            annotations: Optional list of annotations for the request.
            additional_properties: Optional additional properties for the request.
            raw_representation: Optional raw representation of the request.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            approved=approved,  # type: ignore[reportCallIssue]
            id=id,  # type: ignore[reportCallIssue]
            function_call=function_call,  # type: ignore[reportCallIssue]
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )


class FunctionApprovalRequestContent(BaseUserInputRequest):
    """Represents a request for user approval of a function call."""

    type: Literal["function_approval_request"] = "function_approval_request"  # type: ignore[assignment]
    function_call: FunctionCallContent

    def __init__(
        self,
        *,
        id: str,
        function_call: FunctionCallContent,
        annotations: list[Annotations] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionApprovalRequestContent instance.

        Args:
            id: The unique identifier for the request.
            function_call: The function call content to be approved.
            annotations: Optional list of annotations for the request.
            additional_properties: Optional additional properties for the request.
            raw_representation: Optional raw representation of the request.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            id=id,  # type: ignore[reportCallIssue]
            function_call=function_call,  # type: ignore[reportCallIssue]
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )

    def create_response(self, approved: bool) -> "FunctionApprovalResponseContent":
        """Create a response for the function approval request."""
        return FunctionApprovalResponseContent(
            approved,
            id=self.id,
            function_call=self.function_call,
            additional_properties=self.additional_properties,
        )


UserInputRequestContents = Annotated[
    FunctionApprovalRequestContent,
    Field(discriminator="type"),
]

Contents = Annotated[
    TextContent
    | DataContent
    | TextReasoningContent
    | UriContent
    | FunctionCallContent
    | FunctionResultContent
    | ErrorContent
    | UsageContent
    | HostedFileContent
    | HostedVectorStoreContent
    | FunctionApprovalRequestContent
    | FunctionApprovalResponseContent,
    Field(discriminator="type"),
]

# region Chat Response constants


class Role(AFBaseModel):
    """Describes the intended purpose of a message within a chat interaction.

    Attributes:
        value: The string representation of the role.

    Properties:
        SYSTEM: The role that instructs or sets the behaviour of the AI system.
        USER: The role that provides user input for chat interactions.
        ASSISTANT: The role that provides responses to system-instructed, user-prompted input.
        TOOL: The role that provides additional information and references in response to tool use requests.
    """

    value: str = Field(..., kw_only=False)

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
        return f"Role(value={self.value!r})"


# Note: ClassVar is used to indicate that these are class-level constants, not instance attributes.
# The type: ignore[assignment] is used to suppress the type checker warning about assigning to a ClassVar,
# it gets assigned immediately after the class definition.
Role.SYSTEM = Role(value="system")  # type: ignore[assignment]
Role.USER = Role(value="user")  # type: ignore[assignment]
Role.ASSISTANT = Role(value="assistant")  # type: ignore[assignment]
Role.TOOL = Role(value="tool")  # type: ignore[assignment]


class FinishReason(AFBaseModel):
    """Represents the reason a chat response completed.

    Attributes:
        value: The string representation of the finish reason.
    """

    value: str

    CONTENT_FILTER: ClassVar[Self]  # type: ignore[assignment]
    """A FinishReason representing the model filtering content, whether for safety, prohibited content,
    sensitive content, or other such issues."""
    LENGTH: ClassVar[Self]  # type: ignore[assignment]
    """A FinishReason representing the model reaching the maximum length allowed for the request and/or
    response (typically in terms of tokens)."""
    STOP: ClassVar[Self]  # type: ignore[assignment]
    """A FinishReason representing the model encountering a natural stop point or provided stop sequence."""
    TOOL_CALLS: ClassVar[Self]  # type: ignore[assignment]
    """A FinishReason representing the model requesting the use of a tool that was defined in the request."""


FinishReason.CONTENT_FILTER = FinishReason(value="content_filter")  # type: ignore[assignment]
FinishReason.LENGTH = FinishReason(value="length")  # type: ignore[assignment]
FinishReason.STOP = FinishReason(value="stop")  # type: ignore[assignment]
FinishReason.TOOL_CALLS = FinishReason(value="tool_calls")  # type: ignore[assignment]

# region ChatMessage


class ChatMessage(AFBaseModel):
    """Represents a chat message.

    Attributes:
        role: The role of the author of the message.
        contents: The chat message content items.
        author_name: The name of the author of the message.
        message_id: The ID of the chat message.
        additional_properties: Any additional properties associated with the chat message.
        raw_representation: The raw representation of the chat message from an underlying implementation.

    """

    role: Role
    """The role of the author of the message."""
    contents: list[Contents]
    """The chat message content items."""
    author_name: str | None
    """The name of the author of the message."""
    message_id: str | None
    """The ID of the chat message."""
    additional_properties: dict[str, Any] | None = None
    """Any additional properties associated with the chat message."""
    raw_representation: Any | None = Field(default=None, exclude=True)
    """The raw representation of the chat message from an underlying implementation."""

    @overload
    def __init__(
        self,
        role: Role | Literal["system", "user", "assistant", "tool"],
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
        role: Role | Literal["system", "user", "assistant", "tool"],
        *,
        contents: MutableSequence[Contents],
        author_name: str | None = None,
        message_id: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatMessage with a role and optional contents.

        Args:
            role: The role of the author of the message.
            contents: Optional list of BaseContent items to include in the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
            raw_representation: Optional raw representation of the chat message.
        """

    def __init__(
        self,
        role: Role | Literal["system", "user", "assistant", "tool"],
        *,
        text: str | None = None,
        contents: MutableSequence[Contents] | None = None,
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
            role = Role(value=role)
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


# region ChatResponse


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
        structured_output: The structured output of the chat response, if applicable.
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
    finish_reason: FinishReason | None = None
    """The reason for the chat response."""
    usage_details: UsageDetails | None = None
    """The usage details for the chat response."""
    value: Any | None = None
    """The structured output of the chat response, if applicable."""
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
        finish_reason: FinishReason | None = None,
        usage_details: UsageDetails | None = None,
        value: Any | None = None,
        response_format: type[BaseModel] | None = None,
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
            value: Optional value of the structured output.
            response_format: Optional response format for the chat response.
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
        finish_reason: FinishReason | None = None,
        usage_details: UsageDetails | None = None,
        value: Any | None = None,
        response_format: type[BaseModel] | None = None,
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
            value: Optional value of the structured output.
            response_format: Optional response format for the chat response.
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
        finish_reason: FinishReason | None = None,
        usage_details: UsageDetails | None = None,
        value: Any | None = None,
        response_format: type[BaseModel] | None = None,
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
            messages.append(ChatMessage(role=Role.ASSISTANT, contents=[text]))

        super().__init__(
            messages=messages,  # type: ignore[reportCallIssue]
            response_id=response_id,  # type: ignore[reportCallIssue]
            conversation_id=conversation_id,  # type: ignore[reportCallIssue]
            ai_model_id=model_id,  # type: ignore[reportCallIssue]
            created_at=created_at,  # type: ignore[reportCallIssue]
            finish_reason=finish_reason,  # type: ignore[reportCallIssue]
            usage_details=usage_details,  # type: ignore[reportCallIssue]
            value=value,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,  # type: ignore[reportCallIssue]
            **kwargs,
        )
        if response_format:
            self.try_parse_value(output_format_type=response_format)

    @classmethod
    def from_chat_response_updates(
        cls: type[TChatResponse],
        updates: Sequence["ChatResponseUpdate"],
        *,
        output_format_type: type[BaseModel] | None = None,
    ) -> TChatResponse:
        """Joins multiple updates into a single ChatResponse."""
        msg = cls(messages=[])
        for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        if output_format_type:
            msg.try_parse_value(output_format_type)
        return msg

    @classmethod
    async def from_chat_response_generator(
        cls: type[TChatResponse],
        updates: AsyncIterable["ChatResponseUpdate"],
        *,
        output_format_type: type[BaseModel] | None = None,
    ) -> TChatResponse:
        """Joins multiple updates into a single ChatResponse."""
        msg = cls(messages=[])
        async for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        if output_format_type:
            msg.try_parse_value(output_format_type)
        return msg

    @property
    def text(self) -> str:
        """Returns the concatenated text of all messages in the response."""
        return ("\n".join(message.text for message in self.messages if isinstance(message, ChatMessage))).strip()

    def __str__(self) -> str:
        return self.text

    def try_parse_value(self, output_format_type: type[BaseModel]) -> None:
        """If there is a value, does nothing, otherwise tries to parse the text into the value."""
        if self.value is None:
            try:
                self.value = output_format_type.model_validate_json(self.text)  # type: ignore[reportUnknownMemberType]
            except ValidationError as ex:
                logger.debug("Failed to parse value from chat response text: %s", ex)


# region ChatResponseUpdate


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

    contents: list[Contents]
    """The chat response update content items."""

    role: Role | None = None
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
    finish_reason: FinishReason | None = None
    """The finish reason for the operation."""

    additional_properties: dict[str, Any] | None = None
    """Any additional properties associated with the chat response update."""
    raw_representation: Any | None = None
    """The raw representation of the chat response update from an underlying implementation."""

    @overload
    def __init__(
        self,
        *,
        contents: list[Contents],
        role: Role | Literal["system", "user", "assistant", "tool"] | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        conversation_id: str | None = None,
        ai_model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: FinishReason | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""

    @overload
    def __init__(
        self,
        *,
        text: TextContent | str,
        role: Role | Literal["system", "user", "assistant", "tool"] | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        conversation_id: str | None = None,
        ai_model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: FinishReason | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters."""

    def __init__(
        self,
        *,
        contents: list[Contents] | None = None,
        text: TextContent | str | None = None,
        role: Role | Literal["system", "user", "assistant", "tool"] | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        conversation_id: str | None = None,
        ai_model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: FinishReason | None = None,
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
            role = Role(value=role)
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

    def with_(self, contents: list[BaseContent] | None = None, message_id: str | None = None) -> Self:
        """Returns a new instance with the specified contents and message_id."""
        if contents is None:
            contents = []

        return self.model_copy(
            update={
                "contents": self.contents + contents,
                "message_id": message_id or self.message_id,
            }
        )


# region ChatOptions


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
    tools: list[ToolProtocol | MutableMapping[str, Any]] | None = None
    top_p: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    user: str | None = None

    @field_validator("tools", mode="before")
    @classmethod
    def _validate_tools(
        cls,
        tools: (
            ToolProtocol
            | Callable[..., Any]
            | MutableMapping[str, Any]
            | list[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
            | None
        ),
    ) -> list[ToolProtocol | MutableMapping[str, Any]] | None:
        """Parse the tools field."""
        if not tools:
            return None
        if not isinstance(tools, list):
            tools = [tools]  # type: ignore[reportAssignmentType, assignment]
        for idx, tool in enumerate(tools):  # type: ignore[reportArgumentType, arg-type]
            if not isinstance(tool, (ToolProtocol, MutableMapping)):
                # Convert to ToolProtocol if it's a function or callable
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
        # No metadata and logit bias if they are empty
        # Prevents 400 error
        if not self.logit_bias:
            default_exclude.add("logit_bias")
        if not self.metadata:
            default_exclude.add("metadata")

        merged_exclude = default_exclude if exclude is None else default_exclude | set(exclude)

        settings = self.model_dump(exclude_none=True, by_alias=by_alias, exclude=merged_exclude)
        settings = {k: v for k, v in settings.items() if v is not None}
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
        other_tools = other.tools
        # tool_choice has a specialized serialize method. Save it here so we can fix it later.
        tool_choice = other.tool_choice or self.tool_choice
        updated_values = other.model_dump(exclude_none=True, exclude={"tools"})
        logit_bias = updated_values.pop("logit_bias", {})
        metadata = updated_values.pop("metadata", {})
        additional_properties = updated_values.pop("additional_properties", {})
        combined = self.model_copy(update=updated_values)
        combined.tool_choice = tool_choice
        combined.logit_bias = {**(combined.logit_bias or {}), **logit_bias}
        combined.metadata = {**(combined.metadata or {}), **metadata}
        combined.additional_properties = {**(combined.additional_properties or {}), **additional_properties}
        if other_tools:
            if not combined.tools:
                combined.tools = other_tools
            else:
                for tool in other_tools:
                    if tool not in combined.tools:
                        combined.tools.append(tool)
        return combined


# region GeneratedEmbeddings


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
    value: Any | None = None
    raw_representation: Any | None = None
    additional_properties: dict[str, Any] | None = None

    def __init__(
        self,
        messages: ChatMessage | list[ChatMessage] | None = None,
        response_id: str | None = None,
        created_at: CreatedAtT | None = None,
        usage_details: UsageDetails | None = None,
        value: Any | None = None,
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
        value: The structured output of the agent run response, if applicable.
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
            value=value,  # type: ignore[reportCallIssue]
            additional_properties=additional_properties,  # type: ignore[reportCallIssue]
            raw_representation=raw_representation,  # type: ignore[reportCallIssue]
            **kwargs,
        )

    @property
    def text(self) -> str:
        """Get the concatenated text of all messages."""
        return "".join(msg.text for msg in self.messages) if self.messages else ""

    @property
    def user_input_requests(self) -> list[UserInputRequestContents]:
        """Get all BaseUserInputRequest messages from the response."""
        return [
            content for msg in self.messages for content in msg.contents if isinstance(content, BaseUserInputRequest)
        ]

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

    contents: list[Contents] = Field(default_factory=list[Contents])
    role: Role | None = None
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

    @property
    def user_input_requests(self) -> list[UserInputRequestContents]:
        """Get all BaseUserInputRequest messages from the response."""
        return [content for content in self.contents if isinstance(content, BaseUserInputRequest)]

    def __str__(self) -> str:
        return self.text


# region SpeechToTextOptions


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


# region TextToSpeechOptions


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
