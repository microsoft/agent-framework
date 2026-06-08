# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypedDict

from agent_framework import (
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
)
from agent_framework._settings import load_settings
from agent_framework._telemetry import get_user_agent
from agent_framework.observability import ChatTelemetryLayer
from anthropic import NOT_GIVEN, AsyncAnthropicVertex

from ._chat_client import AnthropicOptionsT, RawAnthropicClient

if TYPE_CHECKING:
    from google.auth.credentials import Credentials as GoogleCredentials


class AnthropicVertexSettings(TypedDict, total=False):
    """Resolved settings for Anthropic Vertex wrappers."""

    cloud_ml_region: str | None
    anthropic_vertex_project_id: str | None
    anthropic_vertex_base_url: str | None
    anthropic_chat_model: str | None


class RawAnthropicVertexClient(RawAnthropicClient[AnthropicOptionsT], Generic[AnthropicOptionsT]):
    """Raw Anthropic Vertex chat client without middleware, telemetry, or function invocation support."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "google.vertex.ai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        model: str | None = None,
        region: str | None = None,
        project_id: str | None = None,
        access_token: str | None = None,
        credentials: GoogleCredentials | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropicVertex | None = None,
        additional_beta_flags: list[str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize a raw Anthropic Vertex client.

        Keyword Args:
            model: The Anthropic model to use.
            region: Vertex region. Falls back to `CLOUD_ML_REGION`.
            project_id: Vertex project ID. Falls back to `ANTHROPIC_VERTEX_PROJECT_ID`.
            access_token: Explicit OAuth access token.
            credentials: Google credentials object.
            base_url: Optional custom Anthropic Vertex base URL.
            anthropic_client: Existing AsyncAnthropicVertex client to reuse.
            additional_beta_flags: Additional beta flags to enable on the client.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        settings = load_settings(
            AnthropicVertexSettings,
            env_prefix="",
            cloud_ml_region=region,
            anthropic_vertex_project_id=project_id,
            anthropic_vertex_base_url=base_url,
            anthropic_chat_model=model,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        model_setting = settings.get("anthropic_chat_model")
        region_setting = settings.get("cloud_ml_region")
        project_id_setting = settings.get("anthropic_vertex_project_id")

        if anthropic_client is None:
            resolved_region = region_setting if region_setting is not None else NOT_GIVEN
            resolved_project_id = project_id_setting if project_id_setting is not None else NOT_GIVEN
            anthropic_client = AsyncAnthropicVertex(
                region=resolved_region,
                project_id=resolved_project_id,
                access_token=access_token,
                credentials=credentials,
                base_url=settings.get("anthropic_vertex_base_url"),
                default_headers={"User-Agent": get_user_agent()},
            )

        super().__init__(
            model=model_setting,
            anthropic_client=anthropic_client,
            additional_beta_flags=additional_beta_flags,
            additional_properties=additional_properties,
        )


class AnthropicVertexClient(  # type: ignore[misc]
    FunctionInvocationLayer[AnthropicOptionsT],
    ChatMiddlewareLayer[AnthropicOptionsT],
    ChatTelemetryLayer[AnthropicOptionsT],
    RawAnthropicVertexClient[AnthropicOptionsT],
    Generic[AnthropicOptionsT],
):
    """Anthropic Vertex chat client with middleware, telemetry, and function invocation support."""

    def __init__(
        self,
        *,
        model: str | None = None,
        region: str | None = None,
        project_id: str | None = None,
        access_token: str | None = None,
        credentials: GoogleCredentials | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropicVertex | None = None,
        additional_beta_flags: list[str] | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Anthropic Vertex client.

        Keyword Args:
            model: The Anthropic model to use.
            region: Vertex region. Falls back to `CLOUD_ML_REGION`.
            project_id: Vertex project ID. Falls back to `ANTHROPIC_VERTEX_PROJECT_ID`.
            access_token: Explicit OAuth access token.
            credentials: Google credentials object.
            base_url: Optional custom Anthropic Vertex base URL.
            anthropic_client: Existing AsyncAnthropicVertex client to reuse.
            additional_beta_flags: Additional beta flags to enable on the client.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional middleware to apply to the client.
            function_invocation_configuration: Optional function invocation configuration override.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(
            model=model,
            region=region,
            project_id=project_id,
            access_token=access_token,
            credentials=credentials,
            base_url=base_url,
            anthropic_client=anthropic_client,
            additional_beta_flags=additional_beta_flags,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
