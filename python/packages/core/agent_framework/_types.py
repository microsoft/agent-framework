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
from typing import TYPE_CHECKING, Any, ClassVar, Final, Generic, Literal, cast, overload

from pydantic import BaseModel, ValidationError

from ._logging import get_logger
from ._serialization import SerializationMixin
from ._tools import ToolProtocol, tool
from .exceptions import AdditionItemMismatch, ContentError

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

__all__ = [
    "AgentResponse",
    "AgentResponseUpdate",
    "Annotation",
    "ChatMessage",
    "ChatOptions",
    "ChatResponse",
    "ChatResponseUpdate",
    "Content",
    "FinishReason",
    "Role",
    "TextSpanRegion",
    "ToolMode",
    "UsageDetails",
    "add_usage_details",
    "detect_media_type_from_base64",
    "merge_chat_options",
    "normalize_messages",
    "normalize_tools",
    "prepare_function_call_results",
    "prepend_instructions_to_messages",
    "validate_chat_options",
    "validate_tool_mode",
    "validate_tools",
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


def _parse_content_list(contents_data: Sequence[Any]) -> list["Content"]:
    """Parse a list of content data dictionaries into appropriate Content objects.

    Args:
        contents_data: List of content data (dicts or already constructed objects)

    Returns:
        List of Content objects with unknown types logged and ignored
    """
    contents: list["Content"] = []
    for content_data in contents_data:
        if isinstance(content_data, Content):
            contents.append(content_data)
            continue
        try:
            contents.append(Content.from_dict(content_data))
        except ContentError as exc:
            logger.warning(f"Skipping unknown content type or invalid content: {exc}")

    return contents


# region Internal Helper functions for unified Content


def detect_media_type_from_base64(
    *,
    data_bytes: bytes | None = None,
    data_str: str | None = None,
    data_uri: str | None = None,
) -> str | None:
    """Detect media type from base64-encoded data by examining magic bytes.

    This function examines the binary signature (magic bytes) at the start of the data
    to identify common media types. It's reliable for binary formats like images, audio,
    video, and documents, but cannot detect text-based formats like JSON or plain text.

    Args:
        data_bytes: Raw binary data.
        data_str: Base64-encoded data (without data URI prefix).
        data_uri: Full data URI string (e.g., "data:image/png;base64,iVBORw0KGgo...").
            This will look at the actual data to determine the media_type and not at the URI prefix.
            Will also not compare those two values.

    Raises:
        ValueError: If not exactly 1 of data_bytes, data_str, or data_uri is provided, or if base64 decoding fails.

    Returns:
        The detected media type (e.g., 'image/png', 'audio/wav', 'application/pdf')
        or None if the format is not recognized.

    Examples:
        .. code-block:: python

            from agent_framework import detect_media_type_from_base64

            # Detect from base64 string
            base64_data = "iVBORw0KGgo..."
            media_type = detect_media_type_from_base64(base64_data)
            # Returns: "image/png"

            # Works with data URIs too
            data_uri = "data:image/png;base64,iVBORw0KGgo..."
            media_type = detect_media_type_from_base64(data_uri)
            # Returns: "image/png"
    """
    data: bytes | None = None
    if data_bytes is not None:
        data = data_bytes
    if data_uri is not None:
        if data is not None:
            raise ValueError("Provide exactly one of data_bytes, data_str, or data_uri.")
        # Remove data URI prefix if present
        data_str = data_uri.split(";base64,", 1)[1]
    if data_str is not None:
        if data is not None:
            raise ValueError("Provide exactly one of data_bytes, data_str, or data_uri.")
        try:
            data = base64.b64decode(data_str)
        except Exception as exc:
            raise ValueError("Invalid base64 data provided.") from exc
    if data is None:
        raise ValueError("Provide exactly one of data_bytes, data_str, or data_uri.")

    # Check magic bytes for common formats
    # Images
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and len(data) > 11 and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"<svg") or data.startswith(b"<?xml"):
        return "image/svg+xml"

    # Documents
    if data.startswith(b"%PDF-"):
        return "application/pdf"

    # Audio
    if data.startswith(b"RIFF") and len(data) > 11 and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"ID3") or data.startswith(b"\xff\xfb") or data.startswith(b"\xff\xf3"):
        return "audio/mpeg"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"fLaC"):
        return "audio/flac"

    return None


def _get_data_bytes_as_str(content: "Content") -> str | None:
    """Extract base64 data string from data URI.

    Args:
        content: The Content instance to extract data from.

    Returns:
        The base64-encoded data as a string, or None if not a data content type.

    Raises:
        ContentError: If the URI is not a valid data URI.
    """
    if content.type not in ("data", "uri"):
        return None

    uri = getattr(content, "uri", None)
    if not uri:
        return None

    if not uri.startswith("data:"):
        return None

    if ";base64," not in uri:
        raise ContentError("Data URI must use base64 encoding")

    _, data = uri.split(";base64,", 1)
    return data  # type: ignore[return-value, no-any-return]


def _get_data_bytes(content: "Content") -> bytes | None:
    """Extract and decode binary data from data URI.

    Args:
        content: The Content instance to extract data from.

    Returns:
        The decoded binary data, or None if not a data content type.

    Raises:
        ContentError: If the URI is not a valid data URI or decoding fails.
    """
    data_str = _get_data_bytes_as_str(content)
    if data_str is None:
        return None

    try:
        return base64.b64decode(data_str)
    except Exception as e:
        raise ContentError(f"Failed to decode base64 data: {e}") from e


KNOWN_URI_SCHEMAS: Final[set[str]] = {"http", "https", "ftp", "ftps", "file", "s3", "gs", "azure", "blob"}


def _validate_uri(uri: str, media_type: str | None) -> dict[str, Any]:
    """Validate URI format and return validation result.

    Args:
        uri: The URI to validate.
        media_type: Optional media type associated with the URI.

    Returns:
        If valid, returns a dict, with "type" key indicating "data" or "uri", along with the uri and media_type.
    """
    if not uri:
        raise ContentError("URI cannot be empty")

    # Check for data URI
    if uri.startswith("data:"):
        if "," not in uri:
            raise ContentError("Data URI must contain a comma separating metadata and data")
        prefix, _ = uri.split(",", 1)
        if ";" in prefix:
            parts = prefix.split(";")
            if len(parts) < 2:
                raise ContentError("Invalid data URI format")
            # Check encoding
            encoding = parts[-1]
            if encoding not in ("base64", ""):
                raise ContentError(f"Unsupported data URI encoding: {encoding}")
            if media_type is None:
                # attempt to extract:
                media_type = parts[0][5:]  # Remove 'data:'
        return {"type": "data", "uri": uri, "media_type": media_type}

    # Check for common URI schemes
    if ":" in uri:
        scheme = uri.split(":", 1)[0].lower()
        if not media_type:
            logger.warning("Using URI without media type is not recommended.")
        if scheme not in KNOWN_URI_SCHEMAS:
            logger.info(f"Unknown URI scheme: {scheme}, allowed schemes are {KNOWN_URI_SCHEMAS}.")
        return {"type": "uri", "uri": uri, "media_type": media_type}

    # No scheme found
    raise ContentError("URI must contain a scheme (e.g., http://, data:, file://)")


def _serialize_value(value: Any, exclude_none: bool) -> Any:
    """Recursively serialize a value for to_dict."""
    if value is None:
        return None
    if isinstance(value, Content):
        return value.to_dict(exclude_none=exclude_none)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_serialize_value(item, exclude_none) for item in value]
    if isinstance(value, Mapping):
        return {k: _serialize_value(v, exclude_none) for k, v in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()  # type: ignore[call-arg]
    return value


# endregion

# region Constants and types
_T = TypeVar("_T")
TEmbedding = TypeVar("TEmbedding")
TChatResponse = TypeVar("TChatResponse", bound="ChatResponse")
TToolMode = TypeVar("TToolMode", bound="ToolMode")
TAgentRunResponse = TypeVar("TAgentRunResponse", bound="AgentResponse")
TResponseModel = TypeVar("TResponseModel", bound=BaseModel | None, default=None, covariant=True)
TResponseModelT = TypeVar("TResponseModelT", bound=BaseModel)

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

# region Unified Content Types

ContentType = Literal[
    "text",
    "text_reasoning",
    "data",
    "uri",
    "error",
    "function_call",
    "function_result",
    "usage",
    "hosted_file",
    "hosted_vector_store",
    "code_interpreter_tool_call",
    "code_interpreter_tool_result",
    "image_generation_tool_call",
    "image_generation_tool_result",
    "mcp_server_tool_call",
    "mcp_server_tool_result",
    "function_approval_request",
    "function_approval_response",
]


class TextSpanRegion(TypedDict, total=False):
    """TypedDict representation of a text span region annotation."""

    type: Literal["text_span"]
    start_index: int
    end_index: int


class Annotation(TypedDict, total=False):
    """TypedDict representation of an annotation."""

    type: Literal["citation"]
    title: str
    url: str
    file_id: str
    tool_name: str
    snippet: str
    annotated_regions: Sequence[TextSpanRegion]
    additional_properties: dict[str, Any]
    raw_representation: Any


TContent = TypeVar("TContent", bound="Content")

# endregion


class UsageDetails(TypedDict, total=False):
    """A dictionary representing usage details.

    This is a non-closed dictionary, so any specific provider fields can be added as needed.
    Whenever they can be mapped to standard fields, they will be.
    """

    input_token_count: int | None
    output_token_count: int | None
    total_token_count: int | None


def add_usage_details(usage1: UsageDetails | None, usage2: UsageDetails | None) -> UsageDetails:
    """Add two UsageDetails dictionaries by summing all numeric values.

    Args:
        usage1: First usage details dictionary.
        usage2: Second usage details dictionary.

    Returns:
        A new UsageDetails dictionary with summed values.

    Examples:
        .. code-block:: python

            from agent_framework import UsageDetails, add_usage_details

            usage1 = UsageDetails(input_token_count=5, output_token_count=10)
            usage2 = UsageDetails(input_token_count=3, output_token_count=6)
            combined = add_usage_details(usage1, usage2)
            # Result: {'input_token_count': 8, 'output_token_count': 16}
    """
    if usage1 is None:
        return usage2 or UsageDetails()
    if usage2 is None:
        return usage1

    result = UsageDetails()

    # Combine all keys from both dictionaries
    all_keys = set(usage1.keys()) | set(usage2.keys())

    for key in all_keys:
        val1 = usage1.get(key)
        val2 = usage2.get(key)

        # Sum if both present, otherwise use the non-None value
        if val1 is not None and val2 is not None:
            result[key] = val1 + val2  # type: ignore[literal-required, operator]
        elif val1 is not None:
            result[key] = val1  # type: ignore[literal-required]
        elif val2 is not None:
            result[key] = val2  # type: ignore[literal-required]

    return result


# region Content Class


class Content:
    """Unified content container covering all content variants.

    This class provides a single unified type that handles all content variants.
    Use the class methods like `Content.from_text()`, `Content.from_data()`,
    `Content.from_uri()`, etc. to create instances.
    """

    def __init__(
        self,
        type: ContentType,
        *,
        # Text content fields
        text: str | None = None,
        protected_data: str | None = None,
        # Data/URI content fields
        uri: str | None = None,
        media_type: str | None = None,
        # Error content fields
        message: str | None = None,
        error_code: str | None = None,
        error_details: str | None = None,
        # Usage content fields
        usage_details: dict[str, Any] | UsageDetails | None = None,
        # Function call/result fields
        call_id: str | None = None,
        name: str | None = None,
        arguments: str | Mapping[str, Any] | None = None,
        exception: str | None = None,
        result: Any = None,
        # Hosted file/vector store fields
        file_id: str | None = None,
        vector_store_id: str | None = None,
        # Code interpreter tool fields
        inputs: list["Content"] | None = None,
        outputs: list["Content"] | Any | None = None,
        # Image generation tool fields
        image_id: str | None = None,
        # MCP server tool fields
        tool_name: str | None = None,
        server_name: str | None = None,
        output: Any = None,
        # Function approval fields
        id: str | None = None,
        function_call: "Content | None" = None,
        user_input_request: bool | None = None,
        approved: bool | None = None,
        # Common fields
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any | None = None,
    ) -> None:
        """Create a content instance.

        Prefer using the classmethod constructors like `Content.from_text()` instead of calling __init__ directly.
        """
        self.type = type
        self.annotations = annotations
        self.additional_properties: dict[str, Any] = additional_properties or {}  # type: ignore[assignment]
        self.raw_representation = raw_representation

        # Set all content-specific attributes
        self.text = text
        self.protected_data = protected_data
        self.uri = uri
        self.media_type = media_type
        self.message = message
        self.error_code = error_code
        self.error_details = error_details
        self.usage_details = usage_details
        self.call_id = call_id
        self.name = name
        self.arguments = arguments
        self.exception = exception
        self.result = result
        self.file_id = file_id
        self.vector_store_id = vector_store_id
        self.inputs = inputs
        self.outputs = outputs
        self.image_id = image_id
        self.tool_name = tool_name
        self.server_name = server_name
        self.output = output
        self.id = id
        self.function_call = function_call
        self.user_input_request = user_input_request
        self.approved = approved

    @classmethod
    def from_text(
        cls: type[TContent],
        text: str,
        *,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create text content."""
        return cls(
            "text",
            text=text,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_text_reasoning(
        cls: type[TContent],
        *,
        text: str | None = None,
        protected_data: str | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create text reasoning content."""
        return cls(
            "text_reasoning",
            text=text,
            protected_data=protected_data,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_data(
        cls: type[TContent],
        data: bytes,
        media_type: str,
        *,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        r"""Create data content from raw binary data.

        Use this to create content from binary data (images, audio, documents, etc.).
        The data will be automatically base64-encoded into a data URI.

        Args:
            data: Raw binary data as bytes. This should be the actual binary data,
                not a base64-encoded string. If you have a base64 string,
                decode it first: base64.b64decode(base64_string)
            media_type: The MIME type of the data (e.g., "image/png", "application/pdf").
                If you don't know the media type and have base64 data, you can detect it in some cases:

                .. code-block:: python

                    from agent_framework import detect_media_type_from_base64, Content

                    media_type = detect_media_type_from_base64(base64_string)
                    if media_type is None:
                        raise ValueError("Could not detect media type")
                    data_bytes = base64.b64decode(base64_string)
                    content = Content.from_data(data=data_bytes, media_type=media_type)

        Keyword Args:
            annotations: Optional annotations associated with the content.
            additional_properties: Optional additional properties.
            raw_representation: Optional raw representation from an underlying implementation.

        Returns:
            A Content instance with type="data".

        Raises:
            TypeError: If data is not bytes.

        Examples:
            .. code-block:: python

                from agent_framework import Content, detect_media_type_from_base64
                import base64

                # Create from raw binary data with known media type
                image_bytes = b"\x89PNG\r\n\x1a\n..."
                content = Content.from_data(data=image_bytes, media_type="image/png")

                # If you have a base64 string and need to detect media type
                base64_string = "iVBORw0KGgo..."
                media_type = detect_media_type_from_base64(base64_string)
                if media_type is None:
                    raise ValueError("Unknown media type")
                image_bytes = base64.b64decode(base64_string)
                content = Content.from_data(data=image_bytes, media_type=media_type)
        """
        try:
            encoded_data = base64.b64encode(data).decode("utf-8")
        except TypeError as e:
            raise TypeError(
                "Could not encode data to base64. Ensure 'data' is of type bytes.Or another b64encode compatible type."
            ) from e
        return cls(
            "data",
            uri=f"data:{media_type};base64,{encoded_data}",
            media_type=media_type,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_uri(
        cls: type[TContent],
        uri: str,
        *,
        media_type: str | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create content from a URI, can be both data URI or external URI.

        Use this when you already have a properly formed data URI
        (e.g., "data:image/png;base64,iVBORw0KGgo...").
        Or when you receive a link to a online resource (e.g., "https://example.com/image.png").

        Args:
            uri: A URI string,
                that either includes the media type and base64-encoded data,
                or a valid URL to an external resource.

        Keyword Args:
            media_type: The MIME type of the data (e.g., "image/png", "application/pdf").
                This is optional but recommended for external URIs.
            annotations: Optional annotations associated with the content.
            additional_properties: Optional additional properties.
            raw_representation: Optional raw representation from an underlying implementation.

        Raises:
            ContentError: If the URI is not valid.

        Examples:
            .. code-block:: python

                from agent_framework import Content

                # Create from a data URI
                content = Content.from_uri(uri="data:image/png;base64,iVBORw0KGgo...", media_type="image/png")
                assert content.type == "data"

                # Create from an external URI
                content = Content.from_uri(uri="https://example.com/image.png", media_type="image/png")
                assert content.type == "uri"

                # When receiving a raw already encode data string, you can do this:
                raw_base64_string = "iVBORw0KGgo..."
                content = Content.from_uri(
                    uri=f"data:{(detect_media_type_from_base64(data_str=raw_base64_string) or 'image/png')};base64,{
                        raw_base64_string
                    }"
                )

        Returns:
            A Content instance with type="data" for data URIs or type="uri" for external URIs.
        """
        return cls(
            **_validate_uri(uri, media_type),
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_error(
        cls: type[TContent],
        *,
        message: str | None = None,
        error_code: str | None = None,
        error_details: str | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create error content."""
        return cls(
            "error",
            message=message,
            error_code=error_code,
            error_details=error_details,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_function_call(
        cls: type[TContent],
        call_id: str,
        name: str,
        *,
        arguments: str | Mapping[str, Any] | None = None,
        exception: str | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create function call content."""
        return cls(
            "function_call",
            call_id=call_id,
            name=name,
            arguments=arguments,
            exception=exception,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_function_result(
        cls: type[TContent],
        call_id: str,
        *,
        result: Any = None,
        exception: str | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create function result content."""
        return cls(
            "function_result",
            call_id=call_id,
            result=result,
            exception=exception,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_usage(
        cls: type[TContent],
        usage_details: UsageDetails,
        *,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create usage content."""
        return cls(
            "usage",
            usage_details=usage_details,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_hosted_file(
        cls: type[TContent],
        file_id: str,
        *,
        media_type: str | None = None,
        name: str | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create hosted file content."""
        return cls(
            "hosted_file",
            file_id=file_id,
            media_type=media_type,
            name=name,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_hosted_vector_store(
        cls: type[TContent],
        vector_store_id: str,
        *,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create hosted vector store content."""
        return cls(
            "hosted_vector_store",
            vector_store_id=vector_store_id,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_code_interpreter_tool_call(
        cls: type[TContent],
        *,
        call_id: str | None = None,
        inputs: Sequence["Content"] | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create code interpreter tool call content."""
        return cls(
            "code_interpreter_tool_call",
            call_id=call_id,
            inputs=list(inputs) if inputs is not None else None,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_code_interpreter_tool_result(
        cls: type[TContent],
        *,
        call_id: str | None = None,
        outputs: Sequence["Content"] | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create code interpreter tool result content."""
        return cls(
            "code_interpreter_tool_result",
            call_id=call_id,
            outputs=list(outputs) if outputs is not None else None,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_image_generation_tool_call(
        cls: type[TContent],
        *,
        image_id: str | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create image generation tool call content."""
        return cls(
            "image_generation_tool_call",
            image_id=image_id,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_image_generation_tool_result(
        cls: type[TContent],
        *,
        image_id: str | None = None,
        outputs: Any = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create image generation tool result content."""
        return cls(
            "image_generation_tool_result",
            image_id=image_id,
            outputs=outputs,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_mcp_server_tool_call(
        cls: type[TContent],
        call_id: str,
        tool_name: str,
        *,
        server_name: str | None = None,
        arguments: str | Mapping[str, Any] | None = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create MCP server tool call content."""
        return cls(
            "mcp_server_tool_call",
            call_id=call_id,
            tool_name=tool_name,
            server_name=server_name,
            arguments=arguments,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_mcp_server_tool_result(
        cls: type[TContent],
        call_id: str,
        *,
        output: Any = None,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create MCP server tool result content."""
        return cls(
            "mcp_server_tool_result",
            call_id=call_id,
            output=output,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_function_approval_request(
        cls: type[TContent],
        id: str,
        function_call: "Content",
        *,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create function approval request content."""
        return cls(
            "function_approval_request",
            id=id,
            function_call=function_call,
            user_input_request=True,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    @classmethod
    def from_function_approval_response(
        cls: type[TContent],
        approved: bool,
        id: str,
        function_call: "Content",
        *,
        annotations: Sequence[Annotation] | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any = None,
    ) -> TContent:
        """Create function approval response content."""
        return cls(
            "function_approval_response",
            approved=approved,
            id=id,
            function_call=function_call,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
        )

    def to_function_approval_response(
        self,
        approved: bool,
    ) -> "Content":
        """Convert a function approval request content to a function approval response content."""
        if self.type != "function_approval_request":
            raise ContentError(
                "Can only convert 'function_approval_request' content to 'function_approval_response' content."
            )
        return Content.from_function_approval_response(
            approved=approved,
            id=self.id,  # type: ignore[attr-defined, arg-type]
            function_call=self.function_call,  # type: ignore[attr-defined, arg-type]
            annotations=self.annotations,
            additional_properties=self.additional_properties,
            raw_representation=self.raw_representation,
        )

    def to_dict(self, *, exclude_none: bool = True, exclude: set[str] | None = None) -> dict[str, Any]:
        """Serialize the content to a dictionary."""
        fields_to_capture = (
            "text",
            "protected_data",
            "uri",
            "media_type",
            "message",
            "error_code",
            "error_details",
            "usage_details",
            "call_id",
            "name",
            "arguments",
            "exception",
            "result",
            "file_id",
            "vector_store_id",
            "inputs",
            "outputs",
            "image_id",
            "tool_name",
            "server_name",
            "output",
            "function_call",
            "user_input_request",
            "approved",
            "id",
            "additional_properties",
        )

        exclude = exclude or set()
        result: dict[str, Any] = {"type": self.type}

        for field in fields_to_capture:
            value = getattr(self, field, None)
            if field in exclude:
                continue
            if exclude_none and value is None:
                continue
            result[field] = _serialize_value(value, exclude_none)

        if "annotations" not in exclude and self.annotations is not None:
            result["annotations"] = [dict(annotation) for annotation in self.annotations]

        return result

    def __eq__(self, other: object) -> bool:
        """Check if two Content instances are equal by comparing their dict representations."""
        if not isinstance(other, Content):
            return False
        return self.to_dict(exclude_none=False) == other.to_dict(exclude_none=False)

    def __str__(self) -> str:
        """Return a string representation of the Content."""
        if self.type == "error":
            if self.error_code:
                return f"Error {self.error_code}: {self.message or ''}"
            return self.message or "Unknown error"
        if self.type == "text":
            return self.text or ""
        return f"Content(type={self.type})"

    @classmethod
    def from_dict(cls: type[TContent], data: Mapping[str, Any]) -> TContent:
        """Create a Content instance from a mapping."""
        if not (content_type := data.get("type")):
            raise ValueError("Content mapping requires 'type'")
        remaining = dict(data)
        remaining.pop("type", None)
        annotations = remaining.pop("annotations", None)
        additional_properties = remaining.pop("additional_properties", None)
        raw_representation = remaining.pop("raw_representation", None)

        # Special handling for DataContent with data and media_type
        if content_type == "data" and "data" in remaining and "media_type" in remaining:
            # Use from_data() to properly create the DataContent with URI
            return cls.from_data(remaining["data"], remaining["media_type"])

        # Handle nested Content objects (e.g., function_call in function_approval_request)
        if "function_call" in remaining and isinstance(remaining["function_call"], dict):
            remaining["function_call"] = cls.from_dict(remaining["function_call"])

        # Handle list of Content objects (e.g., inputs in code_interpreter_tool_call)
        if "inputs" in remaining and isinstance(remaining["inputs"], list):
            remaining["inputs"] = [
                cls.from_dict(item) if isinstance(item, dict) else item for item in remaining["inputs"]
            ]

        if "outputs" in remaining and isinstance(remaining["outputs"], list):
            remaining["outputs"] = [
                cls.from_dict(item) if isinstance(item, dict) else item for item in remaining["outputs"]
            ]

        return cls(
            type=content_type,
            annotations=annotations,
            additional_properties=additional_properties,
            raw_representation=raw_representation,
            **remaining,
        )

    def __add__(self, other: "Content") -> "Content":
        """Concatenate or merge two Content instances."""
        if not isinstance(other, Content):
            raise TypeError(f"Incompatible type: Cannot add Content with {type(other).__name__}")

        if self.type != other.type:
            raise TypeError(f"Cannot add Content of type '{self.type}' with type '{other.type}'")

        if self.type == "text":
            return self._add_text_content(other)
        if self.type == "text_reasoning":
            return self._add_text_reasoning_content(other)
        if self.type == "function_call":
            return self._add_function_call_content(other)
        if self.type == "usage":
            return self._add_usage_content(other)
        raise ContentError(f"Addition not supported for content type: {self.type}")

    def _add_text_content(self, other: "Content") -> "Content":
        """Add two TextContent instances."""
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
            annotations = self.annotations + other.annotations  # type: ignore[operator]

        return Content(
            "text",
            text=self.text + other.text,  # type: ignore[attr-defined, operator]
            annotations=annotations,
            additional_properties={
                **(other.additional_properties or {}),
                **(self.additional_properties or {}),
            },
            raw_representation=raw_representation,
        )

    def _add_text_reasoning_content(self, other: "Content") -> "Content":
        """Add two TextReasoningContent instances."""
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
            annotations = self.annotations + other.annotations  # type: ignore[operator]

        # Concatenate text, handling None values
        self_text = self.text or ""  # type: ignore[attr-defined]
        other_text = other.text or ""  # type: ignore[attr-defined]
        combined_text = self_text + other_text if (self_text or other_text) else None

        # Handle protected_data replacement
        protected_data = other.protected_data if other.protected_data is not None else self.protected_data  # type: ignore[attr-defined]

        return Content(
            "text_reasoning",
            text=combined_text,
            protected_data=protected_data,
            annotations=annotations,
            additional_properties={
                **(other.additional_properties or {}),
                **(self.additional_properties or {}),
            },
            raw_representation=raw_representation,
        )

    def _add_function_call_content(self, other: "Content") -> "Content":
        """Add two FunctionCallContent instances."""
        other_call_id = getattr(other, "call_id", None)
        self_call_id = getattr(self, "call_id", None)
        if other_call_id and self_call_id != other_call_id:
            raise ContentError("Cannot add function calls with different call_ids")

        self_arguments = getattr(self, "arguments", None)
        other_arguments = getattr(other, "arguments", None)

        if not self_arguments:
            arguments: str | Mapping[str, Any] | None = other_arguments
        elif not other_arguments:
            arguments = self_arguments
        elif isinstance(self_arguments, str) and isinstance(other_arguments, str):
            arguments = self_arguments + other_arguments
        elif isinstance(self_arguments, dict) and isinstance(other_arguments, dict):
            arguments = {**self_arguments, **other_arguments}
        else:
            raise TypeError("Incompatible argument types")

        # Merge raw representations
        if self.raw_representation is None:
            raw_representation: Any = other.raw_representation
        elif other.raw_representation is None:
            raw_representation = self.raw_representation
        else:
            raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])

        return Content(
            "function_call",
            call_id=self_call_id,
            name=getattr(self, "name", getattr(other, "name", None)),
            arguments=arguments,
            exception=getattr(self, "exception", None) or getattr(other, "exception", None),
            additional_properties={
                **(self.additional_properties or {}),
                **(other.additional_properties or {}),
            },
            raw_representation=raw_representation,
        )

    def _add_usage_content(self, other: "Content") -> "Content":
        """Add two UsageContent instances by combining their usage details."""
        self_details = getattr(self, "usage_details", {})
        other_details = getattr(other, "usage_details", {})

        # Combine token counts
        combined_details: dict[str, Any] = {}
        for key in set(list(self_details.keys()) + list(other_details.keys())):
            self_val = self_details.get(key)
            other_val = other_details.get(key)
            if isinstance(self_val, int) and isinstance(other_val, int):
                combined_details[key] = self_val + other_val
            elif self_val is not None:
                combined_details[key] = self_val
            elif other_val is not None:
                combined_details[key] = other_val

        # Merge raw representations
        if self.raw_representation is None:
            raw_representation = other.raw_representation
        elif other.raw_representation is None:
            raw_representation = self.raw_representation
        else:
            raw_representation = (
                self.raw_representation if isinstance(self.raw_representation, list) else [self.raw_representation]
            ) + (other.raw_representation if isinstance(other.raw_representation, list) else [other.raw_representation])

        return Content(
            "usage",
            usage_details=combined_details,
            additional_properties={
                **(self.additional_properties or {}),
                **(other.additional_properties or {}),
            },
            raw_representation=raw_representation,
        )

    def has_top_level_media_type(self, top_level_media_type: Literal["application", "audio", "image", "text"]) -> bool:
        """Check if content has a specific top-level media type.

        Works with data, uri, and hosted_file content types.

        Args:
            top_level_media_type: The top-level media type to check for.

        Returns:
            True if the content's media type matches the specified top-level type.

        Raises:
            ContentError: If the content type doesn't support media types.

        Examples:
            .. code-block:: python

                from agent_framework import Content

                image = Content.from_uri(uri="data:image/png;base64,abc123", media_type="image/png")
                print(image.has_top_level_media_type("image"))  # True
                print(image.has_top_level_media_type("audio"))  # False
        """
        if self.media_type is None:
            raise ContentError("no media_type found")

        slash_index = self.media_type.find("/")
        span = self.media_type[:slash_index] if slash_index >= 0 else self.media_type
        span = span.strip()
        return span.lower() == top_level_media_type.lower()

    def parse_arguments(self) -> dict[str, Any | None] | None:
        """Parse arguments from function_call or mcp_server_tool_call content.

        If arguments cannot be parsed as JSON or the result is not a dict,
        they are returned as a dictionary with a single key "raw".

        Returns:
            Parsed arguments as a dictionary, or None if no arguments.

        Raises:
            ContentError: If the content type doesn't support arguments.

        Examples:
            .. code-block:: python

                from agent_framework import Content

                func_call = Content.from_function_call(
                    call_id="call_123",
                    name="send_email",
                    arguments='{"to": "user@example.com"}',
                )
                args = func_call.parse_arguments()
                print(args)  # {"to": "user@example.com"}
        """
        if self.arguments is None:
            return None

        if not self.arguments:
            return {}

        if isinstance(self.arguments, str):
            # If arguments are a string, try to parse it as JSON
            try:
                loaded = json.loads(self.arguments)
                if isinstance(loaded, dict):
                    return loaded  # type: ignore[return-value]
                return {"raw": loaded}
            except (json.JSONDecodeError, TypeError):
                return {"raw": self.arguments}
        return self.arguments  # type: ignore[return-value]


# endregion


def _prepare_function_call_results_as_dumpable(content: "Content | Any | list[Content | Any]") -> Any:
    if isinstance(content, list):
        # Particularly deal with lists of Content
        return [_prepare_function_call_results_as_dumpable(item) for item in content]
    if isinstance(content, dict):
        return {k: _prepare_function_call_results_as_dumpable(v) for k, v in content.items()}
    if isinstance(content, BaseModel):
        return content.model_dump()
    if hasattr(content, "to_dict"):
        return content.to_dict(exclude={"raw_representation", "additional_properties"})
    # Handle objects with text attribute (e.g., MCP TextContent)
    if hasattr(content, "text") and isinstance(content.text, str):
        return content.text
    return content


def prepare_function_call_results(content: "Content | Any | list[Content | Any]") -> str:
    """Prepare the values of the function call results."""
    if isinstance(content, Content):
        # For BaseContent objects, use to_dict and serialize to JSON
        # Use default=str to handle datetime and other non-JSON-serializable objects
        return json.dumps(content.to_dict(exclude={"raw_representation", "additional_properties"}), default=str)

    dumpable = _prepare_function_call_results_as_dumpable(content)
    if isinstance(dumpable, str):
        return dumpable
    # fallback - use default=str to handle datetime and other non-JSON-serializable objects
    return json.dumps(dumpable, default=str)


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
            Additional properties are used within Agent Framework, they are not sent to services.
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
                contents=[Content.from_text(text="The weather is sunny!")],
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
                Additional properties are used within Agent Framework, they are not sent to services.
            raw_representation: Optional raw representation of the chat message.
            **kwargs: Additional keyword arguments.
        """

    @overload
    def __init__(
        self,
        role: Role | Literal["system", "user", "assistant", "tool"],
        *,
        contents: "Sequence[Content | Mapping[str, Any]]",
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
                Additional properties are used within Agent Framework, they are not sent to services.
            raw_representation: Optional raw representation of the chat message.
            **kwargs: Additional keyword arguments.
        """

    def __init__(
        self,
        role: Role | Literal["system", "user", "assistant", "tool"] | dict[str, Any],
        *,
        text: str | None = None,
        contents: "Sequence[Content | Mapping[str, Any]] | None" = None,
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
                Additional properties are used within Agent Framework, they are not sent to services.
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
            parsed_contents.append(Content.from_text(text=text))

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
            This property concatenates the text of all TextContent objects in Content.
        """
        return " ".join(content.text for content in self.contents if content.type == "text")  # type: ignore[misc]


def prepare_messages(
    messages: str | ChatMessage | Sequence[str | ChatMessage], system_instructions: str | Sequence[str] | None = None
) -> list[ChatMessage]:
    """Convert various message input formats into a list of ChatMessage objects.

    Args:
        messages: The input messages in various supported formats.
        system_instructions: The system instructions. They will be inserted to the start of the messages list.

    Returns:
        A list of ChatMessage objects.
    """
    if system_instructions is not None:
        if isinstance(system_instructions, str):
            system_instructions = [system_instructions]
        system_instruction_messages = [ChatMessage(role="system", text=instr) for instr in system_instructions]
    else:
        system_instruction_messages = []

    if isinstance(messages, str):
        return [*system_instruction_messages, ChatMessage(role="user", text=messages)]
    if isinstance(messages, ChatMessage):
        return [*system_instruction_messages, messages]

    return_messages: list[ChatMessage] = system_instruction_messages
    for msg in messages:
        if isinstance(msg, str):
            msg = ChatMessage(role="user", text=msg)
        return_messages.append(msg)
    return return_messages


def normalize_messages(
    messages: str | ChatMessage | Sequence[str | ChatMessage] | None = None,
) -> list[ChatMessage]:
    """Normalize message inputs to a list of ChatMessage objects."""
    if messages is None:
        return []

    if isinstance(messages, str):
        return [ChatMessage(role=Role.USER, text=messages)]

    if isinstance(messages, ChatMessage):
        return [messages]

    return [ChatMessage(role=Role.USER, text=msg) if isinstance(msg, str) else msg for msg in messages]


def prepend_instructions_to_messages(
    messages: list[ChatMessage],
    instructions: str | Sequence[str] | None,
    role: Role | Literal["system", "user", "assistant"] = "system",
) -> list[ChatMessage]:
    """Prepend instructions to a list of messages with a specified role.

    This is a helper method for chat clients that need to add instructions
    from options as messages. Different providers support different roles for
    instructions (e.g., OpenAI uses "system", some providers might use "user").

    Args:
        messages: The existing list of ChatMessage objects.
        instructions: The instructions to prepend. Can be a single string or a sequence of strings.
        role: The role to use for the instruction messages. Defaults to "system".

    Returns:
        A new list with instruction messages prepended.

    Examples:
        .. code-block:: python

            from agent_framework import prepend_instructions_to_messages, ChatMessage

            messages = [ChatMessage(role="user", text="Hello")]
            instructions = "You are a helpful assistant"

            # Prepend as system message (default)
            messages_with_instructions = prepend_instructions_to_messages(messages, instructions)

            # Or use a different role
            messages_with_user_instructions = prepend_instructions_to_messages(messages, instructions, role="user")
    """
    if instructions is None:
        return messages

    if isinstance(instructions, str):
        instructions = [instructions]

    instruction_messages = [ChatMessage(role=role, text=instr) for instr in instructions]
    return [*instruction_messages, *messages]


# region ChatResponse


def _process_update(
    response: "ChatResponse | AgentResponse", update: "ChatResponseUpdate | AgentResponseUpdate"
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
        # Fast path: get type attribute (most content will have it)
        content_type = getattr(content, "type", None)
        # Slow path: only check for dict if type is None
        if content_type is None and isinstance(content, (dict, MutableMapping)):
            try:
                content = Content.from_dict(content)
                content_type = content.type
            except ContentError as exc:
                logger.warning(f"Skipping unknown content type or invalid content: {exc}")
                continue
        match content_type:
            # mypy doesn't narrow type based on match/case, but we know these are FunctionCallContents
            case "function_call" if message.contents and message.contents[-1].type == "function_call":
                try:
                    message.contents[-1] += content  # type: ignore[operator]
                except (AdditionItemMismatch, ContentError):
                    message.contents.append(content)
            case "usage":
                if response.usage_details is None:
                    response.usage_details = UsageDetails()
                # mypy doesn't narrow type based on match/case, but we know this is UsageContent
                response.usage_details = add_usage_details(response.usage_details, content.usage_details)  # type: ignore[arg-type]
            case _:
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


def _coalesce_text_content(contents: list["Content"], type_str: Literal["text", "text_reasoning"]) -> None:
    """Take any subsequence Text or TextReasoningContent items and coalesce them into a single item."""
    if not contents:
        return
    coalesced_contents: list["Content"] = []
    first_new_content: Any | None = None
    for content in contents:
        if content.type == type_str:
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


def _finalize_response(response: "ChatResponse | AgentResponse") -> None:
    """Finalizes the response by performing any necessary post-processing."""
    for msg in response.messages:
        _coalesce_text_content(msg.contents, "text")
        _coalesce_text_content(msg.contents, "text_reasoning")


class ChatResponse(SerializationMixin, Generic[TResponseModel]):
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
        value: TResponseModel | None = None,
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
        text: Content | str,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: FinishReason | None = None,
        usage_details: UsageDetails | None = None,
        value: TResponseModel | None = None,
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
        text: Content | str | None = None,
        response_id: str | None = None,
        conversation_id: str | None = None,
        model_id: str | None = None,
        created_at: CreatedAtT | None = None,
        finish_reason: FinishReason | dict[str, Any] | None = None,
        usage_details: UsageDetails | dict[str, Any] | None = None,
        value: TResponseModel | None = None,
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
                text = Content.from_text(text=text)
            messages.append(ChatMessage(role=Role.ASSISTANT, contents=[text]))

        # Handle finish_reason conversion
        if isinstance(finish_reason, dict):
            finish_reason = FinishReason.from_dict(finish_reason)

        # Handle usage_details - UsageDetails is now a TypedDict, so dict is already the right type
        # No conversion needed

        self.messages = list(messages)
        self.response_id = response_id
        self.conversation_id = conversation_id
        self.model_id = model_id
        self.created_at = created_at
        self.finish_reason = finish_reason
        self.usage_details = usage_details
        self._value: TResponseModel | None = value
        self._response_format: type[BaseModel] | None = response_format
        self._value_parsed: bool = value is not None
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs or {})
        self.raw_representation: Any | list[Any] | None = raw_representation

    @overload
    @classmethod
    def from_chat_response_updates(
        cls: type["ChatResponse[Any]"],
        updates: Sequence["ChatResponseUpdate"],
        *,
        output_format_type: type[TResponseModelT],
    ) -> "ChatResponse[TResponseModelT]": ...

    @overload
    @classmethod
    def from_chat_response_updates(
        cls: type["ChatResponse[Any]"],
        updates: Sequence["ChatResponseUpdate"],
        *,
        output_format_type: None = None,
    ) -> "ChatResponse[Any]": ...

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

    @overload
    @classmethod
    async def from_chat_response_generator(
        cls: type["ChatResponse[Any]"],
        updates: AsyncIterable["ChatResponseUpdate"],
        *,
        output_format_type: type[TResponseModelT],
    ) -> "ChatResponse[TResponseModelT]": ...

    @overload
    @classmethod
    async def from_chat_response_generator(
        cls: type["ChatResponse[Any]"],
        updates: AsyncIterable["ChatResponseUpdate"],
        *,
        output_format_type: None = None,
    ) -> "ChatResponse[Any]": ...

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
        response_format = output_format_type if isinstance(output_format_type, type) else None
        msg = cls(messages=[], response_format=response_format)
        async for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        if response_format and issubclass(response_format, BaseModel):
            msg.try_parse_value(response_format)
        return msg

    @property
    def text(self) -> str:
        """Returns the concatenated text of all messages in the response."""
        return ("\n".join(message.text for message in self.messages if isinstance(message, ChatMessage))).strip()

    @property
    def value(self) -> TResponseModel | None:
        """Get the parsed structured output value.

        If a response_format was provided and parsing hasn't been attempted yet,
        this will attempt to parse the text into the specified type.

        Raises:
            ValidationError: If the response text doesn't match the expected schema.
        """
        if self._value_parsed:
            return self._value
        if (
            self._response_format is not None
            and isinstance(self._response_format, type)
            and issubclass(self._response_format, BaseModel)
        ):
            self._value = cast(TResponseModel, self._response_format.model_validate_json(self.text))
            self._value_parsed = True
        return self._value

    def __str__(self) -> str:
        return self.text

    @overload
    def try_parse_value(self, output_format_type: type[TResponseModelT]) -> TResponseModelT | None: ...

    @overload
    def try_parse_value(self, output_format_type: None = None) -> TResponseModel | None: ...

    def try_parse_value(self, output_format_type: type[BaseModel] | None = None) -> BaseModel | None:
        """Try to parse the text into a typed value.

        This is the safe alternative to accessing the value property directly.
        Returns the parsed value on success, or None on failure.

        Args:
            output_format_type: The Pydantic model type to parse into.
                               If None, uses the response_format from initialization.

        Returns:
            The parsed value as the specified type, or None if parsing fails.
        """
        format_type = output_format_type or self._response_format
        if format_type is None or not (isinstance(format_type, type) and issubclass(format_type, BaseModel)):
            return None

        # Cache the result unless a different schema than the configured response_format is requested.
        # This prevents calls with a different schema from polluting the cached value.
        use_cache = (
            self._response_format is None or output_format_type is None or output_format_type is self._response_format
        )

        if use_cache and self._value_parsed and self._value is not None:
            return self._value  # type: ignore[return-value, no-any-return]
        try:
            parsed_value = format_type.model_validate_json(self.text)  # type: ignore[reportUnknownMemberType]
            if use_cache:
                self._value = cast(TResponseModel, parsed_value)
                self._value_parsed = True
            return parsed_value  # type: ignore[return-value]
        except ValidationError as ex:
            logger.warning("Failed to parse value from chat response text: %s", ex)
            return None


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
                contents=[Content.from_text(text="Hello")],
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
        contents: Sequence[Content | dict[str, Any]] | None = None,
        text: Content | str | None = None,
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
                text = Content.from_text(text=text)
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
        return "".join(content.text for content in self.contents if content.type == "text")  # type: ignore[misc]

    def __str__(self) -> str:
        return self.text


# region AgentResponse


class AgentResponse(SerializationMixin, Generic[TResponseModel]):
    """Represents the response to an Agent run request.

    Provides one or more response messages and metadata about the response.
    A typical response will contain a single message, but may contain multiple
    messages in scenarios involving function calls, RAG retrievals, or complex logic.

    Examples:
        .. code-block:: python

            from agent_framework import AgentResponse, ChatMessage

            # Create agent response
            msg = ChatMessage(role="assistant", text="Task completed successfully.")
            response = AgentResponse(messages=[msg], response_id="run_123")
            print(response.text)  # "Task completed successfully."

            # Access user input requests
            user_requests = response.user_input_requests
            print(len(user_requests))  # 0

            # Combine streaming updates
            updates = [...]  # List of AgentResponseUpdate objects
            response = AgentResponse.from_agent_run_response_updates(updates)

            # Serialization - to_dict and from_dict
            response_dict = response.to_dict()
            # {'type': 'agent_response', 'messages': [...], 'response_id': 'run_123',
            #  'additional_properties': {}}
            restored_response = AgentResponse.from_dict(response_dict)
            print(restored_response.response_id)  # "run_123"

            # Serialization - to_json and from_json
            response_json = response.to_json()
            # '{"type": "agent_response", "messages": [...], "response_id": "run_123", ...}'
            restored_from_json = AgentResponse.from_json(response_json)
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
        value: TResponseModel | None = None,
        response_format: type[BaseModel] | None = None,
        raw_representation: Any | None = None,
        additional_properties: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an AgentResponse.

        Keyword Args:
            messages: The list of chat messages in the response.
            response_id: The ID of the chat response.
            created_at: A timestamp for the chat response.
            usage_details: The usage details for the chat response.
            value: The structured output of the agent run response, if applicable.
            response_format: Optional response format for the agent response.
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
        # UsageDetails is now a TypedDict, so dict is already the right type

        self.messages = processed_messages
        self.response_id = response_id
        self.created_at = created_at
        self.usage_details = usage_details
        self._value: TResponseModel | None = value
        self._response_format: type[BaseModel] | None = response_format
        self._value_parsed: bool = value is not None
        self.additional_properties = additional_properties or {}
        self.additional_properties.update(kwargs or {})
        self.raw_representation = raw_representation

    @property
    def text(self) -> str:
        """Get the concatenated text of all messages."""
        return "".join(msg.text for msg in self.messages) if self.messages else ""

    @property
    def value(self) -> TResponseModel | None:
        """Get the parsed structured output value.

        If a response_format was provided and parsing hasn't been attempted yet,
        this will attempt to parse the text into the specified type.

        Raises:
            ValidationError: If the response text doesn't match the expected schema.
        """
        if self._value_parsed:
            return self._value
        if (
            self._response_format is not None
            and isinstance(self._response_format, type)
            and issubclass(self._response_format, BaseModel)
        ):
            self._value = cast(TResponseModel, self._response_format.model_validate_json(self.text))
            self._value_parsed = True
        return self._value

    @property
    def user_input_requests(self) -> list[Content]:
        """Get all BaseUserInputRequest messages from the response."""
        return [
            content
            for msg in self.messages
            for content in msg.contents
            if isinstance(content, Content) and content.user_input_request
        ]

    @overload
    @classmethod
    def from_agent_run_response_updates(
        cls: type["AgentResponse[Any]"],
        updates: Sequence["AgentResponseUpdate"],
        *,
        output_format_type: type[TResponseModelT],
    ) -> "AgentResponse[TResponseModelT]": ...

    @overload
    @classmethod
    def from_agent_run_response_updates(
        cls: type["AgentResponse[Any]"],
        updates: Sequence["AgentResponseUpdate"],
        *,
        output_format_type: None = None,
    ) -> "AgentResponse[Any]": ...

    @classmethod
    def from_agent_run_response_updates(
        cls: type[TAgentRunResponse],
        updates: Sequence["AgentResponseUpdate"],
        *,
        output_format_type: type[BaseModel] | None = None,
    ) -> TAgentRunResponse:
        """Joins multiple updates into a single AgentResponse.

        Args:
            updates: A sequence of AgentResponseUpdate objects to combine.

        Keyword Args:
            output_format_type: Optional Pydantic model type to parse the response text into structured data.
        """
        msg = cls(messages=[], response_format=output_format_type)
        for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        if output_format_type:
            msg.try_parse_value(output_format_type)
        return msg

    @overload
    @classmethod
    async def from_agent_response_generator(
        cls: type["AgentResponse[Any]"],
        updates: AsyncIterable["AgentResponseUpdate"],
        *,
        output_format_type: type[TResponseModelT],
    ) -> "AgentResponse[TResponseModelT]": ...

    @overload
    @classmethod
    async def from_agent_response_generator(
        cls: type["AgentResponse[Any]"],
        updates: AsyncIterable["AgentResponseUpdate"],
        *,
        output_format_type: None = None,
    ) -> "AgentResponse[Any]": ...

    @classmethod
    async def from_agent_response_generator(
        cls: type[TAgentRunResponse],
        updates: AsyncIterable["AgentResponseUpdate"],
        *,
        output_format_type: type[BaseModel] | None = None,
    ) -> TAgentRunResponse:
        """Joins multiple updates into a single AgentResponse.

        Args:
            updates: An async iterable of AgentResponseUpdate objects to combine.

        Keyword Args:
            output_format_type: Optional Pydantic model type to parse the response text into structured data
        """
        msg = cls(messages=[], response_format=output_format_type)
        async for update in updates:
            _process_update(msg, update)
        _finalize_response(msg)
        if output_format_type:
            msg.try_parse_value(output_format_type)
        return msg

    def __str__(self) -> str:
        return self.text

    @overload
    def try_parse_value(self, output_format_type: type[TResponseModelT]) -> TResponseModelT | None: ...

    @overload
    def try_parse_value(self, output_format_type: None = None) -> TResponseModel | None: ...

    def try_parse_value(self, output_format_type: type[BaseModel] | None = None) -> BaseModel | None:
        """Try to parse the text into a typed value.

        This is the safe alternative when you need to parse the response text into a typed value.
        Returns the parsed value on success, or None on failure.

        Args:
            output_format_type: The Pydantic model type to parse into.
                               If None, uses the response_format from initialization.

        Returns:
            The parsed value as the specified type, or None if parsing fails.
        """
        format_type = output_format_type or self._response_format
        if format_type is None or not (isinstance(format_type, type) and issubclass(format_type, BaseModel)):
            return None

        # Cache the result unless a different schema than the configured response_format is requested.
        # This prevents calls with a different schema from polluting the cached value.
        use_cache = (
            self._response_format is None or output_format_type is None or output_format_type is self._response_format
        )

        if use_cache and self._value_parsed and self._value is not None:
            return self._value  # type: ignore[return-value, no-any-return]
        try:
            parsed_value = format_type.model_validate_json(self.text)  # type: ignore[reportUnknownMemberType]
            if use_cache:
                self._value = cast(TResponseModel, parsed_value)
                self._value_parsed = True
            return parsed_value  # type: ignore[return-value]
        except ValidationError as ex:
            logger.warning("Failed to parse value from agent run response text: %s", ex)
            return None


# region AgentResponseUpdate


class AgentResponseUpdate(SerializationMixin):
    """Represents a single streaming response chunk from an Agent.

    Examples:
        .. code-block:: python

            from agent_framework import AgentResponseUpdate, Content

            # Create an agent run update
            update = AgentResponseUpdate(
                contents=[Content.from_text(text="Processing...")],
                role="assistant",
                response_id="run_123",
            )
            print(update.text)  # "Processing..."

            # Check for user input requests
            user_requests = update.user_input_requests

            # Serialization - to_dict and from_dict
            update_dict = update.to_dict()
            # {'type': 'agent_response_update', 'contents': [{'type': 'text', 'text': 'Processing...'}],
            #  'role': {'type': 'role', 'value': 'assistant'}, 'response_id': 'run_123'}
            restored_update = AgentResponseUpdate.from_dict(update_dict)
            print(restored_update.response_id)  # "run_123"

            # Serialization - to_json and from_json
            update_json = update.to_json()
            # '{"type": "agent_response_update", "contents": [{"type": "text", "text": "Processing..."}], ...}'
            restored_from_json = AgentResponseUpdate.from_json(update_json)
            print(restored_from_json.text)  # "Processing..."
    """

    DEFAULT_EXCLUDE: ClassVar[set[str]] = {"raw_representation"}

    def __init__(
        self,
        *,
        contents: Sequence[Content | MutableMapping[str, Any]] | None = None,
        text: Content | str | None = None,
        role: Role | MutableMapping[str, Any] | str | None = None,
        author_name: str | None = None,
        response_id: str | None = None,
        message_id: str | None = None,
        created_at: CreatedAtT | None = None,
        additional_properties: MutableMapping[str, Any] | None = None,
        raw_representation: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an AgentResponseUpdate.

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
        parsed_contents: list[Content] = [] if contents is None else _parse_content_list(contents)

        if text is not None:
            if isinstance(text, str):
                text = Content.from_text(text=text)
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
        return "".join(content.text for content in self.contents if content.type == "text") if self.contents else ""  # type: ignore[misc]

    @property
    def user_input_requests(self) -> list[Content]:
        """Get all BaseUserInputRequest messages from the response."""
        return [content for content in self.contents if isinstance(content, Content) and content.user_input_request]

    def __str__(self) -> str:
        return self.text


# region ChatOptions


class ToolMode(TypedDict, total=False):
    """Tool choice mode for the chat options.

    Fields:
        mode: One of "auto", "required", or "none".
        required_function_name: Optional function name when `mode == "required"`.
    """

    mode: Literal["auto", "required", "none"]
    required_function_name: str


# region TypedDict-based Chat Options


class _ChatOptionsBase(TypedDict, total=False):
    """Common request settings for AI services as a TypedDict.

    All fields are optional (total=False) to allow partial specification.
    Provider-specific TypedDicts extend this with additional options.

    These options represent the common denominator across chat providers.
    Individual implementations may raise errors for unsupported options.

    Examples:
        .. code-block:: python

            from agent_framework import ChatOptions, ToolMode

            # Type-safe options
            options: ChatOptions = {
                "temperature": 0.7,
                "max_tokens": 1000,
                "model_id": "gpt-4",
            }

            # With tools
            options_with_tools: ChatOptions = {
                "model_id": "gpt-4",
                "tool_choice": "auto",
                "temperature": 0.7,
            }

            # Used with Unpack for function signatures
            # async def get_response(self, **options: Unpack[ChatOptions]) -> ChatResponse:
    """

    # Model selection
    model_id: str

    # Generation parameters
    temperature: float
    top_p: float
    max_tokens: int
    stop: str | Sequence[str]
    seed: int
    logit_bias: dict[str | int, float]

    # Penalty parameters
    frequency_penalty: float
    presence_penalty: float

    # Tool configuration (forward reference to avoid circular import)
    tools: "ToolProtocol | Callable[..., Any] | MutableMapping[str, Any] | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]] | None"  # noqa: E501
    tool_choice: ToolMode | Literal["auto", "required", "none"]
    allow_multiple_tool_calls: bool

    # Response configuration
    response_format: type[BaseModel] | Mapping[str, Any] | None

    # Metadata
    metadata: dict[str, Any]
    user: str
    store: bool
    conversation_id: str

    # System/instructions
    instructions: str


if TYPE_CHECKING:

    class ChatOptions(_ChatOptionsBase, Generic[TResponseModel], total=False):
        response_format: type[TResponseModel] | Mapping[str, Any] | None  # type: ignore[misc]

else:
    ChatOptions = _ChatOptionsBase


# region Chat Options Utility Functions


async def validate_chat_options(options: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize chat options dictionary.

    Validates numeric constraints and converts types as needed.

    Args:
        options: The options dictionary to validate.

    Returns:
        The validated and normalized options dictionary.

    Raises:
        ValueError: If any option value is invalid.

    Examples:
        .. code-block:: python

            from agent_framework import validate_chat_options

            options = await validate_chat_options({
                "temperature": 0.7,
                "max_tokens": 1000,
            })
    """
    result = dict(options)  # Make a copy

    # Validate numeric constraints
    if (freq_pen := result.get("frequency_penalty")) is not None:
        if not (-2.0 <= freq_pen <= 2.0):
            raise ValueError("frequency_penalty must be between -2.0 and 2.0")
        result["frequency_penalty"] = float(freq_pen)

    if (pres_pen := result.get("presence_penalty")) is not None:
        if not (-2.0 <= pres_pen <= 2.0):
            raise ValueError("presence_penalty must be between -2.0 and 2.0")
        result["presence_penalty"] = float(pres_pen)

    if (temp := result.get("temperature")) is not None:
        if not (0.0 <= temp <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        result["temperature"] = float(temp)

    if (top_p := result.get("top_p")) is not None:
        if not (0.0 <= top_p <= 1.0):
            raise ValueError("top_p must be between 0.0 and 1.0")
        result["top_p"] = float(top_p)

    if (max_tokens := result.get("max_tokens")) is not None and max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0")

    # Validate and normalize tools
    if "tools" in result:
        result["tools"] = await validate_tools(result["tools"])

    return result


def normalize_tools(
    tools: (
        ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None
    ),
) -> list[ToolProtocol | MutableMapping[str, Any]]:
    """Normalize tools into a list.

    Converts callables to FunctionTool objects and ensures all tools are either
    ToolProtocol instances or MutableMappings.

    Args:
        tools: Tools to normalize - can be a single tool, callable, or sequence.

    Returns:
        Normalized list of tools.

    Examples:
        .. code-block:: python

            from agent_framework import normalize_tools, tool


            @tool
            def my_tool(x: int) -> int:
                return x * 2


            # Single tool
            tools = normalize_tools(my_tool)

            # List of tools
            tools = normalize_tools([my_tool, another_tool])
    """
    final_tools: list[ToolProtocol | MutableMapping[str, Any]] = []
    if not tools:
        return final_tools
    if not isinstance(tools, Sequence) or isinstance(tools, (str, MutableMapping)):
        # Single tool (not a sequence, or is a mapping which shouldn't be treated as sequence)
        if not isinstance(tools, (ToolProtocol, MutableMapping)):
            return [tool(tools)]
        return [tools]
    for tool_item in tools:
        if isinstance(tool_item, (ToolProtocol, MutableMapping)):
            final_tools.append(tool_item)
        else:
            # Convert callable to FunctionTool
            final_tools.append(tool(tool_item))
    return final_tools


async def validate_tools(
    tools: (
        ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None
    ),
) -> list[ToolProtocol | MutableMapping[str, Any]]:
    """Validate and normalize tools into a list.

    Converts callables to FunctionTool objects, expands MCP tools to their constituent
    functions (connecting them if needed), and ensures all tools are either ToolProtocol
    instances or MutableMappings.

    Args:
        tools: Tools to validate - can be a single tool, callable, or sequence.

    Returns:
        Normalized list of tools, or None if no tools provided.

    Examples:
        .. code-block:: python

            from agent_framework import validate_tools, tool


            @tool
            def my_tool(x: int) -> int:
                return x * 2


            # Single tool
            tools = await validate_tools(my_tool)

            # List of tools
            tools = await validate_tools([my_tool, another_tool])
    """
    # Use normalize_tools for common sync logic (converts callables to FunctionTool)
    normalized = normalize_tools(tools)

    # Handle MCP tool expansion (async-only)
    final_tools: list[ToolProtocol | MutableMapping[str, Any]] = []
    for tool_ in normalized:
        # Import MCPTool here to avoid circular imports
        from ._mcp import MCPTool

        if isinstance(tool_, MCPTool):
            # Expand MCP tools to their constituent functions
            if not tool_.is_connected:
                await tool_.connect()
            final_tools.extend(tool_.functions)  # type: ignore
        else:
            final_tools.append(tool_)

    return final_tools


def validate_tool_mode(
    tool_choice: ToolMode | Literal["auto", "required", "none"] | None,
) -> ToolMode:
    """Validate and normalize tool_choice to a ToolMode dict.

    Args:
        tool_choice: The tool choice value to validate.

    Returns:
        A ToolMode dict (contains keys: "mode", and optionally "required_function_name").

    Raises:
        ContentError: If the tool_choice string is invalid.
    """
    if not tool_choice:
        return {"mode": "none"}
    if isinstance(tool_choice, str):
        if tool_choice not in ("auto", "required", "none"):
            raise ContentError(f"Invalid tool choice: {tool_choice}")
        return {"mode": tool_choice}
    if "mode" not in tool_choice:
        raise ContentError("tool_choice dict must contain 'mode' key")
    if tool_choice["mode"] not in ("auto", "required", "none"):
        raise ContentError(f"Invalid tool choice: {tool_choice['mode']}")
    if tool_choice["mode"] != "required" and "required_function_name" in tool_choice:
        raise ContentError("tool_choice with mode other than 'required' cannot have 'required_function_name'")
    return tool_choice


def merge_chat_options(
    base: dict[str, Any] | None,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge two chat options dictionaries.

    Values from override take precedence over base.
    Lists and dicts are combined (not replaced).
    Instructions are concatenated with newlines.

    Args:
        base: The base options dictionary.
        override: The override options dictionary.

    Returns:
        A new merged options dictionary.

    Examples:
        .. code-block:: python

            from agent_framework import merge_chat_options

            base = {"temperature": 0.5, "model_id": "gpt-4"}
            override = {"temperature": 0.7, "max_tokens": 1000}
            merged = merge_chat_options(base, override)
            # {"temperature": 0.7, "model_id": "gpt-4", "max_tokens": 1000}
    """
    if not base:
        return dict(override) if override else {}
    if not override:
        return dict(base)

    result: dict[str, Any] = {}

    # Copy base values (shallow copy for simple values, dict copy for dicts)
    for key, value in base.items():
        if isinstance(value, dict):
            result[key] = dict(value)
        elif isinstance(value, list):
            result[key] = list(value)
        else:
            result[key] = value

    # Apply overrides
    for key, value in override.items():
        if value is None:
            continue

        if key == "instructions":
            # Concatenate instructions
            base_instructions = result.get("instructions")
            if base_instructions:
                result["instructions"] = f"{base_instructions}\n{value}"
            else:
                result["instructions"] = value
        elif key == "tools":
            # Merge tools lists
            base_tools = result.get("tools")
            if base_tools and value:
                # Add tools that aren't already present
                merged_tools = list(base_tools)
                for tool in value if isinstance(value, list) else [value]:
                    if tool not in merged_tools:
                        merged_tools.append(tool)
                result["tools"] = merged_tools
            elif value:
                result["tools"] = list(value) if isinstance(value, list) else [value]
        elif key in ("logit_bias", "metadata", "additional_properties"):
            # Merge dicts
            base_dict = result.get(key)
            if base_dict and isinstance(value, dict):
                result[key] = {**base_dict, **value}
            elif value:
                result[key] = dict(value) if isinstance(value, dict) else value
        elif key == "tool_choice":
            # tool_choice from override takes precedence
            result["tool_choice"] = value if value else result.get("tool_choice")
        elif key == "response_format":
            # response_format from override takes precedence if set
            result["response_format"] = value
        else:
            # Simple override
            result[key] = value

    return result
