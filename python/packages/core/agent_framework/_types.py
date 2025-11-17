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
from typing import Any, ClassVar, Literal, TypeVar, cast, overload

from pydantic import BaseModel, ValidationError

from ._logging import get_logger
from ._serialization import SerializationMixin
from ._tools import ToolProtocol, ai_function
from .exceptions import AdditionItemMismatch, ContentError

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
    "prepare_function_call_results",
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
        Content object

    Raises:
        ContentError if parsing fails
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
            raise ContentError(f"Unknown content type '{content_type}'")


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
            except ContentError as exc:
                logger.warning(f"Skipping unknown content type or invalid content: {exc}")
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

    Examples:
        .. code-block:: python

            from agent_framework import UsageDetails

            # Create usage details
            usage = UsageDetails(
                input_token_count=100,
                output_token_count=50,
                total_token_count=150,
            )
            print(usage.total_token_count)  # 150

            # With additional counts
            usage = UsageDetails(
                input_token_count=100,
                output_token_count=50,
                total_token_count=150,
                reasoning_tokens=25,
            )
            print(usage.additional_counts["reasoning_tokens"])  # 25

            # Combine usage details
            usage1 = UsageDetails(input_token_count=100, output_token_count=50)
            usage2 = UsageDetails(input_token_count=200, output_token_count=100)
            combined = usage1 + usage2
            print(combined.input_token_count)  # 300
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

        Keyword Args:
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

        Keyword Args:
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
    """Represents a region of text that has been annotated.

    Examples:
        .. code-block:: python

            from agent_framework import TextSpanRegion

            # Create a text span region
            region = TextSpanRegion(start_index=0, end_index=10)
            print(region.type)  # "text_span"
    """

    def __init__(
        self,
        *,
        start_index: int | None = None,
        end_index: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize TextSpanRegion.

        Keyword Args:
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
    """Base class for all AI Annotation types."""

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

        Keyword Args:
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

        Keyword Args:
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

    Examples:
        .. code-block:: python

            from agent_framework import CitationAnnotation, TextSpanRegion

            # Create a citation annotation
            citation = CitationAnnotation(
                title="Agent Framework Documentation",
                url="https://example.com/docs",
                snippet="This is a relevant excerpt...",
                annotated_regions=[TextSpanRegion(start_index=0, end_index=25)],
            )
            print(citation.title)  # "Agent Framework Documentation"
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

        Keyword Args:
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
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize BaseContent.

        Keyword Args:
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

        Keyword Args:
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

    Examples:
        .. code-block:: python

            from agent_framework import TextContent

            # Create basic text content
            text = TextContent(text="Hello, world!")
            print(text.text)  # "Hello, world!"

            # Concatenate text content
            text1 = TextContent(text="Hello, ")
            text2 = TextContent(text="world!")
            combined = text1 + text2
            print(combined.text)  # "Hello, world!"
    """

    def __init__(
        self,
        text: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        **kwargs: Any,
    ):
        """Initializes a TextContent instance.

        Args:
            text: The text content represented by this instance.

        Keyword Args:
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

    Examples:
        .. code-block:: python

            from agent_framework import TextReasoningContent

            # Create reasoning content
            reasoning = TextReasoningContent(text="Let me think step by step...")
            print(reasoning.text)  # "Let me think step by step..."

            # Concatenate reasoning content
            reasoning1 = TextReasoningContent(text="First, ")
            reasoning2 = TextReasoningContent(text="second, ")
            combined = reasoning1 + reasoning2
            print(combined.text)  # "First, second, "
    """

    def __init__(
        self,
        text: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        **kwargs: Any,
    ):
        """Initializes a TextReasoningContent instance.

        Args:
            text: The text content represented by this instance.

        Keyword Args:
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


TDataContent = TypeVar("TDataContent", bound="DataContent")


class DataContent(BaseContent):
    """Represents binary data content with an associated media type (also known as a MIME type).

    Important:
        This is for binary data that is represented as a data URI, not for online resources.
        Use ``UriContent`` for online resources.

    Attributes:
        uri: The URI of the data represented by this instance, typically in the form of a data URI.
            Should be in the form: "data:{media_type};base64,{base64_data}".
        media_type: The media type of the data.
        type: The type of content, which is always "data" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    Examples:
        .. code-block:: python

            from agent_framework import DataContent

            # Create from binary data
            image_data = b"raw image bytes"
            data_content = DataContent(data=image_data, media_type="image/png")

            # Create from data URI
            data_uri = "data:image/png;base64,iVBORw0KGgoAAAANS..."
            data_content = DataContent(uri=data_uri)

            # Check media type
            if data_content.has_top_level_media_type("image"):
                print("This is an image")
    """

    @overload
    def __init__(
        self,
        *,
        uri: str,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a DataContent instance with a URI.

        Important:
            This is for binary data that is represented as a data URI, not for online resources.
            Use ``UriContent`` for online resources.

        Keyword Args:
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
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a DataContent instance with binary data.

        Important:
            This is for binary data that is represented as a data URI, not for online resources.
            Use ``UriContent`` for online resources.

        Keyword Args:
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
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a DataContent instance.

        Important:
            This is for binary data that is represented as a data URI, not for online resources.
            Use ``UriContent`` for online resources.

        Keyword Args:
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

    @staticmethod
    def detect_image_format_from_base64(image_base64: str) -> str:
        """Detect image format from base64 data by examining the binary header.

        Args:
            image_base64: Base64 encoded image data

        Returns:
            Image format as string (png, jpeg, webp, gif) with png as fallback
        """
        try:
            # Constants for image format detection
            # ~75 bytes of binary data should be enough to detect most image formats
            FORMAT_DETECTION_BASE64_CHARS = 100

            # Decode a small portion to detect format
            decoded_data = base64.b64decode(image_base64[:FORMAT_DETECTION_BASE64_CHARS])
            if decoded_data.startswith(b"\x89PNG"):
                return "png"
            if decoded_data.startswith(b"\xff\xd8\xff"):
                return "jpeg"
            if decoded_data.startswith(b"RIFF") and b"WEBP" in decoded_data[:12]:
                return "webp"
            if decoded_data.startswith(b"GIF87a") or decoded_data.startswith(b"GIF89a"):
                return "gif"
            return "png"  # Default fallback
        except Exception:
            return "png"  # Fallback if decoding fails

    @staticmethod
    def create_data_uri_from_base64(image_base64: str) -> tuple[str, str]:
        """Create a data URI and media type from base64 image data.

        Args:
            image_base64: Base64 encoded image data

        Returns:
            Tuple of (data_uri, media_type)
        """
        format_type = DataContent.detect_image_format_from_base64(image_base64)
        uri = f"data:image/{format_type};base64,{image_base64}"
        media_type = f"image/{format_type}"
        return uri, media_type

    def get_data_bytes_as_str(self) -> str:
        """Extracts and returns the base64-encoded data from the data URI.

        Returns:
            The binary data as str.
        """
        match = URI_PATTERN.match(self.uri)
        if not match:
            raise ValueError(f"Invalid data URI format: {self.uri}")
        return match.group("base64_data")

    def get_data_bytes(self) -> bytes:
        """Extracts and returns the binary data from the data URI.

        Returns:
            The binary data as bytes.
        """
        base64_data = self.get_data_bytes_as_str()
        return base64.b64decode(base64_data)


class UriContent(BaseContent):
    """Represents a URI content.

    Important:
        This is used for content that is identified by a URI, such as an image or a file.
        For (binary) data URIs, use ``DataContent`` instead.

    Attributes:
        uri: The URI of the content, e.g., 'https://example.com/image.png'.
        media_type: The media type of the content, e.g., 'image/png', 'application/json', etc.
        type: The type of content, which is always "uri" for this class.
        annotations: Optional annotations associated with the content.
        additional_properties: Optional additional properties associated with the content.
        raw_representation: Optional raw representation of the content.

    Examples:
        .. code-block:: python

            from agent_framework import UriContent

            # Create URI content for an image
            image_uri = UriContent(
                uri="https://example.com/image.png",
                media_type="image/png",
            )

            # Create URI content for a document
            doc_uri = UriContent(
                uri="https://example.com/document.pdf",
                media_type="application/pdf",
            )

            # Check if it's an image
            if image_uri.has_top_level_media_type("image"):
                print("This is an image URI")
    """

    def __init__(
        self,
        uri: str,
        media_type: str,
        *,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
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

        Keyword Args:
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
        """Returns a boolean indicating if the media type has the specified top-level media type.

        Args:
            top_level_media_type: The top-level media type to check for, allowed values:
                "image", "text", "application", "audio".

        """
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

    Examples:
        .. code-block:: python

            from agent_framework import ErrorContent

            # Create an error content
            error = ErrorContent(
                message="Failed to process request",
                error_code="PROCESSING_ERROR",
                details="The input format was invalid",
            )
            print(str(error))  # "Error PROCESSING_ERROR: Failed to process request"

            # Error without code
            simple_error = ErrorContent(message="Something went wrong")
            print(str(simple_error))  # "Something went wrong"
    """

    def __init__(
        self,
        *,
        message: str | None = None,
        error_code: str | None = None,
        details: str | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes an ErrorContent instance.

        Keyword Args:
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

    Examples:
        .. code-block:: python

            from agent_framework import FunctionCallContent

            # Create a function call
            func_call = FunctionCallContent(
                call_id="call_123",
                name="get_weather",
                arguments={"location": "Seattle", "unit": "celsius"},
            )

            # Parse arguments
            args = func_call.parse_arguments()
            print(args["location"])  # "Seattle"

            # Create with string arguments (gradual completion)
            func_call_partial_1 = FunctionCallContent(
                call_id="call_124",
                name="search",
                arguments='{"query": ',
            )
            func_call_partial_2 = FunctionCallContent(
                call_id="call_124",
                name="search",
                arguments='"latest news"}',
            )
            full_call = func_call_partial_1 + func_call_partial_2
            args = full_call.parse_arguments()
            print(args["query"])  # "latest news"
    """

    def __init__(
        self,
        *,
        call_id: str,
        name: str,
        arguments: str | dict[str, Any | None] | None = None,
        exception: Exception | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionCallContent instance.

        Keyword Args:
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
        """Parse the arguments into a dictionary.

        If they cannot be parsed as json or if the resulting json is not a dict,
        they are returned as a dictionary with a single key "raw".
        """
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

    Examples:
        .. code-block:: python

            from agent_framework import FunctionResultContent

            # Create a successful function result
            result = FunctionResultContent(
                call_id="call_123",
                result={"temperature": 22, "condition": "sunny"},
            )

            # Create a failed function result
            failed_result = FunctionResultContent(
                call_id="call_124",
                result="Function execution failed",
                exception=ValueError("Invalid location"),
            )
    """

    def __init__(
        self,
        *,
        call_id: str,
        result: Any | None = None,
        exception: Exception | None = None,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionResultContent instance.

        Keyword Args:
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

    Examples:
        .. code-block:: python

            from agent_framework import UsageContent, UsageDetails

            # Create usage content
            usage = UsageContent(
                details=UsageDetails(
                    input_token_count=100,
                    output_token_count=50,
                    total_token_count=150,
                ),
            )
            print(usage.details.total_token_count)  # 150
    """

    def __init__(
        self,
        details: UsageDetails | MutableMapping[str, Any],
        *,
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
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

    Examples:
        .. code-block:: python

            from agent_framework import HostedFileContent

            # Create hosted file content
            file_content = HostedFileContent(file_id="file-abc123")
            print(file_content.file_id)  # "file-abc123"
    """

    def __init__(
        self,
        file_id: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a HostedFileContent instance.

        Args:
            file_id: The identifier of the hosted file.

        Keyword Args:
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
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

    Examples:
        .. code-block:: python

            from agent_framework import HostedVectorStoreContent

            # Create hosted vector store content
            vs_content = HostedVectorStoreContent(vector_store_id="vs-xyz789")
            print(vs_content.vector_store_id)  # "vs-xyz789"
    """

    def __init__(
        self,
        vector_store_id: str,
        *,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a HostedVectorStoreContent instance.

        Args:
            vector_store_id: The identifier of the hosted vector store.

        Keyword Args:
            additional_properties: Optional additional properties associated with the content.
            raw_representation: Optional raw representation of the content.
            **kwargs: Any additional keyword arguments.
        """
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
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize BaseUserInputRequest.

        Keyword Args:
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
    """Represents a response for user approval of a function call.

    Examples:
        .. code-block:: python

            from agent_framework import FunctionApprovalResponseContent, FunctionCallContent

            # Create a function approval response
            func_call = FunctionCallContent(
                call_id="call_123",
                name="send_email",
                arguments={"to": "user@example.com"},
            )
            response = FunctionApprovalResponseContent(
                approved=False,
                id="approval_001",
                function_call=func_call,
            )
            print(response.approved)  # False
    """

    def __init__(
        self,
        approved: bool,
        *,
        id: str,
        function_call: FunctionCallContent | MutableMapping[str, Any],
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionApprovalResponseContent instance.

        Args:
            approved: Whether the function call was approved.

        Keyword Args:
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
    """Represents a request for user approval of a function call.

    Examples:
        .. code-block:: python

            from agent_framework import FunctionApprovalRequestContent, FunctionCallContent

            # Create a function approval request
            func_call = FunctionCallContent(
                call_id="call_123",
                name="send_email",
                arguments={"to": "user@example.com", "subject": "Hello"},
            )
            approval_request = FunctionApprovalRequestContent(
                id="approval_001",
                function_call=func_call,
            )

            # Create response
            approval_response = approval_request.create_response(approved=True)
            print(approval_response.approved)  # True
    """

    def __init__(
        self,
        *,
        id: str,
        function_call: FunctionCallContent | MutableMapping[str, Any],
        annotations: Sequence[Annotations | MutableMapping[str, Any]] | None = None,
        additional_properties: dict[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initializes a FunctionApprovalRequestContent instance.

        Keyword Args:
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


def _prepare_function_call_results_as_dumpable(content: Contents | Any | list[Contents | Any]) -> Any:
    if isinstance(content, list):
        # Particularly deal with lists of Content
        return [_prepare_function_call_results_as_dumpable(item) for item in content]
    if isinstance(content, dict):
        return {k: _prepare_function_call_results_as_dumpable(v) for k, v in content.items()}
    if hasattr(content, "to_dict"):
        return content.to_dict(exclude={"raw_representation", "additional_properties"})
    return content


def prepare_function_call_results(content: Contents | Any | list[Contents | Any]) -> str:
    """Prepare the values of the function call results."""
    if isinstance(content, Contents):
        # For BaseContent objects, use to_dict and serialize to JSON
        return json.dumps(content.to_dict(exclude={"raw_representation", "additional_properties"}))

    dumpable = _prepare_function_call_results_as_dumpable(content)
    if isinstance(dumpable, str):
        return dumpable
    # fallback
    return json.dumps(dumpable)


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

    Examples:
        .. code-block:: python

            from agent_framework import Role

            # Use predefined role constants
            system_role = Role.SYSTEM
            user_role = Role.USER
            assistant_role = Role.ASSISTANT
            tool_role = Role.TOOL

            # Create custom role
            custom_role = Role(value="custom")

            # Compare roles
            print(system_role == Role.SYSTEM)  # True
            print(system_role.value)  # "system"
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

    Examples:
        .. code-block:: python

            from agent_framework import FinishReason

            # Use predefined finish reason constants
            stop_reason = FinishReason.STOP  # Normal completion
            length_reason = FinishReason.LENGTH  # Max tokens reached
            tool_calls_reason = FinishReason.TOOL_CALLS  # Tool calls triggered
            filter_reason = FinishReason.CONTENT_FILTER  # Content filter triggered

            # Check finish reason
            if stop_reason == FinishReason.STOP:
                print("Response completed normally")
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

    Examples:
        .. code-block:: python

            from agent_framework import ChatMessage, TextContent

            # Create a message with text
            user_msg = ChatMessage(role="user", text="What's the weather?")
            print(user_msg.text)  # "What's the weather?"

            # Create a message with role string
            system_msg = ChatMessage(role="system", text="You are a helpful assistant.")

            # Create a message with contents
            assistant_msg = ChatMessage(
                role="assistant",
                contents=[TextContent(text="The weather is sunny!")],
            )
            print(assistant_msg.text)  # "The weather is sunny!"

            # Serialization - to_dict and from_dict
            msg_dict = user_msg.to_dict()
            # {'type': 'chat_message', 'role': {'type': 'role', 'value': 'user'},
            #  'contents': [{'type': 'text', 'text': "What's the weather?"}], 'additional_properties': {}}
            restored_msg = ChatMessage.from_dict(msg_dict)
            print(restored_msg.text)  # "What's the weather?"

            # Serialization - to_json and from_json
            msg_json = user_msg.to_json()
            # '{"type": "chat_message", "role": {"type": "role", "value": "user"}, "contents": [...], ...}'
            restored_from_json = ChatMessage.from_json(msg_json)
            print(restored_from_json.role.value)  # "user"

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

        Keyword Args:
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

        Keyword Args:
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

        Keyword Args:
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


def prepare_messages(messages: str | ChatMessage | list[str] | list[ChatMessage]) -> list[ChatMessage]:
    """Convert various message input formats into a list of ChatMessage objects.

    Args:
        messages: The input messages in various supported formats.

    Returns:
        A list of ChatMessage objects.
    """
    if isinstance(messages, str):
        return [ChatMessage(role="user", text=messages)]
    if isinstance(messages, ChatMessage):
        return [messages]
    return_messages: list[ChatMessage] = []
    for msg in messages:
        if isinstance(msg, str):
            msg = ChatMessage(role="user", text=msg)
        return_messages.append(msg)
    return return_messages


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
            except ContentError as exc:
                logger.warning(f"Skipping unknown content type or invalid content: {exc}")
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

    Examples:
        .. code-block:: python

            from agent_framework import ChatResponse, ChatMessage

            # Create a simple text response
            response = ChatResponse(text="Hello, how can I help you?")
            print(response.text)  # "Hello, how can I help you?"

            # Create a response with messages
            msg = ChatMessage(role="assistant", text="The weather is sunny.")
            response = ChatResponse(
                messages=[msg],
                finish_reason="stop",
                model_id="gpt-4",
            )

            # Combine streaming updates
            updates = [...]  # List of ChatResponseUpdate objects
            response = ChatResponse.from_chat_response_updates(updates)

            # Serialization - to_dict and from_dict
            response_dict = response.to_dict()
            # {'type': 'chat_response', 'messages': [...], 'model_id': 'gpt-4',
            #  'finish_reason': {'type': 'finish_reason', 'value': 'stop'}}
            restored_response = ChatResponse.from_dict(response_dict)
            print(restored_response.model_id)  # "gpt-4"

            # Serialization - to_json and from_json
            response_json = response.to_json()
            # '{"type": "chat_response", "messages": [...], "model_id": "gpt-4", ...}'
            restored_from_json = ChatResponse.from_json(response_json)
            print(restored_from_json.text)  # "The weather is sunny."
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

        Keyword Args:
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

        Keyword Args:
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
        """Initializes a ChatResponse with the provided parameters.

        Keyword Args:
            messages: A single ChatMessage or a sequence of ChatMessage objects to include in the response.
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
        """Joins multiple updates into a single ChatResponse.

        Example:
            .. code-block:: python

                from agent_framework import ChatResponse, ChatResponseUpdate

                # Create some response updates
                updates = [
                    ChatResponseUpdate(role="assistant", text="Hello"),
                    ChatResponseUpdate(text=" How can I help you?"),
                ]

                # Combine updates into a single ChatResponse
                response = ChatResponse.from_chat_response_updates(updates)
                print(response.text)  # "Hello How can I help you?"

        Args:
            updates: A sequence of ChatResponseUpdate objects to combine.

        Keyword Args:
            output_format_type: Optional Pydantic model type to parse the response text into structured data.
        """
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
        """Joins multiple updates into a single ChatResponse.

        Example:
            .. code-block:: python

                from agent_framework import ChatResponse, ChatResponseUpdate, ChatClient

                client = ChatClient()  # should be a concrete implementation
                response = await ChatResponse.from_chat_response_generator(
                    client.get_streaming_response("Hello, how are you?")
                )
                print(response.text)

        Args:
            updates: An async iterable of ChatResponseUpdate objects to combine.

        Keyword Args:
            output_format_type: Optional Pydantic model type to parse the response text into structured data.
        """
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

    Examples:
        .. code-block:: python

            from agent_framework import ChatResponseUpdate, TextContent

            # Create a response update
            update = ChatResponseUpdate(
                contents=[TextContent(text="Hello")],
                role="assistant",
                message_id="msg_123",
            )
            print(update.text)  # "Hello"

            # Create update with text shorthand
            update = ChatResponseUpdate(text="World!", role="assistant")

            # Serialization - to_dict and from_dict
            update_dict = update.to_dict()
            # {'type': 'chat_response_update', 'contents': [{'type': 'text', 'text': 'Hello'}],
            #  'role': {'type': 'role', 'value': 'assistant'}, 'message_id': 'msg_123'}
            restored_update = ChatResponseUpdate.from_dict(update_dict)
            print(restored_update.text)  # "Hello"

            # Serialization - to_json and from_json
            update_json = update.to_json()
            # '{"type": "chat_response_update", "contents": [{"type": "text", "text": "Hello"}], ...}'
            restored_from_json = ChatResponseUpdate.from_json(update_json)
            print(restored_from_json.message_id)  # "msg_123"

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

        Keyword Args:
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


# region AgentRunResponse


class AgentRunResponse(SerializationMixin):
    """Represents the response to an Agent run request.

    Provides one or more response messages and metadata about the response.
    A typical response will contain a single message, but may contain multiple
    messages in scenarios involving function calls, RAG retrievals, or complex logic.

    Examples:
        .. code-block:: python

            from agent_framework import AgentRunResponse, ChatMessage

            # Create agent response
            msg = ChatMessage(role="assistant", text="Task completed successfully.")
            response = AgentRunResponse(messages=[msg], response_id="run_123")
            print(response.text)  # "Task completed successfully."

            # Access user input requests
            user_requests = response.user_input_requests
            print(len(user_requests))  # 0

            # Combine streaming updates
            updates = [...]  # List of AgentRunResponseUpdate objects
            response = AgentRunResponse.from_agent_run_response_updates(updates)

            # Serialization - to_dict and from_dict
            response_dict = response.to_dict()
            # {'type': 'agent_run_response', 'messages': [...], 'response_id': 'run_123',
            #  'additional_properties': {}}
            restored_response = AgentRunResponse.from_dict(response_dict)
            print(restored_response.response_id)  # "run_123"

            # Serialization - to_json and from_json
            response_json = response.to_json()
            # '{"type": "agent_run_response", "messages": [...], "response_id": "run_123", ...}'
            restored_from_json = AgentRunResponse.from_json(response_json)
            print(restored_from_json.text)  # "Task completed successfully."
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation"}

    def __init__(
        self,
        *,
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

        Keyword Args:
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
        """Joins multiple updates into a single AgentRunResponse.

        Args:
            updates: A sequence of AgentRunResponseUpdate objects to combine.

        Keyword Args:
            output_format_type: Optional Pydantic model type to parse the response text into structured data.
        """
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
        """Joins multiple updates into a single AgentRunResponse.

        Args:
            updates: An async iterable of AgentRunResponseUpdate objects to combine.

        Keyword Args:
            output_format_type: Optional Pydantic model type to parse the response text into structured data
        """
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
    """Represents a single streaming response chunk from an Agent.

    Examples:
        .. code-block:: python

            from agent_framework import AgentRunResponseUpdate, TextContent

            # Create an agent run update
            update = AgentRunResponseUpdate(
                contents=[TextContent(text="Processing...")],
                role="assistant",
                response_id="run_123",
            )
            print(update.text)  # "Processing..."

            # Check for user input requests
            user_requests = update.user_input_requests

            # Serialization - to_dict and from_dict
            update_dict = update.to_dict()
            # {'type': 'agent_run_response_update', 'contents': [{'type': 'text', 'text': 'Processing...'}],
            #  'role': {'type': 'role', 'value': 'assistant'}, 'response_id': 'run_123'}
            restored_update = AgentRunResponseUpdate.from_dict(update_dict)
            print(restored_update.response_id)  # "run_123"

            # Serialization - to_json and from_json
            update_json = update.to_json()
            # '{"type": "agent_run_response_update", "contents": [{"type": "text", "text": "Processing..."}], ...}'
            restored_from_json = AgentRunResponseUpdate.from_json(update_json)
            print(restored_from_json.text)  # "Processing..."
    """

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

        Keyword Args:
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
        parsed_contents: list[Contents] = [] if contents is None else _parse_content_list(contents)

        if text is not None:
            if isinstance(text, str):
                text = TextContent(text=text)
            parsed_contents.append(text)

        # Convert role from dict if needed (for SerializationMixin support)
        if isinstance(role, MutableMapping):
            role = Role.from_dict(role)
        elif isinstance(role, str):
            role = Role(value=role)

        self.contents = parsed_contents
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
    """Defines if and how tools are used in a chat request.

    Examples:
        .. code-block:: python

            from agent_framework import ToolMode

            # Use predefined tool modes
            auto_mode = ToolMode.AUTO  # Model decides when to use tools
            required_mode = ToolMode.REQUIRED_ANY  # Model must use a tool
            none_mode = ToolMode.NONE  # No tools allowed

            # Require a specific function
            specific_mode = ToolMode.REQUIRED(function_name="get_weather")
            print(specific_mode.required_function_name)  # "get_weather"

            # Compare modes
            print(auto_mode == "auto")  # True
    """

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
        *,
        required_function_name: str | None = None,
    ) -> None:
        """Initialize ToolMode.

        Args:
            mode: The tool mode - "auto", "required", or "none".

        Keyword Args:
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
    """Common request settings for AI services.

    Examples:
        .. code-block:: python

            from agent_framework import ChatOptions, ai_function

            # Create basic chat options
            options = ChatOptions(
                model_id="gpt-4",
                temperature=0.7,
                max_tokens=1000,
            )


            # With tools
            @ai_function
            def get_weather(location: str) -> str:
                '''Get weather for a location.'''
                return f"Weather in {location}"


            options = ChatOptions(
                model_id="gpt-4",
                tools=get_weather,
                tool_choice="auto",
            )

            # Require a specific tool to be called
            options_required = ChatOptions(
                model_id="gpt-4",
                tools=get_weather,
                tool_choice=ToolMode.REQUIRED(function_name="get_weather"),
            )

            # Combine options
            base_options = ChatOptions(temperature=0.5)
            extended_options = ChatOptions(max_tokens=500, tools=get_weather)
            combined = base_options & extended_options
    """

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
        **kwargs: Any,
    ):
        """Initialize ChatOptions.

        Keyword Args:
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
            additional_properties: Provider-specific additional properties, can also be passed as kwargs.
            **kwargs: Additional properties to include in additional_properties.
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

        if additional_properties is None:
            additional_properties = {}
        if kwargs:
            additional_properties.update(kwargs)

        self.additional_properties = cast(dict[str, Any], additional_properties)
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
    ) -> ToolMode | None:
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
                    raise ContentError(f"Invalid tool choice: {tool_choice}")
        if isinstance(tool_choice, (dict, Mapping)):
            return ToolMode.from_dict(tool_choice)  # type: ignore
        return tool_choice

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
        combined.response_format = response_format

        # Apply scalar and mapping updates from the other options
        updated_data = other.to_dict(exclude_none=True, exclude={"tools"})
        logit_bias = updated_data.pop("logit_bias", {})
        metadata = updated_data.pop("metadata", {})
        additional_properties: dict[str, Any] = updated_data.pop("additional_properties", {})

        for key, value in updated_data.items():
            setattr(combined, key, value)

        combined.tool_choice = tool_choice
        # Preserve response_format from other if it exists, otherwise keep self's
        if other.response_format is not None:
            combined.response_format = other.response_format
        if other.instructions:
            combined.instructions = "\n".join([combined.instructions or "", other.instructions or ""])

        combined.logit_bias = (
            {**(combined.logit_bias or {}), **logit_bias} if logit_bias or combined.logit_bias else None
        )
        combined.metadata = {**(combined.metadata or {}), **metadata} if metadata or combined.metadata else None
        if combined.additional_properties and additional_properties:
            combined.additional_properties.update(additional_properties)
        else:
            if additional_properties:
                combined.additional_properties = additional_properties
        if other_tools:
            if combined.tools is None:
                combined.tools = list(other_tools)
            else:
                for tool in other_tools:
                    if tool not in combined.tools:
                        combined.tools.append(tool)
        return combined
