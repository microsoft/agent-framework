# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class AIContent(BaseModel):
    """Represents content used by AI services."""
    raw_representation: Any | None = None
    """The raw representation of the content from an underlying implementation."""
    additional_properties: Dict[str, Any] | None = None
    """Additional properties for the content."""


class TextContent(AIContent):
    """Represents text content in a chat."""
    text: str
    """The text content represented by this instance."""


class TextReasoningContent(AIContent):
    """Represents text reasoning content in a chat.

    Remarks:
        This class and `TextContent` are superficially similar, but distinct.
    """  # TODO(): Should we merge these two classes, and use a property to distinguish them?
    text: str
    """The text reasoning content represented by this instance."""


class DataContent(AIContent):
    """Represents binary data content with an associated media type (also known as a MIME type)."""
    data: bytes
    """The data represented by this instance."""

    media_type: str
    """The media type of the data, e.g., 'image/png', 'application/json', etc."""

    @property
    def base64_data(self) -> str:
        """Returns the data represented by this instance encoded as a Base64 string."""
        import base64
        return base64.b64encode(self.data).decode("utf-8")  # use ASCII instead? (Should be equivalent for base64)

    # @base64_data.setter
    # def base64_data(self, value: str) -> None:
    #     """Sets the data from a base64 encoded string."""
    #     import base64  # noqa: ERA001
    #     self.data = base64.b64decode(value.encode("utf-8"))  # noqa: ERA001

    @property
    def uri(self) -> str:
        """Returns the data as a data URI."""
        return f"data:{self.media_type};base64,{self.base64_data}"

    # @uri.setter
    # def uri(self, value: str) -> None:
    #     """Sets the data from a data URI."""
    #     import re  # noqa: ERA001
    #     match = re.match(r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>.+)$", value)  # noqa: ERA001
    #     if not match:
    #         raise ValueError("Invalid data URI format")  # noqa: ERA001
    #     self.media_type = match.group("media_type")  # noqa: ERA001
    #     self.base64_data = match.group("base64_data")  # noqa: ERA001


class ErrorContent(AIContent):
    """Represents an error.

    Remarks:
        Typically used for non-fatal errors, where something went wrong as part of the operation,
        but the operation was still able to continue.
    """
    error_code: str | None = None
    """The error code associated with the error."""
    details: str | None = None
    """Additional details about the error."""
    message: str | None
    """The error message."""

    def __str__(self) -> str:
        """Returns a string representation of the error."""
        return f"Error {self.error_code}: {self.message}" if self.error_code else self.message


class FunctionCallContent(AIContent):
    """Represents a function call request."""
    call_id: str
    """The function call identifier."""
    name: str
    """The name of the function requested."""
    arguments: Dict[str, Any | None] | None = None
    """The arguments requested to be provided to the function."""
    exception: Exception | None = None
    """Any exception that occurred while mapping the original function call data to this representation."""


class FunctionResultContent(AIContent):
    """Represents the result of a function call."""
    call_id: str
    """The identifier of the function call for which this is the result."""
    result: Any | None = None
    """The result of the function call, or a generic error message if the function call failed."""
    exception: Exception | None = None
    """An exception that occurred if the function call failed."""


class UriContent(AIContent):
    """Represents a URI content.

    Remarks:
        This is used for content that is identified by a URI, such as an image or a file.
        For data URIs, use `DataContent` instead.
    """
    uri: str
    """The URI of the content, e.g., 'https://example.com/image.png'."""
    media_type: str
    """The media type of the content, e.g., 'image/png', 'application/json', etc."""


# TODO(): Do we want to surface this? Will it even be possible for agents to bookkeep without this?
class UsageContent(AIContent):
    """Represents usage information associated with a chat request and response."""
    details: UsageDetails
    """The usage information."""


class UsageDetails(BaseModel):
    """Provides usage details about a request/response."""
    input_token_count: int | None = None
    """The number of tokens in the input."""
    output_token_count: int | None = None
    """The number of tokens in the output."""
    total_token_count: int | None = None
    """The total number of tokens used to produce the response."""
    additional_counts: Dict[str, int] | None = None
    """A dictionary of additional usage counts."""
