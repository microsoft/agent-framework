# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Generic, TypedDict

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
)
from agent_framework._settings import SecretString, load_settings
from agent_framework.observability import ChatTelemetryLayer
from anthropic import AsyncAnthropicBedrock

from ._chat_client import AnthropicOptionsT, RawAnthropicClient


class AnthropicBedrockSettings(TypedDict, total=False):
    """Resolved settings for Anthropic Bedrock wrappers."""

    aws_access_key_id: SecretString | None
    aws_secret_access_key: SecretString | None
    aws_region: str | None
    aws_profile: str | None
    aws_session_token: SecretString | None
    anthropic_bedrock_base_url: str | None
    anthropic_chat_model: str | None


class RawAnthropicBedrockClient(RawAnthropicClient[AnthropicOptionsT], Generic[AnthropicOptionsT]):
    """Raw Anthropic Bedrock chat client without middleware, telemetry, or function invocation support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "aws.bedrock"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        model: str | None = None,
        aws_secret_key: str | None = None,
        aws_access_key: str | None = None,
        aws_region: str | None = None,
        aws_profile: str | None = None,
        aws_session_token: str | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropicBedrock | None = None,
        additional_beta_flags: list[str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Anthropic Bedrock client.

        Keyword Args:
            model: The Anthropic model to use.
            aws_secret_key: AWS secret access key.
            aws_access_key: AWS access key ID.
            aws_region: AWS region.
            aws_profile: AWS profile name.
            aws_session_token: AWS session token.
            base_url: Optional custom Anthropic Bedrock base URL.
            anthropic_client: Existing AsyncAnthropicBedrock client to reuse.
            additional_beta_flags: Additional beta flags to enable on the client.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        settings = load_settings(
            AnthropicBedrockSettings,
            env_prefix="",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_region=aws_region,
            aws_profile=aws_profile,
            aws_session_token=aws_session_token,
            anthropic_bedrock_base_url=base_url,
            anthropic_chat_model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        model_setting = settings.get("anthropic_chat_model")
        access_key_secret = settings.get("aws_access_key_id")
        secret_key_secret = settings.get("aws_secret_access_key")
        session_token_secret = settings.get("aws_session_token")

        if anthropic_client is None:
            anthropic_client = AsyncAnthropicBedrock(
                aws_secret_key=secret_key_secret.get_secret_value() if secret_key_secret is not None else None,
                aws_access_key=access_key_secret.get_secret_value() if access_key_secret is not None else None,
                aws_region=settings.get("aws_region"),
                aws_profile=settings.get("aws_profile"),
                aws_session_token=session_token_secret.get_secret_value() if session_token_secret is not None else None,
                base_url=settings.get("anthropic_bedrock_base_url"),
                default_headers={"User-Agent": AGENT_FRAMEWORK_USER_AGENT},
            )

        super().__init__(
            model=model_setting,
            anthropic_client=anthropic_client,
            additional_beta_flags=additional_beta_flags,
            additional_properties=additional_properties,
        )


class AnthropicBedrockClient(  # type: ignore[misc]
    FunctionInvocationLayer[AnthropicOptionsT],
    ChatMiddlewareLayer[AnthropicOptionsT],
    ChatTelemetryLayer[AnthropicOptionsT],
    RawAnthropicBedrockClient[AnthropicOptionsT],
    Generic[AnthropicOptionsT],
):
    """Anthropic Bedrock chat client with middleware, telemetry, and function invocation support."""

    def __init__(
        self,
        *,
        model: str | None = None,
        aws_secret_key: str | None = None,
        aws_access_key: str | None = None,
        aws_region: str | None = None,
        aws_profile: str | None = None,
        aws_session_token: str | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropicBedrock | None = None,
        additional_beta_flags: list[str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Anthropic Bedrock client.

        Keyword Args:
            model: The Anthropic model to use.
            aws_secret_key: AWS secret access key.
            aws_access_key: AWS access key ID.
            aws_region: AWS region.
            aws_profile: AWS profile name.
            aws_session_token: AWS session token.
            base_url: Optional custom Anthropic Bedrock base URL.
            anthropic_client: Existing AsyncAnthropicBedrock client to reuse.
            additional_beta_flags: Additional beta flags to enable on the client.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(
            model=model,
            aws_secret_key=aws_secret_key,
            aws_access_key=aws_access_key,
            aws_region=aws_region,
            aws_profile=aws_profile,
            aws_session_token=aws_session_token,
            base_url=base_url,
            anthropic_client=anthropic_client,
            additional_beta_flags=additional_beta_flags,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
