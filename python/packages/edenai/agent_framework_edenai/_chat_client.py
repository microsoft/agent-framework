# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, ClassVar, Generic, Literal, cast, overload

from agent_framework import (
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CompactionStrategy,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    TokenizerProtocol,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework.observability import ChatTelemetryLayer
from agent_framework_openai._chat_completion_client import RawOpenAIChatCompletionClient
from openai import AsyncOpenAI
from pydantic import BaseModel

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover


__all__ = [
    "EdenAIChatClient",
    "EdenAIChatOptions",
    "EdenAISettings",
]

# Eden AI is OpenAI compatible, so this base URL is used with the OpenAI SDK.
DEFAULT_EDENAI_BASE_URL = "https://api.edenai.run/v3"

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


# region Eden AI Chat Options TypedDict


class EdenAIChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Eden AI chat options dict.

    Eden AI is a gateway that exposes many providers behind one OpenAI compatible
    API, so the standard OpenAI Chat Completions options are supported. The model
    uses the ``provider/model`` format, for example ``openai/gpt-4o-mini`` or
    ``anthropic/claude-sonnet-4-5``.

    See: https://docs.edenai.co

    Keys:
        # Inherited from ChatOptions (supported via the OpenAI compatible API):
        model: The ``provider/model`` identifier, for example ``openai/gpt-4o-mini``.
        temperature: Sampling temperature (0-2).
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum tokens to generate.
        stop: Stop sequences.
        tools: List of tools available to the model.
        tool_choice: How the model should use tools.
        frequency_penalty: Frequency penalty (-2.0 to 2.0).
        presence_penalty: Presence penalty (-2.0 to 2.0).
        seed: Random seed for reproducibility.
        response_format: Structured output schema.

    Note:
        The options that are honored depend on the underlying provider the model
        routes to. Options a provider does not support are typically ignored.
    """

    # Eden AI specific options
    extra_body: dict[str, Any]
    """Additional request body parameters passed through to the underlying provider."""


EdenAIChatOptionsT = TypeVar(
    "EdenAIChatOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="EdenAIChatOptions",
    covariant=True,
)


# endregion


class EdenAISettings(TypedDict, total=False):
    """Eden AI settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'EDENAI_'.

    Keys:
        api_key: The Eden AI API key. (Env var EDENAI_API_KEY)
        base_url: The base URL for the Eden AI OpenAI compatible API.
            Defaults to https://api.edenai.run/v3. (Env var EDENAI_BASE_URL)
        model: The ``provider/model`` to use, for example ``openai/gpt-4o-mini``.
            (Env var EDENAI_MODEL)
    """

    api_key: SecretString | None
    base_url: str | None
    model: str | None


class EdenAIChatClient(
    FunctionInvocationLayer[EdenAIChatOptionsT],
    ChatMiddlewareLayer[EdenAIChatOptionsT],
    ChatTelemetryLayer[EdenAIChatOptionsT],
    RawOpenAIChatCompletionClient[EdenAIChatOptionsT],
    Generic[EdenAIChatOptionsT],
):
    """Eden AI Chat completion class with middleware, telemetry, and function invocation support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "edenai"

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: ChatOptions[ResponseModelT],
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[ResponseModelT]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[False] = ...,
        options: EdenAIChatOptionsT | ChatOptions[None] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[Any]]: ...

    @overload
    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: Literal[True],
        options: EdenAIChatOptionsT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> ResponseStream[ChatResponseUpdate, ChatResponse[Any]]: ...

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: EdenAIChatOptionsT | ChatOptions[Any] | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    ) -> Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]:
        """Get a response from the Eden AI chat client with all standard layers enabled."""
        super_get_response = cast(
            "Callable[..., Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]]",
            super().get_response,
        )
        effective_client_kwargs = dict(client_kwargs) if client_kwargs is not None else {}
        if middleware is not None:
            effective_client_kwargs["middleware"] = middleware
        return super_get_response(
            messages=messages,
            stream=stream,
            options=options,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            function_invocation_kwargs=function_invocation_kwargs,
            client_kwargs=effective_client_kwargs,
        )

    def __init__(
        self,
        model: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str = "utf-8",
    ) -> None:
        """Initialize an EdenAIChatClient.

        Eden AI is a gateway to many model providers behind one OpenAI compatible API
        and a single key. Models use the ``provider/model`` format, for example
        ``openai/gpt-4o-mini`` or ``anthropic/claude-sonnet-4-5``. The full list is
        available from the Eden AI catalog, so this client does not hardcode it.

        Keyword Args:
            model: The ``provider/model`` to use. If not provided, it is loaded from
                the EDENAI_MODEL environment variable.
            api_key: The Eden AI API key. If not provided, it is loaded from the
                EDENAI_API_KEY environment variable.
            base_url: The base URL for the Eden AI OpenAI compatible API. If not
                provided, it is loaded from EDENAI_BASE_URL and otherwise defaults to
                https://api.edenai.run/v3.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional sequence of ChatAndFunctionMiddlewareTypes to apply to requests.
            function_invocation_configuration: Optional configuration for function invocation support.
            env_file_path: If provided, the .env settings are read from this file path location.
            env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

        Examples:

            .. code-block:: python

                # Create an EdenAIChatClient with a specific model:
                from agent_framework.edenai import EdenAIChatClient

                client = EdenAIChatClient(model="openai/gpt-4o-mini", api_key="...")

                agent = client.as_agent(
                    name="EdenAgent",
                    instructions="You are a helpful agent.",
                    tools=get_weather,
                )
                response = await agent.run("What's the weather like in Paris?")

                # Or set the values in the environment:
                # EDENAI_API_KEY=...
                # EDENAI_MODEL=openai/gpt-4o-mini
                client = EdenAIChatClient()

        Raises:
            SettingNotFoundError: If the api key or model could not be resolved.
        """
        settings = load_settings(
            EdenAISettings,
            env_prefix="EDENAI_",
            required_fields=["api_key", "model"],
            api_key=api_key,
            base_url=base_url,
            model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        resolved_api_key: str = str(settings["api_key"])  # type: ignore[typeddict-item]
        resolved_model: str = settings["model"]  # type: ignore[assignment,typeddict-item]
        resolved_base_url = settings.get("base_url") or DEFAULT_EDENAI_BASE_URL

        super().__init__(
            model=resolved_model,
            async_client=AsyncOpenAI(base_url=resolved_base_url, api_key=resolved_api_key),
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )
