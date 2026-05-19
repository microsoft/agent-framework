# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterable, Awaitable, Sequence
from typing import Any, ClassVar, Final, Generic, Mapping, TypedDict

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework.observability import ChatTelemetryLayer
from anthropic import AsyncAnthropic

from agent_framework_anthropic._chat_client import AnthropicOptionsT, RawAnthropicClient

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover

__all__ = [
    "MiniMaxClient",
    "MiniMaxSettings",
    "RawMiniMaxClient",
]

logger = logging.getLogger("agent_framework.minimax")

MINIMAX_DEFAULT_BASE_URL: Final[str] = "https://api.minimax.io/anthropic"

MINIMAX_MODELS: Final[list[str]] = [
    "MiniMax-M2.7",
    "MiniMax-M2.7-highspeed",
]

# Parameters not supported by MiniMax Anthropic-compatible API
MINIMAX_UNSUPPORTED_PARAMS: Final[frozenset[str]] = frozenset([
    "betas",
    "top_k",
    "stop_sequences",
    "service_tier",
    "mcp_servers",
    "context_management",
    "container",
    "thinking",
    "output_format",
    "additional_beta_flags",
])


class MiniMaxSettings(TypedDict, total=False):
    """MiniMax Project settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'MINIMAX_'.

    Keys:
        api_key: The MiniMax API key.
        chat_model: The MiniMax chat model.
        base_url: Optional custom base URL for the MiniMax API.
    """

    api_key: SecretString | None
    chat_model: str | None
    base_url: str | None


class RawMiniMaxClient(
    RawAnthropicClient[AnthropicOptionsT],
    Generic[AnthropicOptionsT],
):
    """Raw MiniMax chat client using Anthropic-compatible API.

    Warning:
        **This class should not normally be used directly.** It does not include middleware,
        telemetry, or function invocation support that you most likely need.
        Use ``MiniMaxClient`` instead for a fully-featured client with all layers applied.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "minimax"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropic | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw MiniMax client.

        Keyword Args:
            api_key: The MiniMax API key to use for authentication.
            model: The model to use (e.g. ``"MiniMax-M2.7"``).
            base_url: Optional base URL override. Defaults to ``https://api.minimax.io/anthropic``.
            anthropic_client: An existing AsyncAnthropic client to use with a custom base_url.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.

        Examples:
            .. code-block:: python

                from agent_framework_minimax import MiniMaxClient

                # Using environment variables (set MINIMAX_API_KEY)
                client = MiniMaxClient(model="MiniMax-M2.7")

                # Or passing parameters directly
                client = MiniMaxClient(
                    model="MiniMax-M2.7",
                    api_key="your_minimax_api_key",
                )
        """
        settings = load_settings(
            MiniMaxSettings,
            env_prefix="MINIMAX_",
            api_key=api_key,
            chat_model=model,
            base_url=base_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        api_key_secret = settings.get("api_key")
        model_setting = settings.get("chat_model")
        base_url_setting = settings.get("base_url") or MINIMAX_DEFAULT_BASE_URL

        if anthropic_client is None:
            if api_key_secret is None:
                raise ValueError(
                    "MiniMax API key is required. Set via 'api_key' parameter "
                    "or 'MINIMAX_API_KEY' environment variable."
                )
            anthropic_client = AsyncAnthropic(
                api_key=api_key_secret.get_secret_value(),
                base_url=base_url_setting,
                default_headers={"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
            )

        super().__init__(
            model=model_setting,
            anthropic_client=anthropic_client,
            additional_properties=additional_properties,
        )

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Execute a chat request against MiniMax's Anthropic-compatible API.

        Overrides the parent to use the standard messages API (not beta) and
        filters out parameters unsupported by MiniMax.
        """
        run_options = self._prepare_options(messages, options, **kwargs)

        # Remove params not supported by MiniMax Anthropic-compatible API
        for param in MINIMAX_UNSUPPORTED_PARAMS:
            run_options.pop(param, None)

        if stream:
            async def _stream() -> AsyncIterable[ChatResponseUpdate]:
                async for chunk in await self.anthropic_client.messages.create(**run_options, stream=True):  # type: ignore[misc]
                    parsed_chunk = self._process_stream_event(chunk)  # type: ignore[arg-type]
                    if parsed_chunk:
                        yield parsed_chunk

            return self._build_response_stream(_stream(), response_format=options.get("response_format"))

        async def _get_response() -> ChatResponse:
            message = await self.anthropic_client.messages.create(**run_options, stream=False)  # type: ignore[misc]
            return self._process_message(message, options)  # type: ignore[arg-type]

        return _get_response()


class MiniMaxClient(  # type: ignore[misc]
    FunctionInvocationLayer[AnthropicOptionsT],
    ChatMiddlewareLayer[AnthropicOptionsT],
    ChatTelemetryLayer[AnthropicOptionsT],
    RawMiniMaxClient[AnthropicOptionsT],
    Generic[AnthropicOptionsT],
):
    """MiniMax chat client with middleware, telemetry, and function invocation support.

    Uses MiniMax's Anthropic-compatible API (https://api.minimax.io/anthropic).
    Supported models: ``MiniMax-M2.7``, ``MiniMax-M2.7-highspeed``.

    Examples:
        .. code-block:: python

            from agent_framework_minimax import MiniMaxClient

            # Set MINIMAX_API_KEY environment variable, then:
            client = MiniMaxClient(model="MiniMax-M2.7")
            response = await client.get_response("Hello from MiniMax!")
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropic | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a MiniMax client.

        Keyword Args:
            api_key: The MiniMax API key to use for authentication.
            model: The model to use (e.g. ``"MiniMax-M2.7"``).
            base_url: Optional base URL override. Defaults to ``https://api.minimax.io/anthropic``.
            anthropic_client: An existing AsyncAnthropic client to use with a custom base_url.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            anthropic_client=anthropic_client,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
