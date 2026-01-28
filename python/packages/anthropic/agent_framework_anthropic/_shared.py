# Copyright (c) Microsoft. All rights reserved.

"""Anthropic settings with backend-aware environment variable resolution."""

from typing import TYPE_CHECKING, Any, ClassVar, Literal

from agent_framework._settings import AFSettings, BackendConfig, SecretString

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["AnthropicBackend", "AnthropicSettings"]

AnthropicBackend = Literal["anthropic", "foundry", "vertex", "bedrock"]


class AnthropicSettings(AFSettings):
    """Anthropic settings with multi-backend support.

    This settings class supports four backends:
    - **anthropic**: Direct Anthropic API (default, highest precedence)
    - **foundry**: Azure AI Foundry
    - **vertex**: Google Vertex AI
    - **bedrock**: AWS Bedrock

    The backend is determined by:
    1. Explicit `backend` parameter
    2. `ANTHROPIC_CHAT_CLIENT_BACKEND` environment variable
    3. Auto-detection based on which backend's credentials are present (using precedence)

    Keyword Args:
        backend: Explicit backend selection. One of "anthropic", "foundry", "vertex", "bedrock".
        model_id: The model ID to use (e.g., "claude-sonnet-4-5-20250929").

        # Anthropic backend
        api_key: Anthropic API key (env: ANTHROPIC_API_KEY).
        base_url: Base URL for the API (env: ANTHROPIC_BASE_URL).

        # Foundry backend
        foundry_api_key: Azure AI Foundry API key (env: ANTHROPIC_FOUNDRY_API_KEY).
        foundry_resource: Azure resource name (env: ANTHROPIC_FOUNDRY_RESOURCE).
        foundry_base_url: Foundry endpoint URL (env: ANTHROPIC_FOUNDRY_BASE_URL).
        ad_token_provider: Azure AD token provider callable.

        # Vertex backend
        vertex_access_token: Google access token (env: ANTHROPIC_VERTEX_ACCESS_TOKEN).
        vertex_region: GCP region (env: CLOUD_ML_REGION).
        vertex_project_id: GCP project ID (env: ANTHROPIC_VERTEX_PROJECT_ID).
        vertex_base_url: Vertex endpoint URL (env: ANTHROPIC_VERTEX_BASE_URL).
        google_credentials: Google auth credentials object.

        # Bedrock backend
        aws_access_key: AWS access key ID (env: ANTHROPIC_AWS_ACCESS_KEY_ID).
        aws_secret_key: AWS secret access key (env: ANTHROPIC_AWS_SECRET_ACCESS_KEY).
        aws_session_token: AWS session token (env: ANTHROPIC_AWS_SESSION_TOKEN).
        aws_profile: AWS profile name (env: ANTHROPIC_AWS_PROFILE).
        aws_region: AWS region (env: ANTHROPIC_AWS_REGION).
        bedrock_base_url: Bedrock endpoint URL (env: ANTHROPIC_BEDROCK_BASE_URL).

        env_file_path: Path to .env file for loading settings.
        env_file_encoding: Encoding of the .env file.

    Examples:
        Using Anthropic API directly:

        .. code-block:: python

            # Via environment variable ANTHROPIC_API_KEY
            settings = AnthropicSettings()

            # Or explicitly
            settings = AnthropicSettings(api_key="sk-...")

        Using Azure AI Foundry:

        .. code-block:: python

            settings = AnthropicSettings(
                backend="foundry",
                foundry_resource="my-resource",
                foundry_api_key="...",
            )

        Using Google Vertex AI:

        .. code-block:: python

            settings = AnthropicSettings(
                backend="vertex",
                vertex_region="us-central1",
                vertex_project_id="my-project",
            )

        Using AWS Bedrock:

        .. code-block:: python

            settings = AnthropicSettings(
                backend="bedrock",
                aws_region="us-east-1",
                aws_profile="my-profile",
            )
    """

    env_prefix: ClassVar[str] = "ANTHROPIC_"
    backend_env_var: ClassVar[str | None] = "ANTHROPIC_CHAT_CLIENT_BACKEND"

    # Common field mappings (used regardless of backend)
    field_env_vars: ClassVar[dict[str, str]] = {
        "model_id": "CHAT_MODEL_ID",  # ANTHROPIC_CHAT_MODEL_ID
    }

    # Backend-specific configurations
    backend_configs: ClassVar[dict[str, BackendConfig]] = {
        "anthropic": BackendConfig(
            env_prefix="ANTHROPIC_",
            precedence=1,
            detection_fields={"api_key"},
            field_env_vars={
                "api_key": "API_KEY",
                "base_url": "BASE_URL",
            },
        ),
        "foundry": BackendConfig(
            env_prefix="ANTHROPIC_FOUNDRY_",
            precedence=2,
            detection_fields={"foundry_api_key", "foundry_resource"},
            field_env_vars={
                "foundry_api_key": "API_KEY",
                "foundry_resource": "RESOURCE",
                "foundry_base_url": "BASE_URL",
            },
        ),
        "vertex": BackendConfig(
            env_prefix="ANTHROPIC_VERTEX_",
            precedence=3,
            detection_fields={"vertex_access_token", "vertex_project_id"},
            field_env_vars={
                "vertex_access_token": "ACCESS_TOKEN",
                "vertex_project_id": "PROJECT_ID",
                "vertex_base_url": "BASE_URL",
                "vertex_region": "REGION",
            },
        ),
        "bedrock": BackendConfig(
            env_prefix="ANTHROPIC_",
            precedence=4,
            detection_fields={"aws_access_key", "aws_profile"},
            field_env_vars={
                "aws_access_key": "AWS_ACCESS_KEY_ID",
                "aws_secret_key": "AWS_SECRET_ACCESS_KEY",
                "aws_session_token": "AWS_SESSION_TOKEN",
                "aws_profile": "AWS_PROFILE",
                "aws_region": "AWS_REGION",
                "bedrock_base_url": "BEDROCK_BASE_URL",
            },
        ),
    }

    # Common
    model_id: str | None = None

    # Anthropic backend
    api_key: SecretString | None = None
    base_url: str | None = None

    # Foundry backend
    foundry_api_key: SecretString | None = None
    foundry_resource: str | None = None
    foundry_base_url: str | None = None
    # ad_token_provider is not stored - passed directly to client

    # Vertex backend
    vertex_access_token: str | None = None
    vertex_region: str | None = None
    vertex_project_id: str | None = None
    vertex_base_url: str | None = None
    # google_credentials is not stored - passed directly to client

    # Bedrock backend
    aws_access_key: str | None = None
    aws_secret_key: SecretString | None = None
    aws_session_token: str | None = None
    aws_profile: str | None = None
    aws_region: str | None = None
    bedrock_base_url: str | None = None

    def __init__(
        self,
        *,
        backend: AnthropicBackend | None = None,
        model_id: str | None = None,
        # Anthropic backend
        api_key: str | None = None,
        base_url: str | None = None,
        # Foundry backend
        foundry_api_key: str | None = None,
        foundry_resource: str | None = None,
        foundry_base_url: str | None = None,
        ad_token_provider: "Callable[[], str] | None" = None,
        # Vertex backend
        vertex_access_token: str | None = None,
        vertex_region: str | None = None,
        vertex_project_id: str | None = None,
        vertex_base_url: str | None = None,
        google_credentials: Any | None = None,
        # Bedrock backend
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        bedrock_base_url: str | None = None,
        # Common
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize Anthropic settings."""
        # Store non-serializable objects before calling super().__init__
        self._ad_token_provider = ad_token_provider
        self._google_credentials = google_credentials

        super().__init__(
            backend=backend,
            model_id=model_id,
            api_key=api_key,
            base_url=base_url,
            foundry_api_key=foundry_api_key,
            foundry_resource=foundry_resource,
            foundry_base_url=foundry_base_url,
            vertex_access_token=vertex_access_token,
            vertex_region=vertex_region,
            vertex_project_id=vertex_project_id,
            vertex_base_url=vertex_base_url,
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key,
            aws_session_token=aws_session_token,
            aws_profile=aws_profile,
            aws_region=aws_region,
            bedrock_base_url=bedrock_base_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        # Handle special case for vertex_region from CLOUD_ML_REGION
        if self.vertex_region is None and self._backend == "vertex":
            import os

            self.vertex_region = os.environ.get("CLOUD_ML_REGION")

    @property
    def ad_token_provider(self) -> "Callable[[], str] | None":
        """Get the Azure AD token provider."""
        return self._ad_token_provider

    @property
    def google_credentials(self) -> Any | None:
        """Get the Google credentials object."""
        return self._google_credentials
