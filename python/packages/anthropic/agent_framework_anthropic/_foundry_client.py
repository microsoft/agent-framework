# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, ClassVar, Generic, TypedDict

from agent_framework import (
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import get_user_agent
from agent_framework.observability import ChatTelemetryLayer
from anthropic import AsyncAnthropicFoundry

from ._chat_client import AnthropicOptionsT, RawAnthropicClient

AnthropicFoundryAzureADTokenProvider = Callable[[], str | Awaitable[str]]


class AnthropicFoundrySettings(TypedDict, total=False):
    """Resolved settings for Anthropic Foundry wrappers."""

    anthropic_foundry_api_key: SecretString | None
    anthropic_foundry_resource: str | None
    anthropic_foundry_base_url: str | None
    anthropic_chat_model: str | None


class RawAnthropicFoundryClient(RawAnthropicClient[AnthropicOptionsT], Generic[AnthropicOptionsT]):
    """Raw Anthropic Foundry chat client without middleware, telemetry, or function invocation support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        model: str | None = None,
        resource: str | None = None,
        api_key: str | None = None,
        azure_ad_token_provider: AnthropicFoundryAzureADTokenProvider | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropicFoundry | None = None,
        additional_beta_flags: list[str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Anthropic Foundry client.

        Keyword Args:
            model: The Anthropic model to use.
            resource: The Foundry resource name.
            api_key: The Foundry Anthropic API key.
            azure_ad_token_provider: Azure AD token provider used by the Anthropic SDK.
            base_url: Full Anthropic-compatible Foundry base URL.
            anthropic_client: Existing AsyncAnthropicFoundry client to reuse.
            additional_beta_flags: Additional beta flags to enable on the client.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        settings = load_settings(
            AnthropicFoundrySettings,
            env_prefix="",
            anthropic_foundry_api_key=api_key,
            anthropic_foundry_resource=resource,
            anthropic_foundry_base_url=base_url,
            anthropic_chat_model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        api_key_secret = settings.get("anthropic_foundry_api_key")
        model_setting = settings.get("anthropic_chat_model")
        resource_setting = settings.get("anthropic_foundry_resource")
        base_url_setting = settings.get("anthropic_foundry_base_url")
        api_key_value = api_key_secret.get_secret_value() if api_key_secret is not None else None

        if anthropic_client is None:
            if base_url_setting is None and resource_setting is None:
                message = (
                    "Anthropic Foundry requires either `resource`/`ANTHROPIC_FOUNDRY_RESOURCE` "
                    "or `base_url`/`ANTHROPIC_FOUNDRY_BASE_URL`."
                )
                raise ValueError(message)
            if base_url_setting is not None:
                anthropic_client = AsyncAnthropicFoundry(
                    base_url=base_url_setting,
                    api_key=api_key_value,
                    azure_ad_token_provider=azure_ad_token_provider,
                    default_headers={"User-Agent": get_user_agent()},
                )
            else:
                anthropic_client = AsyncAnthropicFoundry(
                    resource=resource_setting,
                    api_key=api_key_value,
                    azure_ad_token_provider=azure_ad_token_provider,
                    default_headers={"User-Agent": get_user_agent()},
                )

        super().__init__(
            model=model_setting,
            anthropic_client=anthropic_client,
            additional_beta_flags=additional_beta_flags,
            additional_properties=additional_properties,
        )


class AnthropicFoundryClient(  # type: ignore[misc]
    FunctionInvocationLayer[AnthropicOptionsT],
    ChatMiddlewareLayer[AnthropicOptionsT],
    ChatTelemetryLayer[AnthropicOptionsT],
    RawAnthropicFoundryClient[AnthropicOptionsT],
    Generic[AnthropicOptionsT],
):
    """Anthropic Foundry chat client with middleware, telemetry, and function invocation support."""

    def __init__(
        self,
        *,
        model: str | None = None,
        resource: str | None = None,
        api_key: str | None = None,
        azure_ad_token_provider: AnthropicFoundryAzureADTokenProvider | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropicFoundry | None = None,
        additional_beta_flags: list[str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Anthropic Foundry client.

        Keyword Args:
            model: The Anthropic model to use.
            resource: The Foundry resource name.
            api_key: The Foundry Anthropic API key.
            azure_ad_token_provider: Azure AD token provider used by the Anthropic SDK.
            base_url: Full Anthropic-compatible Foundry base URL.
            anthropic_client: Existing AsyncAnthropicFoundry client to reuse.
            additional_beta_flags: Additional beta flags to enable on the client.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(
            model=model,
            resource=resource,
            api_key=api_key,
            azure_ad_token_provider=azure_ad_token_provider,
            base_url=base_url,
            anthropic_client=anthropic_client,
            additional_beta_flags=additional_beta_flags,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
