# Copyright (c) Microsoft. All rights reserved.

import base64
import json
import re
import sys
from collections.abc import (
    AsyncIterable,
    Callable,
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from copy import deepcopy
from typing import Any, ClassVar, Literal, TypeVar, overload

from pydantic import BaseModel, ValidationError

from ._logging import get_logger
from ._serialization import SerializationMixin
from ._tools import ToolProtocol, ai_function
from .exceptions import AdditionItemMismatch

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


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
    "CitationAnnotation",
    "Contents",
    "DataContent",
    "ErrorContent",
    "FinishReason",
    "FunctionApprovalRequestContent",
    "FunctionApprovalResponseContent",
    "FunctionCallContent",
    "FunctionResultContent",
    "HostedFileContent",
    "HostedVectorStoreContent",
    "Role",
    "TextContent",
    "TextReasoningContent",
    "TextSpanRegion",
    "ToolMode",
    "UriContent",
    "UsageContent",
    "UsageDetails",
]

logger = get_logger("agent_framework")


# region Content Parsing Utilities


class EnumLike(type):
    """Generic metaclass for creating enum-like classes with predefined constants.

    This metaclass automatically creates class-level constants based on a _constants
    class attribute. Each constant is defined as a tuple of (name, *args) where
    name is the constant name and args are the constructor arguments.
    """

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any]) -> "EnumLike":
        cls = super().__new__(mcs, name, bases, namespace)

        # Create constants if _constants is defined
        if (const := getattr(cls, "_constants", None)) and isinstance(const, dict):
            for const_name, const_args in const.items():
                if isinstance(const_args, (list, tuple)):
                    setattr(cls, const_name, cls(*const_args))
                else:
                    setattr(cls, const_name, cls(const_args))

        return cls


def _parse_content(content_data: MutableMapping[str, Any]) -> "Contents":
    """Parse a single content data dictionary into the appropriate Content object.

    Args:
        content_data: Content data (dict)

    Returns:
        Content object or raises ValidationError if parsing fails
    """
    content_type = str(content_data.get("type"))
    match content_type:
        case "text":
            return TextContent.from_dict(content_data)
        case "data":
            return DataContent.from_dict(content_data)
        case "uri":
            return UriContent.from_dict(content_data)
        case "error":
            return ErrorContent.from_dict(content_data)
        case "function_call":
            return FunctionCallContent.from_dict(content_data)
        case "function_result":
            return FunctionResultContent.from_dict(content_data)
        case "usage":
            return UsageContent.from_dict(content_data)
        case "hosted_file":
            return HostedFileContent.from_dict(content_data)
        case "hosted_vector_store":
            return HostedVectorStoreContent.from_dict(content_data)
        case "function_approval_request":
            return FunctionApprovalRequestContent.from_dict(content_data)
        case "function_approval_response":
            return FunctionApprovalResponseContent.from_dict(content_data)
        case "text_reasoning":
            return TextReasoningContent.from_dict(content_data)
        case _:
            raise ValidationError([f"Unknown content type '{content_type}'"], model=Contents)  # type: ignore


def _parse_content_list(contents_data: Sequence[Any]) -> list["Contents"]:
    """Parse a list of content data dictionaries into appropriate Content objects.

    Args:
        contents_data: List of content data (dicts or already constructed objects)

    Returns:
        List of Content objects with unknown types logged and ignored
    """
    contents: list["Contents"] = []
    for content_data in contents_data:
        if isinstance(content_data, dict):
            try:
                content = _parse_content(content_data)
                contents.append(content)
            except ValidationError as ve:
                logger.warning(f"Skipping unknown content type or invalid content: {ve}")
        else:
            # If it's already a content object, keep it as is
            contents.append(content_data)

    return contents


# endregion

# region Constants and types
_T = TypeVar("_T")
TEmbedding = TypeVar("TEmbedding")
TChatResponse = TypeVar("TChatResponse", bound="ChatResponse")
TToolMode = TypeVar("TToolMode", bound="ToolMode")
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


class UsageDetails(SerializationMixin):
    """Provides usage details about a request/response.

    Attributes:
        input_token_count: The number of tokens in the input.
        output_token_count: The number of tokens in the output.
        total_token_count: The total number of tokens used to produce the response.
        additional_counts: A dictionary of additional token counts, can be set by passing kwargs.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"_extra_counts"}

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
        self.input_token_count = input_token_count
        self.output_token_count = output_token_count
        self.total_token_count = total_token_count

        # Validate that all kwargs are integers (preserving Pydantic behavior)
        self._extra_counts: dict[str, int] = {}
        for key, value in kwargs.items():
            if not isinstance(value, int):
                raise ValueError(f"Additional counts must be integers, got {type(value).__name__}")
            self._extra_counts[key] = value

    def to_dict(self, *, exclude_none: bool = True, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert the UsageDetails instance to a dictionary.

        Args:
            exclude_none: Whether to exclude None values from the output.
            exclude: Set of field names to exclude from the output.

        Returns:
            Dictionary representation of the UsageDetails instance.
        """
        # Get the base dict from parent class
        result = super().to_dict(exclude_none=exclude_none, exclude=exclude)

        # Add additional counts (extra fields)
        if exclude is None:
            exclude = set()

        for key, value in self._extra_counts.items():
            if key in exclude:
                continue
            if exclude_none and value is None:
                continue
            result[key] = value

        return result

    def __str__(self) -> str:
        """Returns a string representation of the usage details."""
        return self.to_json()

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
        return self._extra_counts

    def __setitem__(self, key: str, value: int) -> None:
        """Sets an additional count for the usage details."""
        if not isinstance(value, int):
            raise ValueError("Additional counts must be integers.")
        self._extra_counts[key] = value

    def __add__(self, other: "UsageDetails | None") -> "UsageDetails":
        """Combines two `UsageDetails` instances."""
        if not other:
            return self
        if not isinstance(other, UsageDetails):
            raise ValueError("Can only add two usage details objects together.")

        additional_counts = self.additional_counts.copy()
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

    def __eq__(self, other: object) -> bool:
        """Check if two UsageDetails instances are equal."""
        if not isinstance(other, UsageDetails):
            return False

        return (
            self.input_token_count == other.input_token_count
            and self.output_token_count == other.output_token_count
            and self.total_token_count == other.total_token_count
            and self.additional_counts == other.additional_counts
        )


