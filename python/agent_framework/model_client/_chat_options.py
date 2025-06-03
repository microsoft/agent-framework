# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from agent_framework import AITool


class ChatResponseFormatJson(BaseModel):
    """Represents a response format for structured JSON data."""

    type: Literal["json"] = "json"

    schema_name: str | None = None
    """The name of the schema."""
    schema_description: str | None = None
    """The description of the schema."""
    schema_: dict[str, Any] | None = Field(
        default=None,
        alias="schema",
    )
    """The JSON schema associated with the response, or `None` if there is none."""


class ChatResponseFormatText(BaseModel):
    """Represents a response format with no constraints around the format."""

    type: Literal["text"] = "text"


ChatResponseFormat = ChatResponseFormatJson | ChatResponseFormatText


class AutoChatToolMode(BaseModel):
    """Indicates that a `ModelClient` is free to select any of the available tools, or none at all."""

    value: Literal["auto"] = "auto"


class NoneChatToolMode(BaseModel):
    """Indicates that a `ModelClient` should not request the invocation of any tools."""

    value: Literal["none"] = "none"


class RequiredChatToolMode(BaseModel):
    """Represents a mode where a chat tool must be called.

    This class can optionally nominate a specific function or indicate that any of the functions can be
    selected.
    """

    value: Literal["require_any", "require_specific"] = "require_any"

    required_function_name: str | None = None
    """The name of a specific function that must be called."""


ChatToolMode = AutoChatToolMode | NoneChatToolMode | RequiredChatToolMode


# SyncRawRepresentationFactory = Callable[ChatOptions, Any]  # noqa: ERA001


class ChatOptions(TypedDict, total=False):
    """Represents the options for a chat request.

    Remarks:
        This class is here for the purposes of documentation and ease of use. Options should still
        be passed as keyword arguments to the `ModelClient.generate_response` and
        `ModelClient.generate_streaming_response` methods.
    """

    allow_multiple_tool_calls: bool | None
    """Indicates whether a single response is allowed to include multiple tool calls. If `False`,
    the `ModelClient` is asked to return a maximum of one tool call per request. If `True`, there is
    no limit. If `None`, the provider may select its own default."""
    conversation_id: str | None
    """An optional identifier used to associate a request with an existing conversation."""
    frequency_penalty: float | None
    """A penalty for repeated tokens in chat responses proportional to how many times they've appeared."""
    max_output_tokens: int | None
    """The maximum number of tokens in the generated chat response."""
    model_id: str | None
    """The model ID for the chat request."""
    presence_penalty: float | None
    """a value that influences the probability of generated tokens appearing based on their existing
    presence in generated text."""
    response_format: ChatResponseFormat | None
    """The response format for the chat request."""
    seed: int | None
    """A seed value used by a service to control the reproducibility of results."""
    stop_sequences: list[str] | None
    """The list of stop sequences."""
    temperature: float | None
    """The temperature for generating chat responses."""
    tool_mode: ChatToolMode | None
    """The tool mode for the chat request."""
    tools: list[AITool] | None
    """The list of tools to include with a chat request."""
    top_k: int | None
    """The number of most probable tokens that the model considers when generating the next part of
    the text."""
    top_p: float | None
    """The 'nucleus sampling' factor (or "top p") for generating chat responses."""

    # raw_representation_factory: SyncRawRepresentationFactory | None = None  # ???  # noqa: ERA001
    # This is probably not needed - the ChatClient should be able to deal with the conversion internally,
    # especially since the ChatOptions are passed as kwargs.
