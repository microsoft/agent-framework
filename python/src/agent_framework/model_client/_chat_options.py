# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Literal, Protocol, Self, TypedDict

from pydantic import BaseModel


class ChatResponseFormat(Protocol):
    """Represents the response format desired by the caller."""
    type: Literal["json", "text"]  # type: str instead?

    JSON: ClassVar[Self]  # type: ignore[assignment]
    """A singleton instance representing structured JSON data but without any particular schema.

    Remarks:
        If a schema is desired, instantiate `ChatResponseFormatJson` directly, instead.
    """
    TEXT: ClassVar[Self]  # type: ignore[assignment]
    """A singleton instance representing plain text data."""


class ChatResponseFormatJson(ChatResponseFormat):
    """Represents a response format for structured JSON data."""
    type: Literal["json"] = "json"

    schema_name: str | None = None
    """The name of the schema."""
    schema_description: str | None = None
    """The description of the schema."""
    schema: Dict[str, Any] | None = None  # Should this be a type {t: pydantic.BaseModel} instead?
    """The JSON schema associated with the response, or `None` if there is none."""


class ChatResponseFormatText(ChatResponseFormat):
    """Represents a response format with no constraints around the format."""
    type: Literal["text"] = "text"


# Note: ClassVar is used to indicate that these are class-level constants, not instance attributes.
# The type: ignore[assignment] is used to suppress the type checker warning about assigning to a ClassVar,
# it gets assigned immediately after the class definition.
ChatResponseFormatJson.JSON = ChatResponseFormatJson()
ChatResponseFormatText.TEXT = ChatResponseFormatText()


class ChatToolMode(BaseModel):
    """Describes how tools should be selected by a `ModelClient`.

    Remarks:
        Predefined values `AUTO`, `NONE`, and `REQUIRE_ANY` are provided. To nominate a specific function, use
        `require_specific(tool_name: str)`.
    """
    value: str

    NONE: ClassVar[Self]  # type: ignore[assignment]
    """A predefined ChatToolMode indicating that tool usage is unsupported."""
    AUTO: ClassVar[Self]  # type: ignore[assignment]
    """A predefined ChatToolMode indication that tool usage is optional."""
    REQUIRE_ANY: ClassVar[Self]  # type: ignore[assignment]
    """A predefined ChatToolMode indicating that tool usage is required, but that any tool can be selected.
    At least one tool must be provided in the request."""

    def require_specific(self, tool_name: str) -> Self:
        """Instantiates a `ChatToolMode` indicating that tool usage is required, and that the specified tool must be selected.
        The tool name must match an entry in the list of available tools in the request.
        """  # noqa: D205, E501
        return RequiredChatToolMode(value="require_specific", required_function_name=tool_name)


class AutoChatToolMode(ChatToolMode):
    """Indicates that a `ModelClient` is free to select any of the available tools, or none at all."""
    value: Literal["auto"] = "auto"


class NoneChatToolMode(ChatToolMode):
    """Indicates that a `ModelClient` should not request the invocation of any tools."""
    value: Literal["none"] = "none"


class RequiredChatToolMode(ChatToolMode):
    """Represents a mode where a chat tool must be called.

    This class can optionally nominate a specific function or indicate that any of the functions can be
    selected.
    """
    value: Literal["require_any", "require_specific"] = "require_any"

    required_function_name: str | None = None
    """The name of a specific function that must be called."""


# Note: ClassVar is used to indicate that these are class-level constants, not instance attributes.
# The type: ignore[assignment] is used to suppress the type checker warning about assigning to a ClassVar,
# it gets assigned immediately after the class definition.
ChatToolMode.NONE = NoneChatToolMode()
ChatToolMode.AUTO = AutoChatToolMode()
ChatToolMode.REQUIRE_ANY = RequiredChatToolMode()


class AITool(Protocol):
    """Represents a tool that can be specified to an AI service."""
    name: str
    """The name of the tool."""
    description: str | None = None
    """A description of the tool, suitable for use in describing the purpose to a model."""
    additional_properties: Dict[str, Any] | None = None
    """Additional properties associated with the tool."""


# SyncRawRepresentationFactory = Callable[ChatOptions, Any]  # noqa: ERA001

class ChatOptions(TypedDict, total=False):
    """Represents the options for a chat request.

    Remarks:
        This class is here for the purposes of documentation and ease of use. Options should still
        be passed as keyword arguments to the `ModelClient.generate_response` and
        `ModelClient.generate_streaming_response` methods.
    """
    allow_multiple_tool_calls: bool | None = None
    """Indicates whether a single response is allowed to include multiple tool calls. If `False`,
    the `ModelClient` is asked to return a maximum of one tool call per request. If `True`, there is
    no limit. If `None`, the provider may select its own default."""
    conversation_id: str | None = None
    """An optional identifier used to associate a request with an existing conversation."""
    frequency_penalty: float | None = None
    """A penalty for repeated tokens in chat responses proportional to how many times they've appeared."""
    max_output_tokens: int | None = None
    """The maximum number of tokens in the generated chat response."""
    model_id: str | None = None
    """The model ID for the chat request."""
    presence_penalty: float | None = None
    """a value that influences the probability of generated tokens appearing based on their existing
    presence in generated text."""
    # raw_representation_factory: SyncRawRepresentationFactory | None = None  # ???  # noqa: ERA001
    response_format: ChatResponseFormat | None = None
    """The response format for the chat request."""
    seed: int | None = None
    """A seed value used by a service to control the reproducibility of results."""
    stop_sequences: List[str] | None = None
    """The list of stop sequences."""
    temperature: float | None = None
    """The temperature for generating chat responses."""
    tool_mode: ChatToolMode | None = None
    """The tool mode for the chat request."""
    tools: List[AITool] | None = None
    """The list of tools to include with a chat request."""
    top_k: int | None = None
    """The number of most probable tokens that the model considers when generating the next part of
    the text."""
    top_p: float | None = None
    """The 'nucleus sampling' factor (or "top p") for generating chat responses."""