# region BaseAnnotation


class TextSpanRegion(SerializationMixin):
    """Represents a region of text that has been annotated."""

    def __init__(
        self,
        *,
        start_index: int | None = None,
        end_index: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize TextSpanRegion.

        Args:
            start_index: The start index of the text span.
            end_index: The end index of the text span.
            **kwargs: Additional keyword arguments.
        """
        self.type: Literal["text_span"] = "text_span"
        self.start_index = start_index
        self.end_index = end_index

        # Handle any additional kwargs
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)


AnnotatedRegions = TextSpanRegion


class BaseAnnotation(SerializationMixin):
    """Base class for all AI Annotation types.

    Args:
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content from an underlying implementation.

    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation", "additional_properties"}

    def __init__(
        self,
        *,
        annotated_regions: list[AnnotatedRegions] | list[MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize BaseAnnotation.

        Args:
            annotated_regions: A list of regions that have been annotated. Can be region objects or dicts.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content from an underlying implementation.
            **kwargs: Additional keyword arguments (merged into additional_properties).
        """
        # Handle annotated_regions conversion from dict format (for SerializationMixin support)
        self.annotated_regions: list[AnnotatedRegions] | None = None
        if annotated_regions is not None:
            converted_regions: list[AnnotatedRegions] = []
            for region_data in annotated_regions:
                if isinstance(region_data, MutableMapping):
                    if region_data.get("type", "") == "text_span":
                        converted_regions.append(TextSpanRegion.from_dict(region_data))
                    else:
                        logger.warning(f"Unknown region type: {region_data.get('type', '')} in {region_data}")
                else:
                    # Already a region object, keep as is
                    converted_regions.append(region_data)
            self.annotated_regions = converted_regions

        # Merge kwargs into additional_properties
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs)

        self.raw_representation = raw_representation

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Convert the instance to a dictionary.

        Extracts additional_properties fields to the root level.

        Args:
            exclude: Set of field names to exclude from serialization.
            exclude_none: Whether to exclude None values from the output. Defaults to True.

        Returns:
            Dictionary representation of the instance.
        """
        # Get the base dict from SerializationMixin
        result = super().to_dict(exclude=exclude, exclude_none=exclude_none)

        # Extract additional_properties to root level
        if self.additional_properties:
            result.update(self.additional_properties)

        return result


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

    def __init__(
        self,
        *,
        title: str | None = None,
        url: str | None = None,
        file_id: str | None = None,
        tool_name: str | None = None,
        snippet: str | None = None,
        annotated_regions: list[AnnotatedRegions] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize CitationAnnotation.

        Args:
            title: The title of the cited content.
            url: The URL of the cited content.
            file_id: The file identifier of the cited content, if applicable.
            tool_name: The name of the tool that generated the citation, if applicable.
            snippet: A snippet of the cited content, if applicable.
            annotated_regions: A list of regions that have been annotated with this citation.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content from an underlying implementation.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            annotated_regions=annotated_regions,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.title = title
        self.url = url
        self.file_id = file_id
        self.tool_name = tool_name
        self.snippet = snippet
        self.type: Literal["citation"] = "citation"


Annotations = CitationAnnotation


# region BaseContent

TContents = TypeVar("TContents", bound="BaseContent")


class BaseContent(SerializationMixin):
    """Represents content used by AI services.

    Attributes:
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content from an underlying implementation.

    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation", "additional_properties"}

    def __init__(
        self,
        *,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize BaseContent.

        Args:
            annotations: Optional annotations associated with the content. Can be annotation objects or dicts.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content from an underlying implementation.
            **kwargs: Additional keyword arguments (merged into additional_properties).
        """
        self.annotations: list[Annotations] | None = None
        # Handle annotations conversion from dict format (for SerializationMixin support)
        if annotations is not None:
            converted_annotations: list[Annotations] = []
            for annotation_data in annotations:
                if isinstance(annotation_data, Annotations):
                    # If it's already an annotation object, keep it as is
                    converted_annotations.append(annotation_data)
                elif isinstance(annotation_data, MutableMapping) and annotation_data.get("type", "") == "citation":
                    converted_annotations.append(CitationAnnotation.from_dict(annotation_data))
                else:
                    logger.debug(
                        f"Unknown annotation found: {annotation_data.get('type', 'no_type')}"
                        f" with data: {annotation_data}"
                    )
            self.annotations = converted_annotations

        # Merge kwargs into additional_properties
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs)

        self.raw_representation = raw_representation

    def to_dict(self, *, exclude: set[str] | None = None, exclude_none: bool = True) -> dict[str, Any]:
        """Convert the instance to a dictionary.

        Extracts additional_properties fields to the root level.

        Args:
            exclude: Set of field names to exclude from serialization.
            exclude_none: Whether to exclude None values from the output. Defaults to True.

        Returns:
            Dictionary representation of the instance.
        """
        # Get the base dict from SerializationMixin
        result = super().to_dict(exclude=exclude, exclude_none=exclude_none)

        # Extract additional_properties to root level
        if self.additional_properties:
            result.update(self.additional_properties)

        return result


class TextContent(BaseContent):
    """Represents text content in a chat.

    Attributes:
        text: The text content represented by this instance.
        type: The type of content, which is always "text" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.
    """

    def __init__(
        self,
        text: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
        **kwargs: Any,
    ):
        """Initializes a TextContent instance.

        Args:
            text: The text content represented by this instance.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            annotations: Optional annotations associated with the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.text = text
        self.type: Literal["text"] = "text"

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

        # Merge raw representations
        if self.raw_representation is None:
            raw_representation = other.raw_representation
        elif other.raw_representation is None:
            raw_representation = self.raw_representation
        else:
            raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])

        # Merge annotations
        if self.annotations is None:
            annotations = other.annotations
        elif other.annotations is None:
            annotations = self.annotations
        else:
            annotations = self.annotations + other.annotations

        # Create new instance using from_dict for proper deserialization
        result_dict = {
            "text": self.text + other.text,
            "type": "text",
            "annotations": [ann.to_dict(exclude_none=False) for ann in annotations] if annotations else None,
            "additional_properties": {
                **(other.additional_properties or {}),
                **(self.additional_properties or {}),
            },
            "raw_representation": raw_representation,
        }
        return TextContent.from_dict(result_dict)

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

        # Concatenate text
        self.text += other.text

        # Merge additional properties (self takes precedence)
        if self.additional_properties is None:
            self.additional_properties = {}
        if other.additional_properties:
            # Update from other first, then restore self's values to maintain precedence
            self_props = self.additional_properties.copy()
            self.additional_properties.update(other.additional_properties)
            self.additional_properties.update(self_props)

        # Merge raw representations
        if self.raw_representation is None:
            self.raw_representation = other.raw_representation
        elif other.raw_representation is not None:
            self.raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])

        # Merge annotations
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

    def __init__(
        self,
        text: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
        **kwargs: Any,
    ):
        """Initializes a TextReasoningContent instance.

        Args:
            text: The text content represented by this instance.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            annotations: Optional annotations associated with the content.
            **kwargs: Any additional keyword arguments.
        """
        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.text = text
        self.type: Literal["text_reasoning"] = "text_reasoning"

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

        # Merge raw representations
        if self.raw_representation is None:
            raw_representation = other.raw_representation
        elif other.raw_representation is None:
            raw_representation = self.raw_representation
        else:
            raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])

        # Merge annotations
        if self.annotations is None:
            annotations = other.annotations
        elif other.annotations is None:
            annotations = self.annotations
        else:
            annotations = self.annotations + other.annotations

        # Create new instance using from_dict for proper deserialization
        result_dict = {
            "text": self.text + other.text,
            "type": "text_reasoning",
            "annotations": [ann.to_dict(exclude_none=False) for ann in annotations] if annotations else None,
            "additional_properties": {**(self.additional_properties or {}), **(other.additional_properties or {})},
            "raw_representation": raw_representation,
        }
        return TextReasoningContent.from_dict(result_dict)

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

        # Concatenate text
        self.text += other.text

        # Merge additional properties (self takes precedence)
        if self.additional_properties is None:
            self.additional_properties = {}
        if other.additional_properties:
            # Update from other first, then restore self's values to maintain precedence
            self_props = self.additional_properties.copy()
            self.additional_properties.update(other.additional_properties)
            self.additional_properties.update(self_props)

        # Merge raw representations
        if self.raw_representation is None:
            self.raw_representation = other.raw_representation
        elif other.raw_representation is not None:
            self.raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])

        # Merge annotations
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

    @overload
    def __init__(
        self,
        *,
        uri: str,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
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
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
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
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
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

        # Validate URI format and extract media type if not provided
        validated_uri = self._validate_uri(uri)
        if media_type is None:
            match = URI_PATTERN.match(validated_uri)
            if match:
                media_type = match.group("media_type")

        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.uri = validated_uri
        self.media_type = media_type
        self.type: Literal["data"] = "data"

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

    def __init__(
        self,
        uri: str,
        media_type: str,
        *,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
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
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.uri = uri
        self.media_type = media_type
        self.type: Literal["uri"] = "uri"

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

    def __init__(
        self,
        *,
        message: str | None = None,
        error_code: str | None = None,
        details: str | None = None,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
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
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.message = message
        self.error_code = error_code
        self.details = details
        self.type: Literal["error"] = "error"

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

    def __init__(
        self,
        *,
        call_id: str,
        name: str,
        arguments: str | dict[str, Any | None] | None = None,
        exception: Exception | None = None,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
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
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.call_id = call_id
        self.name = name
        self.arguments = arguments
        self.exception = exception
        self.type: Literal["function_call"] = "function_call"

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

    def __init__(
        self,
        *,
        call_id: str,
        result: Any | None = None,
        exception: Exception | None = None,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
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
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.call_id = call_id
        self.result = result
        self.exception = exception
        self.type: Literal["function_result"] = "function_result"


class UsageContent(BaseContent):
    """Represents usage information associated with a chat request and response.

    Attributes:
        details: The usage information, including input and output token counts, and any additional counts.
        type: The type of content, which is always "usage" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

    def __init__(
        self,
        details: UsageDetails | MutableMapping[str, Any],
        *,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a UsageContent instance."""
        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        # Convert dict to UsageDetails if needed
        if isinstance(details, MutableMapping):
            details = UsageDetails.from_dict(details)
        self.details = details
        self.type: Literal["usage"] = "usage"


class HostedFileContent(BaseContent):
    """Represents a hosted file content.

    Attributes:
        file_id: The identifier of the hosted file.
        type: The type of content, which is always "hosted_file" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

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
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.file_id = file_id
        self.type: Literal["hosted_file"] = "hosted_file"


class HostedVectorStoreContent(BaseContent):
    """Represents a hosted vector store content.

    Attributes:
        vector_store_id: The identifier of the hosted vector store.
        type: The type of content, which is always "hosted_vector_store" for this class.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    """

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
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.vector_store_id = vector_store_id
        self.type: Literal["hosted_vector_store"] = "hosted_vector_store"


class BaseUserInputRequest(BaseContent):
    """Base class for all user requests."""

    def __init__(
        self,
        *,
        id: str,
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize BaseUserInputRequest.

        Args:
            id: The unique identifier for the request.
            annotations: Optional annotations associated with the content.
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
        if not id or len(id) < 1:
            raise ValueError("id must be at least 1 character long")
        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.id = id
        self.type: Literal["user_input_request"] = "user_input_request"


class FunctionApprovalResponseContent(BaseContent):
    """Represents a response for user approval of a function call."""

    def __init__(
        self,
        approved: bool,
        *,
        id: str,
        function_call: FunctionCallContent | MutableMapping[str, Any],
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionApprovalResponseContent instance.

        Args:
            approved: Whether the function call was approved.
            id: The unique identifier for the request.
            function_call: The function call content to be approved. Can be a FunctionCallContent object or dict.
            annotations: Optional list of annotations for the request.
            additional_properties: Optional additional properties for the request.
            raw_representation: Optional raw representation of the request.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.id = id
        self.approved = approved
        # Convert dict to FunctionCallContent if needed (for SerializationMixin support)
        if isinstance(function_call, MutableMapping):
            self.function_call = FunctionCallContent.from_dict(function_call)
        else:
            self.function_call = function_call
        # Override the type for this specific subclass
        self.type: Literal["function_approval_response"] = "function_approval_response"


class FunctionApprovalRequestContent(BaseContent):
    """Represents a request for user approval of a function call."""

    def __init__(
        self,
        *,
        id: str,
        function_call: FunctionCallContent | MutableMapping[str, Any],
        annotations: list[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionApprovalRequestContent instance.

        Args:
            id: The unique identifier for the request.
            function_call: The function call content to be approved. Can be a FunctionCallContent object or dict.
            annotations: Optional list of annotations for the request.
            additional_properties: Optional additional properties for the request.
            raw_representation: Optional raw representation of the request.
            **kwargs: Additional keyword arguments.
        """
        super().__init__(
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **kwargs,
        )
        self.id = id
        # Convert dict to FunctionCallContent if needed (for SerializationMixin support)
        if isinstance(function_call, MutableMapping):
            self.function_call = FunctionCallContent.from_dict(function_call)
        else:
            self.function_call = function_call
        # Override the type for this specific subclass
        self.type: Literal["function_approval_request"] = "function_approval_request"

    def create_response(self, approved: bool) -> "FunctionApprovalResponseContent":
        """Create a response for the function approval request."""
        return FunctionApprovalResponseContent(
            approved,
            id=self.id,
            function_call=self.function_call,
            additional_properties=self.additional_properties,
        )


UserInputRequestContents = FunctionApprovalRequestContent

Contents = (
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
    | FunctionApprovalResponseContent
)

# region Chat Response constants


class Role(SerializationMixin, metaclass=EnumLike):
    """Describes the intended purpose of a message within a chat interaction.

    Attributes:
        value: The string representation of the role.

    Properties:
        SYSTEM: The role that instructs or sets the behavior of the AI system.
        USER: The role that provides user input for chat interactions.
        ASSISTANT: The role that provides responses to system-instructed, user-prompted input.
        TOOL: The role that provides additional information and references in response to tool use requests.
    """

    # Constants configuration for EnumLike metaclass
    _constants: ClassVar[dict[str, str]] = {
        "SYSTEM": "system",
        "USER": "user",
        "ASSISTANT": "assistant",
        "TOOL": "tool",
    }

    # Type annotations for constants
    SYSTEM: "Role"
    USER: "Role"
    ASSISTANT: "Role"
    TOOL: "Role"

    def __init__(self, value: str) -> None:
        """Initialize Role with a value.

        Args:
            value: The string representation of the role.
        """
        self.value = value

    def __str__(self) -> str:
        """Returns the string representation of the role."""
        return self.value

    def __repr__(self) -> str:
        """Returns the string representation of the role."""
        return f"Role(value={self.value!r})"

    def __eq__(self, other: object) -> bool:
        """Check if two Role instances are equal."""
        if not isinstance(other, Role):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash of the Role for use in sets and dicts."""
        return hash(self.value)


class FinishReason(SerializationMixin, metaclass=EnumLike):
    """Represents the reason a chat response completed.

    Attributes:
        value: The string representation of the finish reason.
    """

    # Constants configuration for EnumLike metaclass
    _constants: ClassVar[dict[str, str]] = {
        "CONTENT_FILTER": "content_filter",
        "LENGTH": "length",
        "STOP": "stop",
        "TOOL_CALLS": "tool_calls",
    }

    # Type annotations for constants
    CONTENT_FILTER: "FinishReason"
    LENGTH: "FinishReason"
    STOP: "FinishReason"
    TOOL_CALLS: "FinishReason"

    def __init__(self, value: str) -> None:
        """Initialize FinishReason with a value.

        Args:
            value: The string representation of the finish reason.
        """
        self.value = value

    def __eq__(self, other: object) -> bool:
        """Check if two FinishReason instances are equal."""
        if not isinstance(other, FinishReason):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash of the FinishReason for use in sets and dicts."""
        return hash(self.value)

    def __str__(self) -> str:
        """Returns the string representation of the finish reason."""
        return self.value

    def __repr__(self) -> str:
        """Returns the string representation of the finish reason."""
        return f"FinishReason(value={self.value!r})"


# region ChatMessage


class ChatMessage(SerializationMixin):
    """Represents a chat message.

    Attributes:
        role: The role of the author of the message.
        contents: The chat message content items.
        author_name: The name of the author of the message.
        message_id: The ID of the chat message.
        additional_properties: Any additional properties associated with the chat message.
        raw_representation: The raw representation of the chat message from an underlying implementation.

    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation"}

    @overload
    def __init__(
        self,
        role: Role | Literal["system", "user", "assistant", "tool"],
        *,
        text: str,
        author_name: str | None = None,
        message_id: str | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a ChatMessage with a role and text content.

        Args:
            role: The role of the author of the message.
            text: The text content of the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
            raw_representation: Optional raw representation of the chat message.
            **kwargs: Additional keyword arguments.
        """

    @overload
    def __init__(
        self,
        role: Role | Literal["system", "user", "assistant", "tool"],
        *,
        contents: Sequence[Contents | Mapping[str, Any]],
        author_name: str | None = None,
        message_id: str | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a ChatMessage with a role and optional contents.

        Args:
            role: The role of the author of the message.
            contents: Optional list of BaseContent items to include in the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
            raw_representation: Optional raw representation of the chat message.
            **kwargs: Additional keyword arguments.
        """

    def __init__(
        self,
        role: Role | Literal["system", "user", "assistant", "tool"] | dict[str, Any],
        *,
        text: str | None = None,
        contents: Sequence[Contents | Mapping[str, Any]] | None = None,
        author_name: str | None = None,
        message_id: str | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize ChatMessage.

        Args:
            role: The role of the author of the message (Role, string, or dict).
            text: Optional text content of the message.
            contents: Optional list of BaseContent items or dicts to include in the message.
            author_name: Optional name of the author of the message.
            message_id: Optional ID of the chat message.
            additional_properties: Optional additional properties associated with the chat message.
            raw_representation: Optional raw representation of the chat message.
            kwargs: will be combined with additional_properties if provided.
        """
        # Handle role conversion
        if isinstance(role, dict):
            role = Role.from_dict(role)
        elif isinstance(role, str):
            role = Role(value=role)

        # Handle contents conversion
        parsed_contents = [] if contents is None else _parse_content_list(contents)

        if text is not None:
            parsed_contents.append(TextContent(text=text))

        self.role = role
        self.contents = parsed_contents
        self.author_name = author_name
        self.message_id = message_id
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs or {})
        self.raw_representation = raw_representation

    @property
    def text(self) -> str:
        """Returns the text content of the message.

        Remarks:
            This property concatenates the text of all TextContent objects in Contents.
        """
        return " ".join(content.text for content in self.contents if isinstance(content, TextContent))


# region ChatResponse


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
        elif isinstance(content, (dict, MutableMapping)):
            try:
                cont = _parse_content(content)
                message.contents.append(cont)
            except ValidationError as ve:
                logger.warning(f"Skipping unknown content type or invalid content: {ve}")
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
        if update.model_id is not None:
            response.model_id = update.model_id


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


class ChatResponse(SerializationMixin):
    """Represents the response to a chat request.

    Attributes:
        messages: The list of chat messages in the response.
        response_id: The ID of the chat response.
        conversation_id: An identifier for the state of the conversation.
        model_id: The model ID used in the creation of the chat response.
        created_at: A timestamp for the chat response.
        finish_reason: The reason for the chat response.
        usage_details: The usage details for the chat response.
        structured_output: The structured output of the chat response, if applicable.
        additional_properties: Any additional properties associated with the chat response.
        raw_representation: The raw representation of the chat response from an underlying implementation.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation", "additional_properties"}

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
        messages: ChatMessage | MutableSequence[ChatMessage] | list[dict[str, Any]] | None = None,
        text: TextContent | str | None = None,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: FinishReason | dict[str, Any] | None = None,
        usage_details: UsageDetails | dict[str, Any] | None = None,
        value: Any | None = None,
        response_format: type[BaseModel] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a ChatResponse with the provided parameters."""
        # Handle messages conversion
        if messages is None:
            messages = []
        elif not isinstance(messages, MutableSequence):
            messages = [messages]
        else:
            # Convert any dicts in messages list to ChatMessage objects
            converted_messages: list[ChatMessage] = []
            for msg in messages:
                if isinstance(msg, dict):
                    converted_messages.append(ChatMessage.from_dict(msg))
                else:
                    converted_messages.append(msg)
            messages = converted_messages

        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            messages.append(ChatMessage(role=Role.ASSISTANT, contents=[text]))

        # Handle finish_reason conversion
        if isinstance(finish_reason, dict):
            finish_reason = FinishReason.from_dict(finish_reason)

        # Handle usage_details conversion
        if isinstance(usage_details, dict):
            usage_details = UsageDetails.from_dict(usage_details)

        self.messages = list(messages)
        self.response_id = response_id
        self.conversation_id = conversation_id
        self.model_id = model_id
        self.created_at = created_at
        self.finish_reason = finish_reason
        self.usage_details = usage_details
        self.value = value
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs or {})
        self.raw_representation: Any | list[Any] | None = raw_representation

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


class ChatResponseUpdate(SerializationMixin):
    """Represents a single streaming response chunk from a `ChatClient`.

    Attributes:
        contents: The chat response update content items.
        role: The role of the author of the response update.
        author_name: The name of the author of the response update.
        response_id: The ID of the response of which this update is a part.
        message_id: The ID of the message of which this update is a part.
        conversation_id: An identifier for the state of the conversation of which this update is a part.
        model_id: The model ID associated with this response update.
        created_at: A timestamp for the chat response update.
        finish_reason: The finish reason for the operation.
        additional_properties: Any additional properties associated with the chat response update.
        raw_representation: The raw representation of the chat response update from an underlying implementation.

    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation"}

    def __init__(
        self,
        *,
        contents: Sequence[Contents | dict[str, Any]] | None = None,
        text: TextContent | str | None = None,
        role: Role | Literal["system", "user", "assistant", "tool"] | dict[str, Any] | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: FinishReason | dict[str, Any] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a ChatResponseUpdate with the provided parameters.

        Args:
            contents: Optional list of BaseContent items or dicts to include in the update.
            text: Optional text content to include in the update.
            role: Optional role of the author of the response update (Role, string, or dict
            author_name: Optional name of the author of the response update.
            response_id: Optional ID of the response of which this update is a part.
            message_id: Optional ID of the message of which this update is a part.
            conversation_id: Optional identifier for the state of the conversation of which this update is a part
            model_id: Optional model ID associated with this response update.
            created_at: Optional timestamp for the chat response update.
            finish_reason: Optional finish reason for the operation.
            additional_properties: Optional additional properties associated with the chat response update.
            raw_representation: Optional raw representation of the chat response update
                from an underlying implementation.
            **kwargs: Any additional keyword arguments.

        """
        # Handle contents conversion
        contents = [] if contents is None else _parse_content_list(contents)

        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            contents.append(text)

        # Handle role conversion
        if isinstance(role, dict):
            role = Role.from_dict(role)
        elif isinstance(role, str):
            role = Role(value=role)

        # Handle finish_reason conversion
        if isinstance(finish_reason, dict):
            finish_reason = FinishReason.from_dict(finish_reason)

        self.contents = list(contents)
        self.role = role
        self.author_name = author_name
        self.response_id = response_id
        self.message_id = message_id
        self.conversation_id = conversation_id
        self.model_id = model_id
        self.created_at = created_at
        self.finish_reason = finish_reason
        self.additional_properties = additional_properties
        self.raw_representation = raw_representation

    @property
    def text(self) -> str:
        """Returns the concatenated text of all contents in the update."""
        return "".join(content.text for content in self.contents if isinstance(content, TextContent))

    def __str__(self) -> str:
        return self.text

    def with_(self, contents: list[BaseContent] | None = None, message_id: str | None = None) -> "ChatResponseUpdate":
        """Returns a new instance with the specified contents and message_id."""
        if contents is None:
            contents = []

        # Create a dictionary of current instance data
        current_data = self.to_dict()

        # Update with new values
        current_data["contents"] = self.contents + contents
        current_data["message_id"] = message_id or self.message_id

        return ChatResponseUpdate.from_dict(current_data)


# region AgentRunResponse


class AgentRunResponse(SerializationMixin):
    """Represents the response to an Agent run request.

    Provides one or more response messages and metadata about the response.
    A typical response will contain a single message, but may contain multiple
    messages in scenarios involving function calls, RAG retrievals, or complex logic.
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation"}

    def __init__(
        self,
        messages: ChatMessage
        | list[ChatMessage]
        | MutableMapping[str, Any]
        | list[MutableMapping[str, Any]]
        | None = None,
        response_id: str | None = None,
        created_at: CreatedAtT | None = None,
        usage_details: UsageDetails | MutableMapping[str, Any] | None = None,
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
                for message_data in messages:
                    if isinstance(message_data, ChatMessage):
                        processed_messages.append(message_data)
                    elif isinstance(message_data, MutableMapping):
                        processed_messages.append(ChatMessage.from_dict(message_data))
                    else:
                        logger.warning(f"Unknown message content: {message_data}")
            elif isinstance(messages, MutableMapping):
                processed_messages.append(ChatMessage.from_dict(messages))

        # Convert usage_details from dict if needed (for SerializationMixin support)
        if isinstance(usage_details, MutableMapping):
            usage_details = UsageDetails.from_dict(usage_details)

        self.messages = processed_messages
        self.response_id = response_id
        self.created_at = created_at
        self.usage_details = usage_details
        self.value = value
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs or {})
        self.raw_representation = raw_representation

    @property
    def text(self) -> str:
        """Get the concatenated text of all messages."""
        return "".join(msg.text for msg in self.messages) if self.messages else ""

    @property
    def user_input_requests(self) -> list[UserInputRequestContents]:
        """Get all BaseUserInputRequest messages from the response."""
        return [
            content
            for msg in self.messages
            for content in msg.contents
            if isinstance(content, UserInputRequestContents)
        ]

    @classmethod
    def from_agent_run_response_updates(
        cls: type[TAgentRunResponse],
        updates: Sequence["AgentRunResponseUpdate"],
        *,
        output_format_type: type[BaseModel] | None = None,
    ) -> TAgentRunResponse:
        """Joins multiple updates into a single AgentRunResponse."""
        msg = cls(messages=[])
        for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        if output_format_type:
            msg.try_parse_value(output_format_type)
        return msg

    @classmethod
    async def from_agent_response_generator(
        cls: type[TAgentRunResponse],
        updates: AsyncIterable["AgentRunResponseUpdate"],
        *,
        output_format_type: type[BaseModel] | None = None,
    ) -> TAgentRunResponse:
        """Joins multiple updates into a single AgentRunResponse."""
        msg = cls(messages=[])
        async for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        if output_format_type:
            msg.try_parse_value(output_format_type)
        return msg

    def __str__(self) -> str:
        return self.text

    def try_parse_value(self, output_format_type: type[BaseModel]) -> None:
        """If there is a value, does nothing, otherwise tries to parse the text into the value."""
        if self.value is None:
            try:
                self.value = output_format_type.model_validate_json(self.text)  # type: ignore[reportUnknownMemberType]
            except ValidationError as ex:
                logger.debug("Failed to parse value from agent run response text: %s", ex)


# region AgentRunResponseUpdate


class AgentRunResponseUpdate(SerializationMixin):
    """Represents a single streaming response chunk from an Agent."""

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation"}

    def __init__(
        self,
        *,
        contents: Sequence[Contents | MutableMapping[str, Any]] | None = None,
        text: TextContent | str | None = None,
        role: Role | MutableMapping[str, Any] | str | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        created_at: CreatedAtT | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an AgentRunResponseUpdate.

        Args:
            contents: Optional list of BaseContent items or dicts to include in the update.
            text: Optional text content of the update.
            role: The role of the author of the response update (Role, string, or dict
            author_name: Optional name of the author of the response update.
            response_id: Optional ID of the response of which this update is a part.
            message_id: Optional ID of the message of which this update is a part.
            created_at: Optional timestamp for the chat response update.
            additional_properties: Optional additional properties associated with the chat response update.
            raw_representation: Optional raw representation of the chat response update.
            kwargs: will be combined with additional_properties if provided.

        """
        contents = [] if contents is None else _parse_content_list(contents)

        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            contents.append(text)

        # Convert role from dict if needed (for SerializationMixin support)
        if isinstance(role, MutableMapping):
            role = Role.from_dict(role)
        elif isinstance(role, str):
            role = Role(value=role)

        self.contents = contents
        self.role = role
        self.author_name = author_name
        self.response_id = response_id
        self.message_id = message_id
        self.created_at = created_at
        self.additional_properties = additional_properties
        self.raw_representation: Any | list[Any] | None = raw_representation

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
        return [content for content in self.contents if isinstance(content, UserInputRequestContents)]

    def __str__(self) -> str:
        return self.text


# region ChatOptions


class ToolMode(SerializationMixin, metaclass=EnumLike):
    """Defines if and how tools are used in a chat request."""

    # Constants configuration for EnumLike metaclass
    _constants: ClassVar[dict[str, tuple[str, ...]]] = {
        "AUTO": ("auto",),
        "REQUIRED_ANY": ("required",),
        "NONE": ("none",),
    }

    # Type annotations for constants
    AUTO: "ToolMode"
    REQUIRED_ANY: "ToolMode"
    NONE: "ToolMode"

    def __init__(
        self,
        mode: Literal["auto", "required", "none"] = "none",
        required_function_name: str | None = None,
    ) -> None:
        """Initialize ToolMode.

        Args:
            mode: The tool mode - "auto", "required", or "none".
            required_function_name: Optional function name for required mode.
        """
        self.mode = mode
        self.required_function_name = required_function_name

    @classmethod
    def REQUIRED(cls, function_name: str | None = None) -> "ToolMode":
        """Returns a ToolMode that requires the specified function to be called."""
        return cls(mode="required", required_function_name=function_name)

    def __eq__(self, other: object) -> bool:
        """Checks equality with another ToolMode or string."""
        if isinstance(other, str):
            return self.mode == other
        if isinstance(other, ToolMode):
            return self.mode == other.mode and self.required_function_name == other.required_function_name
        return False

    def __hash__(self) -> int:
        """Return hash of the ToolMode for use in sets and dicts."""
        return hash((self.mode, self.required_function_name))

    def serialize_model(self) -> str:
        """Serializes the ToolMode to just the mode string."""
        return self.mode

    def __str__(self) -> str:
        """Returns the string representation of the mode."""
        return self.mode

    def __repr__(self) -> str:
        """Returns the string representation of the ToolMode."""
        if self.required_function_name:
            return f"ToolMode(mode={self.mode!r}, required_function_name={self.required_function_name!r})"
        return f"ToolMode(mode={self.mode!r})"


class ChatOptions(SerializationMixin):
    """Common request settings for AI services."""

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"_tools"}  # Internal field, use .tools property

    def __init__(
        self,
        *,
        model_id: str | None = None,
        allow_multiple_tool_calls: bool | None = None,
        conversation_id: str | None = None,
        frequency_penalty: float | None = None,
        instructions: str | None = None,
        logit_bias: MutableMapping[str | int, float] | None = None,
        max_tokens: int | None = None,
        metadata: MutableMapping[str, str] | None = None,
        presence_penalty: float | None = None,
        response_format: type[BaseModel] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        store: bool | None = None,
        temperature: float | None = None,
        tool_choice: ToolMode | Literal["auto", "required", "none"] | Mapping[str, Any] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        top_p: float | None = None,
        user: str | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
    ):
        """Initialize ChatOptions.

        Args:
            additional_properties: Provider-specific additional properties.
            model_id: The AI model ID to use.
            allow_multiple_tool_calls: Whether to allow multiple tool calls.
            conversation_id: The conversation ID.
            frequency_penalty: The frequency penalty (must be between -2.0 and 2.0).
            instructions: the instructions, will be turned into a system or equivalent message.
            logit_bias: The logit bias mapping.
            max_tokens: The maximum number of tokens (must be > 0).
            metadata: Metadata mapping.
            presence_penalty: The presence penalty (must be between -2.0 and 2.0).
            response_format: Structured output response format schema. Must be a valid Pydantic model.
            seed: Random seed for reproducibility.
            stop: Stop sequences.
            store: Whether to store the conversation.
            temperature: The temperature (must be between 0.0 and 2.0).
            tool_choice: The tool choice mode.
            tools: List of available tools.
            top_p: The top-p value (must be between 0.0 and 1.0).
            user: The user ID.
        """
        # Validate numeric constraints and convert types as needed
        if frequency_penalty is not None:
            if not (-2.0 <= frequency_penalty <= 2.0):
                raise ValueError("frequency_penalty must be between -2.0 and 2.0")
            frequency_penalty = float(frequency_penalty)
        if presence_penalty is not None:
            if not (-2.0 <= presence_penalty <= 2.0):
                raise ValueError("presence_penalty must be between -2.0 and 2.0")
            presence_penalty = float(presence_penalty)
        if temperature is not None:
            if not (0.0 <= temperature <= 2.0):
                raise ValueError("temperature must be between 0.0 and 2.0")
            temperature = float(temperature)
        if top_p is not None:
            if not (0.0 <= top_p <= 1.0):
                raise ValueError("top_p must be between 0.0 and 1.0")
            top_p = float(top_p)
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")

        self.additional_properties = additional_properties or {}
        self.model_id = model_id
        self.allow_multiple_tool_calls = allow_multiple_tool_calls
        self.conversation_id = conversation_id
        self.frequency_penalty = frequency_penalty
        self.instructions = instructions
        self.logit_bias = logit_bias
        self.max_tokens = max_tokens
        self.metadata = metadata
        self.presence_penalty = presence_penalty
        self.response_format = response_format
        self.seed = seed
        self.stop = stop
        self.store = store
        self.temperature = temperature
        self.tool_choice = self._validate_tool_mode(tool_choice)
        self._tools = self._validate_tools(tools)
        self.top_p = top_p
        self.user = user

    @property
    def tools(self) -> list[ToolProtocol | MutableMapping[str, Any]] | None:
        """Return the tools that are specified."""
        return self._tools

    @tools.setter
    def tools(
        self,
        new_tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None,
    ) -> None:
        """Set the tools."""
        self._tools = self._validate_tools(new_tools)

    @classmethod
    def _validate_tools(
        cls,
        tools: (
            ToolProtocol
            | Callable[..., Any]
            | MutableMapping[str, Any]
            | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
            | None
        ),
    ) -> list[ToolProtocol | MutableMapping[str, Any]] | None:
        """Parse the tools field."""
        if not tools:
            return None
        if not isinstance(tools, Sequence):
            if not isinstance(tools, (ToolProtocol, MutableMapping)):
                return [ai_function(tools)]
            return [tools]
        return [tool if isinstance(tool, (ToolProtocol, MutableMapping)) else ai_function(tool) for tool in tools]

    @classmethod
    def _validate_tool_mode(
        cls, tool_choice: ToolMode | Literal["auto", "required", "none"] | Mapping[str, Any] | None
    ) -> ToolMode | str | None:
        """Validates the tool_choice field to ensure it is a valid ToolMode."""
        if not tool_choice:
            return None
        if isinstance(tool_choice, str):
            match tool_choice:
                case "auto":
                    return ToolMode.AUTO
                case "required":
                    return ToolMode.REQUIRED_ANY
                case "none":
                    return ToolMode.NONE
                case _:
                    raise ValidationError(f"Invalid tool choice: {tool_choice}")
        if isinstance(tool_choice, (dict, Mapping)):
            return ToolMode.from_dict(tool_choice)  # type: ignore
        return tool_choice

    def to_provider_settings(self, by_alias: bool = True, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert the ChatOptions to a dictionary suitable for provider requests.

        Args:
            by_alias: Use alias names for fields if True.
            exclude: Additional keys to exclude from the output.

        Returns:
            Dictionary of settings for provider.
        """
        default_exclude = {"additional_properties", "type"}  # 'type' is for serialization, not API calls
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

        settings = self.to_dict(exclude_none=True, exclude=merged_exclude)
        if by_alias and self.model_id is not None:
            settings["model"] = settings.pop("model_id", None)

        # Serialize tool_choice to its string representation for provider settings
        if "tool_choice" in settings and isinstance(self.tool_choice, ToolMode):
            settings["tool_choice"] = self.tool_choice.serialize_model()

        settings = {k: v for k, v in settings.items() if v is not None}
        settings.update(self.additional_properties)
        for key in merged_exclude:
            settings.pop(key, None)
        return settings

    def __and__(self, other: object) -> "ChatOptions":
        """Combines two ChatOptions instances.

        The values from the other ChatOptions take precedence.
        List and dicts are combined.
        """
        if not isinstance(other, ChatOptions):
            return self
        other_tools = other.tools
        # tool_choice has a specialized serialize method. Save it here so we can fix it later.
        tool_choice = other.tool_choice or self.tool_choice
        # response_format is a class type that can't be serialized. Save it here so we can restore it later.
        response_format = self.response_format
        # Start with a shallow copy of self that preserves tool objects
        combined = ChatOptions.from_dict(self.to_dict())
        combined.tool_choice = self.tool_choice
        combined.tools = list(self.tools) if self.tools else None
        combined.logit_bias = dict(self.logit_bias) if self.logit_bias else None
        combined.metadata = dict(self.metadata) if self.metadata else None
        combined.additional_properties = dict(self.additional_properties)
        combined.response_format = response_format

        # Apply scalar and mapping updates from the other options
        updated_data = other.to_dict(exclude_none=True, exclude={"tools"})
        logit_bias = updated_data.pop("logit_bias", {})
        metadata = updated_data.pop("metadata", {})
        additional_properties = updated_data.pop("additional_properties", {})

        for key, value in updated_data.items():
            setattr(combined, key, value)

        combined.tool_choice = tool_choice
        # Preserve response_format from other if it exists, otherwise keep self's
        if other.response_format is not None:
            combined.response_format = other.response_format
        combined.instructions = "\n".join([combined.instructions or "", other.instructions or ""])
        combined.logit_bias = {**(combined.logit_bias or {}), **logit_bias}
        combined.metadata = {**(combined.metadata or {}), **metadata}
        combined.additional_properties = {**(combined.additional_properties or {}), **additional_properties}
        if other_tools:
            if combined.tools is None:
                combined.tools = list(other_tools)
            else:
                for tool in other_tools:
                    if tool not in combined.tools:
                        combined.tools.append(tool)
        return combined
