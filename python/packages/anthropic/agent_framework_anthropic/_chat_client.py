# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import (
    AsyncIterable,
    Callable,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from typing import Any, ClassVar, Final, Generic, Literal, TypedDict, TypeVar, overload

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    Annotation,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FinishReason,
    FunctionTool,
    HostedCodeInterpreterTool,
    HostedMCPTool,
    HostedWebSearchTool,
    Role,
    TextSpanRegion,
    UsageDetails,
    get_logger,
    prepare_function_call_results,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_instrumentation
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock, AsyncAnthropicVertex
from anthropic.types.beta import (
    BetaContentBlock,
    BetaMessage,
    BetaMessageDeltaUsage,
    BetaRawContentBlockDelta,
    BetaRawMessageStreamEvent,
    BetaTextBlock,
    BetaUsage,
)
from anthropic.types.beta.beta_bash_code_execution_tool_result_error import (
    BetaBashCodeExecutionToolResultError,
)
from anthropic.types.beta.beta_code_execution_tool_result_error import (
    BetaCodeExecutionToolResultError,
)
from pydantic import BaseModel, SecretStr

from ._shared import AnthropicBackend, AnthropicSettings

if sys.version_info >= (3, 13):
    from typing import TypeVar
else:
    from typing_extensions import TypeVar

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover

__all__ = [
    "AnthropicChatOptions",
    "AnthropicClient",
    "ThinkingConfig",
]

logger = get_logger("agent_framework.anthropic")

ANTHROPIC_DEFAULT_MAX_TOKENS: Final[int] = 1024
BETA_FLAGS: Final[list[str]] = ["mcp-client-2025-04-04", "code-execution-2025-08-25"]
STRUCTURED_OUTPUTS_BETA_FLAG: Final[str] = "structured-outputs-2025-11-13"


# region Anthropic Chat Options TypedDict


class ThinkingConfig(TypedDict, total=False):
    """Configuration for enabling Claude's extended thinking.

    When enabled, responses include ``thinking`` content blocks showing Claude's
    thinking process before the final answer. Requires a minimum budget of 1,024
    tokens and counts towards your ``max_tokens`` limit.

    See https://docs.claude.com/en/docs/build-with-claude/extended-thinking for details.

    Keys:
        type: "enabled" to enable extended thinking, "disabled" to disable.
        budget_tokens: The token budget for thinking (minimum 1024, required when type="enabled").
    """

    type: Literal["enabled", "disabled"]
    budget_tokens: int


class AnthropicChatOptions(ChatOptions, total=False):
    """Anthropic-specific chat options.

    Extends ChatOptions with options specific to Anthropic's Messages API.
    Options that Anthropic doesn't support are typed as None to indicate they're unavailable.

    Note:
        Anthropic REQUIRES max_tokens to be specified. If not provided,
        a default of 1024 will be used.

    Keys:
        model_id: The model to use for the request,
            translates to ``model`` in Anthropic API.
        temperature: Sampling temperature between 0 and 1.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum number of tokens to generate (REQUIRED).
        stop: Stop sequences,
            translates to ``stop_sequences`` in Anthropic API.
        tools: List of tools (functions) available to the model.
        tool_choice: How the model should use tools.
        response_format: Structured output schema.
        metadata: Request metadata with user_id for tracking.
        user: User identifier, translates to ``metadata.user_id`` in Anthropic API.
        instructions: System instructions for the model,
            translates to ``system`` in Anthropic API.
        top_k: Number of top tokens to consider for sampling.
        service_tier: Service tier ("auto" or "standard_only").
        thinking: Extended thinking configuration for Claude models.
            When enabled, responses include ``thinking`` content blocks showing Claude's
            thinking process before the final answer. Requires a minimum budget of 1,024
            tokens and counts towards your ``max_tokens`` limit.
            See https://docs.claude.com/en/docs/build-with-claude/extended-thinking for details.
        container: Container configuration for skills.
        additional_beta_flags: Additional beta flags to enable on the request.
    """

    # Anthropic-specific generation parameters (supported by all models)
    top_k: int
    service_tier: Literal["auto", "standard_only"]

    # Extended thinking (Claude models)
    thinking: ThinkingConfig

    # Skills
    container: dict[str, Any]

    # Beta features
    additional_beta_flags: list[str]

    # Unsupported base options (override with None to indicate not supported)
    logit_bias: None  # type: ignore[misc]
    seed: None  # type: ignore[misc]
    frequency_penalty: None  # type: ignore[misc]
    presence_penalty: None  # type: ignore[misc]
    store: None  # type: ignore[misc]
    conversation_id: None  # type: ignore[misc]


TAnthropicOptions = TypeVar(
    "TAnthropicOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AnthropicChatOptions",
    covariant=True,
)

# Translation between framework options keys and Anthropic Messages API
OPTION_TRANSLATIONS: dict[str, str] = {
    "model_id": "model",
    "stop": "stop_sequences",
    "instructions": "system",
}


# region Role and Finish Reason Maps


ROLE_MAP: dict[Role, str] = {
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
    Role.SYSTEM: "user",
    Role.TOOL: "user",
}

FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop_sequence": FinishReason.STOP,
    "max_tokens": FinishReason.LENGTH,
    "tool_use": FinishReason.TOOL_CALLS,
    "end_turn": FinishReason.STOP,
    "refusal": FinishReason.CONTENT_FILTER,
    "pause_turn": FinishReason.STOP,
}

# Type alias for all supported Anthropic client types
AnthropicClientType = AsyncAnthropic | AsyncAnthropicBedrock | AsyncAnthropicVertex


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class AnthropicClient(BaseChatClient[TAnthropicOptions], Generic[TAnthropicOptions]):
    """Anthropic Chat client with multi-backend support.

    This client supports four backends:
    - **anthropic**: Direct Anthropic API (default)
    - **foundry**: Azure AI Foundry
    - **vertex**: Google Vertex AI
    - **bedrock**: AWS Bedrock

    The backend is determined automatically based on which credentials are available,
    or can be explicitly specified via the `backend` parameter.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "anthropic"  # type: ignore[reportIncompatibleVariableOverride, misc]

    @overload
    def __init__(
        self,
        *,
        backend: Literal["anthropic"],
        model_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        client: AnthropicClientType | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with direct Anthropic API backend.

        Args:
            backend: Must be "anthropic" for direct Anthropic API.
            model_id: The model to use (e.g., "claude-sonnet-4-5-20250929").
                Env var: ANTHROPIC_CHAT_MODEL_ID
            api_key: Anthropic API key.
                Env var: ANTHROPIC_API_KEY
            base_url: Optional custom base URL for the API.
                Env var: ANTHROPIC_BASE_URL
            client: Pre-configured AsyncAnthropic client instance. If provided,
                other connection parameters are ignored.
            additional_beta_flags: Additional beta feature flags to enable.
            env_file_path: Path to .env file to load environment variables from.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments passed to the underlying client.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["foundry"],
        model_id: str | None = None,
        foundry_api_key: str | None = None,
        foundry_resource: str | None = None,
        foundry_base_url: str | None = None,
        ad_token_provider: Callable[[], str] | None = None,
        client: AnthropicClientType | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with Azure AI Foundry backend.

        Args:
            backend: Must be "foundry" for Azure AI Foundry.
            model_id: The model to use (e.g., "claude-sonnet-4-5-20250929").
                Env var: ANTHROPIC_CHAT_MODEL_ID
            foundry_api_key: Azure AI Foundry API key. Use this or ad_token_provider.
                Env var: ANTHROPIC_FOUNDRY_API_KEY
            foundry_resource: Azure resource name (e.g., "my-resource" for
                https://my-resource.services.ai.azure.com/models).
                Env var: ANTHROPIC_FOUNDRY_RESOURCE
            foundry_base_url: Custom base URL. Alternative to foundry_resource.
                Env var: ANTHROPIC_FOUNDRY_BASE_URL
            ad_token_provider: Callable that returns an Azure AD token for authentication.
                Use this instead of foundry_api_key for Azure AD auth.
            client: Pre-configured AsyncAnthropicFoundry client instance. If provided,
                other connection parameters are ignored.
            additional_beta_flags: Additional beta feature flags to enable.
            env_file_path: Path to .env file to load environment variables from.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments passed to the underlying client.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["vertex"],
        model_id: str | None = None,
        vertex_access_token: str | None = None,
        vertex_region: str | None = None,
        vertex_project_id: str | None = None,
        vertex_base_url: str | None = None,
        google_credentials: Any | None = None,
        client: AnthropicClientType | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with Google Vertex AI backend.

        Args:
            backend: Must be "vertex" for Google Vertex AI.
            model_id: The model to use (e.g., "claude-sonnet-4-5-20250929").
                Env var: ANTHROPIC_CHAT_MODEL_ID
            vertex_access_token: Google Cloud access token. Use this or google_credentials.
                Env var: ANTHROPIC_VERTEX_ACCESS_TOKEN
            vertex_region: GCP region (e.g., "us-central1", "europe-west1").
                Env var: CLOUD_ML_REGION
            vertex_project_id: GCP project ID.
                Env var: ANTHROPIC_VERTEX_PROJECT_ID
            vertex_base_url: Custom base URL for the Vertex AI API.
                Env var: ANTHROPIC_VERTEX_BASE_URL
            google_credentials: google.auth.credentials.Credentials instance for authentication.
                Use this instead of vertex_access_token for service account auth.
            client: Pre-configured AsyncAnthropicVertex client instance. If provided,
                other connection parameters are ignored.
            additional_beta_flags: Additional beta feature flags to enable.
            env_file_path: Path to .env file to load environment variables from.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments passed to the underlying client.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        backend: Literal["bedrock"],
        model_id: str | None = None,
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        bedrock_base_url: str | None = None,
        client: AnthropicClientType | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with AWS Bedrock backend.

        Args:
            backend: Must be "bedrock" for AWS Bedrock.
            model_id: The model to use (e.g., "claude-sonnet-4-5-20250929").
                Env var: ANTHROPIC_CHAT_MODEL_ID
            aws_access_key: AWS access key ID.
                Env var: ANTHROPIC_AWS_ACCESS_KEY_ID
            aws_secret_key: AWS secret access key.
                Env var: ANTHROPIC_AWS_SECRET_ACCESS_KEY
            aws_session_token: AWS session token for temporary credentials.
                Env var: ANTHROPIC_AWS_SESSION_TOKEN
            aws_profile: AWS profile name from ~/.aws/credentials. Alternative to access keys.
                Env var: ANTHROPIC_AWS_PROFILE
            aws_region: AWS region (e.g., "us-east-1", "eu-west-1").
                Env var: ANTHROPIC_AWS_REGION
            bedrock_base_url: Custom base URL for the Bedrock API.
                Env var: ANTHROPIC_BEDROCK_BASE_URL
            client: Pre-configured AsyncAnthropicBedrock client instance. If provided,
                other connection parameters are ignored.
            additional_beta_flags: Additional beta feature flags to enable.
            env_file_path: Path to .env file to load environment variables from.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments passed to the underlying client.
        """
        ...

    @overload
    def __init__(
        self,
        *,
        backend: None = None,
        model_id: str | None = None,
        # Anthropic backend parameters
        api_key: str | None = None,
        base_url: str | None = None,
        # Foundry backend parameters
        foundry_api_key: str | None = None,
        foundry_resource: str | None = None,
        foundry_base_url: str | None = None,
        ad_token_provider: Callable[[], str] | None = None,
        # Vertex backend parameters
        vertex_access_token: str | None = None,
        vertex_region: str | None = None,
        vertex_project_id: str | None = None,
        vertex_base_url: str | None = None,
        google_credentials: Any | None = None,
        # Bedrock backend parameters
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        bedrock_base_url: str | None = None,
        # Common parameters
        client: AnthropicClientType | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize with auto-detected backend based on available credentials.

        Backend detection order (first match wins):
        1. anthropic - if ANTHROPIC_API_KEY is set
        2. foundry - if ANTHROPIC_FOUNDRY_API_KEY or ANTHROPIC_FOUNDRY_RESOURCE is set
        3. vertex - if ANTHROPIC_VERTEX_ACCESS_TOKEN or ANTHROPIC_VERTEX_PROJECT_ID is set
        4. bedrock - if ANTHROPIC_AWS_ACCESS_KEY_ID or ANTHROPIC_AWS_PROFILE is set

        You can also explicitly set the backend via ANTHROPIC_CHAT_CLIENT_BACKEND env var.

        Args:
            backend: None for auto-detection.
            model_id: The model to use (e.g., "claude-sonnet-4-5-20250929").
                Env var: ANTHROPIC_CHAT_MODEL_ID
            api_key: Anthropic API key (for anthropic backend).
                Env var: ANTHROPIC_API_KEY
            base_url: Custom base URL (for anthropic backend).
                Env var: ANTHROPIC_BASE_URL
            foundry_api_key: Azure AI Foundry API key (for foundry backend).
                Env var: ANTHROPIC_FOUNDRY_API_KEY
            foundry_resource: Azure resource name (for foundry backend).
                Env var: ANTHROPIC_FOUNDRY_RESOURCE
            foundry_base_url: Custom base URL (for foundry backend).
                Env var: ANTHROPIC_FOUNDRY_BASE_URL
            ad_token_provider: Azure AD token provider callable (for foundry backend).
            vertex_access_token: Google Cloud access token (for vertex backend).
                Env var: ANTHROPIC_VERTEX_ACCESS_TOKEN
            vertex_region: GCP region (for vertex backend).
                Env var: CLOUD_ML_REGION
            vertex_project_id: GCP project ID (for vertex backend).
                Env var: ANTHROPIC_VERTEX_PROJECT_ID
            vertex_base_url: Custom base URL (for vertex backend).
                Env var: ANTHROPIC_VERTEX_BASE_URL
            google_credentials: Google credentials instance (for vertex backend).
            aws_access_key: AWS access key ID (for bedrock backend).
                Env var: ANTHROPIC_AWS_ACCESS_KEY_ID
            aws_secret_key: AWS secret access key (for bedrock backend).
                Env var: ANTHROPIC_AWS_SECRET_ACCESS_KEY
            aws_session_token: AWS session token (for bedrock backend).
                Env var: ANTHROPIC_AWS_SESSION_TOKEN
            aws_profile: AWS profile name (for bedrock backend).
                Env var: ANTHROPIC_AWS_PROFILE
            aws_region: AWS region (for bedrock backend).
                Env var: ANTHROPIC_AWS_REGION
            bedrock_base_url: Custom base URL (for bedrock backend).
                Env var: ANTHROPIC_BEDROCK_BASE_URL
            client: Pre-configured Anthropic client instance. If provided,
                other connection parameters are ignored.
            additional_beta_flags: Additional beta feature flags to enable.
            env_file_path: Path to .env file to load environment variables from.
            env_file_encoding: Encoding of the .env file.
            **kwargs: Additional arguments passed to the underlying client.
        """
        ...

    def __init__(
        self,
        *,
        backend: AnthropicBackend | None = None,
        model_id: str | None = None,
        # Anthropic backend parameters
        api_key: str | None = None,
        base_url: str | None = None,
        # Foundry backend parameters
        foundry_api_key: str | None = None,
        foundry_resource: str | None = None,
        foundry_base_url: str | None = None,
        ad_token_provider: Callable[[], str] | None = None,
        # Vertex backend parameters
        vertex_access_token: str | None = None,
        vertex_region: str | None = None,
        vertex_project_id: str | None = None,
        vertex_base_url: str | None = None,
        google_credentials: Any | None = None,
        # Bedrock backend parameters
        aws_access_key: str | None = None,
        aws_secret_key: str | None = None,
        aws_session_token: str | None = None,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        bedrock_base_url: str | None = None,
        # Common parameters
        client: AnthropicClientType | None = None,
        additional_beta_flags: list[str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        # Legacy parameter (deprecated)
        anthropic_client: AnthropicClientType | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Anthropic Chat client.

                This client supports multiple backends for accessing Claude models:
                - **anthropic**: Direct Anthropic API
                - **foundry**: Azure AI Foundry
                - **vertex**: Google Vertex AI
                - **bedrock**: AWS Bedrock

                The backend is automatically detected based on available credentials,
                or can be explicitly specified via the `backend` parameter or
                `ANTHROPIC_CHAT_CLIENT_BACKEND` environment variable.

        Keyword Args:
                    backend: Explicit backend selection. If not provided, auto-detection is used.
                    model_id: The model ID to use (e.g., "claude-sonnet-4-5-20250929").

                    # Anthropic backend
                    api_key: Anthropic API key (env: ANTHROPIC_API_KEY).
                    base_url: Base URL for the API (env: ANTHROPIC_BASE_URL).

                    # Foundry backend (Azure AI Foundry)
                    foundry_api_key: Azure AI Foundry API key (env: ANTHROPIC_FOUNDRY_API_KEY).
                    foundry_resource: Azure resource name (env: ANTHROPIC_FOUNDRY_RESOURCE).
                    foundry_base_url: Foundry endpoint URL (env: ANTHROPIC_FOUNDRY_BASE_URL).
                    ad_token_provider: Azure AD token provider callable.

                    # Vertex backend (Google Vertex AI)
                    vertex_access_token: Google access token (env: ANTHROPIC_VERTEX_ACCESS_TOKEN).
                    vertex_region: GCP region (env: CLOUD_ML_REGION).
                    vertex_project_id: GCP project ID (env: ANTHROPIC_VERTEX_PROJECT_ID).
                    vertex_base_url: Vertex endpoint URL (env: ANTHROPIC_VERTEX_BASE_URL).
                    google_credentials: Google auth credentials object.

                    # Bedrock backend (AWS Bedrock)
                    aws_access_key: AWS access key ID (env: ANTHROPIC_AWS_ACCESS_KEY_ID).
                    aws_secret_key: AWS secret access key (env: ANTHROPIC_AWS_SECRET_ACCESS_KEY).
                    aws_session_token: AWS session token (env: ANTHROPIC_AWS_SESSION_TOKEN).
                    aws_profile: AWS profile name (env: ANTHROPIC_AWS_PROFILE).
                    aws_region: AWS region (env: ANTHROPIC_AWS_REGION).
                    bedrock_base_url: Bedrock endpoint URL (env: ANTHROPIC_BEDROCK_BASE_URL).

                    # Common parameters
                    client: Pre-configured Anthropic SDK client. If provided, backend-specific
                        parameters are ignored for client creation.
                    additional_beta_flags: Additional beta flags to enable on the client.
                    env_file_path: Path to .env file for loading settings.
                    env_file_encoding: Encoding of the .env file.
                    anthropic_client: Deprecated. Use `client` instead.
                    **kwargs: Additional keyword arguments passed to the parent class.

        Examples:
                    Using Anthropic API directly:

                    .. code-block:: python

                        # Via environment variable ANTHROPIC_API_KEY
                        client = AnthropicClient(model_id="claude-sonnet-4-5-20250929")

                        # Or explicitly
                        client = AnthropicClient(
                            api_key="sk-...",
                            model_id="claude-sonnet-4-5-20250929",
                        )

                    Using Azure AI Foundry:

                    .. code-block:: python

                        client = AnthropicClient(
                            backend="foundry",
                            foundry_resource="my-resource",
                            foundry_api_key="...",
                            model_id="claude-sonnet-4-5-20250929",
                        )

                    Using Google Vertex AI:

                    .. code-block:: python

                        client = AnthropicClient(
                            backend="vertex",
                            vertex_region="us-central1",
                            vertex_project_id="my-project",
                            model_id="claude-sonnet-4-5-20250929",
                        )

                    Using AWS Bedrock:

                    .. code-block:: python

                        client = AnthropicClient(
                            backend="bedrock",
                            aws_region="us-east-1",
                            aws_profile="my-profile",
                            model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                        )

                    Using a pre-configured client:

                    .. code-block:: python

                        from anthropic import AsyncAnthropic

                        sdk_client = AsyncAnthropic(api_key="sk-...")
                        client = AnthropicClient(
                            client=sdk_client,
                            model_id="claude-sonnet-4-5-20250929",
                        )
        <<<<<<< HEAD

                        # Using custom ChatOptions with type safety:
                        from typing import TypedDict
                        from agent_framework.anthropic import AnthropicChatOptions


                        class MyOptions(AnthropicChatOptions, total=False):
                            my_custom_option: str


                        client: AnthropicClient[MyOptions] = AnthropicClient(model_id="claude-sonnet-4-5-20250929")
                        response = await client.get_response("Hello", options={"my_custom_option": "value"})

        =======
        >>>>>>> e37fa5c9 (updated decision and implementation for anthropic)
        """
        # Handle legacy parameter
        if anthropic_client is not None and client is None:
            client = anthropic_client

        # Create settings to resolve backend and load env vars
        settings = AnthropicSettings(
            backend=backend,
            model_id=model_id,
            api_key=api_key,
            base_url=base_url,
            foundry_api_key=foundry_api_key,
            foundry_resource=foundry_resource,
            foundry_base_url=foundry_base_url,
            ad_token_provider=ad_token_provider,
            vertex_access_token=vertex_access_token,
            vertex_region=vertex_region,
            vertex_project_id=vertex_project_id,
            vertex_base_url=vertex_base_url,
            google_credentials=google_credentials,
            aws_access_key=aws_access_key,
            aws_secret_key=aws_secret_key,
            aws_session_token=aws_session_token,
            aws_profile=aws_profile,
            aws_region=aws_region,
            bedrock_base_url=bedrock_base_url,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        # Create client if not provided
        if client is None:
            client = self._create_client(settings)

        # Initialize parent
        super().__init__(**kwargs)

        # Initialize instance variables
        self.anthropic_client = client
        self.additional_beta_flags = additional_beta_flags or []
        self.model_id = settings.model_id
        self._backend = settings.backend
        # streaming requires tracking the last function call ID and name
        self._last_call_id_name: tuple[str, str] | None = None

    def _create_client(self, settings: AnthropicSettings) -> AnthropicClientType:
        """Create the appropriate Anthropic SDK client based on the resolved backend.

        Args:
            settings: The resolved Anthropic settings.

        Returns:
            An Anthropic SDK client instance.

        Raises:
            ServiceInitializationError: If required credentials are missing.
        """
        resolved_backend = settings.backend or "anthropic"
        default_headers = {"User-Agent": AGENT_FRAMEWORK_USER_AGENT}

        if resolved_backend == "anthropic":
            return self._create_anthropic_client(settings, default_headers)
        if resolved_backend == "foundry":
            return self._create_foundry_client(settings, default_headers)
        if resolved_backend == "vertex":
            return self._create_vertex_client(settings, default_headers)
        if resolved_backend == "bedrock":
            return self._create_bedrock_client(settings, default_headers)
        raise ServiceInitializationError(f"Unknown backend: {resolved_backend}")

    def _create_anthropic_client(self, settings: AnthropicSettings, default_headers: dict[str, str]) -> AsyncAnthropic:
        """Create an Anthropic API client."""
        if not settings.api_key:
            raise ServiceInitializationError(
                "Anthropic API key is required. Set via 'api_key' parameter "
                "or 'ANTHROPIC_API_KEY' environment variable."
            )

        api_key = settings.api_key.get_secret_value() if isinstance(settings.api_key, SecretStr) else settings.api_key

        return AsyncAnthropic(
            api_key=api_key,
            base_url=settings.base_url,
            default_headers=default_headers,
        )

    def _create_foundry_client(self, settings: AnthropicSettings, default_headers: dict[str, str]) -> AsyncAnthropic:
        """Create an Azure AI Foundry client.

        Azure AI Foundry uses the standard Anthropic client with custom auth.
        """
        api_key: str | None = None

        if settings.foundry_api_key:
            api_key = (
                settings.foundry_api_key.get_secret_value()
                if isinstance(settings.foundry_api_key, SecretStr)
                else settings.foundry_api_key
            )
        elif settings.ad_token_provider:
            api_key = settings.ad_token_provider()

        if not api_key:
            raise ServiceInitializationError(
                "Azure AI Foundry requires 'foundry_api_key' or 'ad_token_provider'. "
                "Set via parameters or 'ANTHROPIC_FOUNDRY_API_KEY' environment variable."
            )

        if not settings.foundry_base_url and not settings.foundry_resource:
            raise ServiceInitializationError(
                "Azure AI Foundry requires 'foundry_base_url' or 'foundry_resource'. "
                "Set via parameters or environment variables."
            )

        base_url = settings.foundry_base_url
        if not base_url and settings.foundry_resource:
            base_url = f"https://{settings.foundry_resource}.services.ai.azure.com/models"

        return AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers,
        )

    def _create_vertex_client(
        self, settings: AnthropicSettings, default_headers: dict[str, str]
    ) -> AsyncAnthropicVertex:
        """Create a Google Vertex AI client."""
        if not settings.vertex_region:
            raise ServiceInitializationError(
                "Vertex AI requires 'vertex_region'. Set via parameter or 'CLOUD_ML_REGION' environment variable."
            )

        client_kwargs: dict[str, Any] = {
            "region": settings.vertex_region,
            "default_headers": default_headers,
        }

        if settings.vertex_project_id:
            client_kwargs["project_id"] = settings.vertex_project_id

        if settings.vertex_access_token:
            client_kwargs["access_token"] = settings.vertex_access_token

        if settings.google_credentials:
            client_kwargs["credentials"] = settings.google_credentials

        if settings.vertex_base_url:
            client_kwargs["base_url"] = settings.vertex_base_url

        return AsyncAnthropicVertex(**client_kwargs)

    def _create_bedrock_client(
        self, settings: AnthropicSettings, default_headers: dict[str, str]
    ) -> AsyncAnthropicBedrock:
        """Create an AWS Bedrock client."""
        client_kwargs: dict[str, Any] = {
            "default_headers": default_headers,
        }

        if settings.aws_access_key:
            client_kwargs["aws_access_key"] = settings.aws_access_key
        if settings.aws_secret_key:
            client_kwargs["aws_secret_key"] = (
                settings.aws_secret_key.get_secret_value()
                if isinstance(settings.aws_secret_key, SecretStr)
                else settings.aws_secret_key
            )
        if settings.aws_session_token:
            client_kwargs["aws_session_token"] = settings.aws_session_token
        if settings.aws_profile:
            client_kwargs["aws_profile"] = settings.aws_profile
        if settings.aws_region:
            client_kwargs["aws_region"] = settings.aws_region
        if settings.bedrock_base_url:
            client_kwargs["base_url"] = settings.bedrock_base_url

        return AsyncAnthropicBedrock(**client_kwargs)

    # region Get response methods

    @override
    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        # prepare
        run_options = self._prepare_options(messages, options, **kwargs)
        # execute
        message = await self.anthropic_client.beta.messages.create(**run_options, stream=False)
        # process
        return self._process_message(message, options)

    @override
    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        # prepare
        run_options = self._prepare_options(messages, options, **kwargs)
        # execute and process
        async for chunk in await self.anthropic_client.beta.messages.create(**run_options, stream=True):
            parsed_chunk = self._process_stream_event(chunk)
            if parsed_chunk:
                yield parsed_chunk

    # region Prep methods

    def _prepare_options(
        self,
        messages: MutableSequence[ChatMessage],
        options: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create run options for the Anthropic client based on messages and options.

        Args:
            messages: The list of chat messages.
            options: The options dict.
            kwargs: Additional keyword arguments.

        Returns:
            A dictionary of run options for the Anthropic client.
        """
        # Prepend instructions from options if they exist
        instructions = options.get("instructions")
        if instructions:
            from agent_framework._types import prepend_instructions_to_messages

            messages = prepend_instructions_to_messages(list(messages), instructions, role="system")

        # Start with a copy of options, excluding keys we handle separately
        run_options: dict[str, Any] = {
            k: v for k, v in options.items() if v is not None and k not in {"instructions", "response_format"}
        }

        # Translation between options keys and Anthropic Messages API
        for old_key, new_key in OPTION_TRANSLATIONS.items():
            if old_key in run_options and old_key != new_key:
                run_options[new_key] = run_options.pop(old_key)

        # model id
        if not run_options.get("model"):
            if not self.model_id:
                raise ValueError("model_id must be a non-empty string")
            run_options["model"] = self.model_id

        # max_tokens - Anthropic requires this, default if not provided
        if not run_options.get("max_tokens"):
            run_options["max_tokens"] = ANTHROPIC_DEFAULT_MAX_TOKENS

        # messages
        run_options["messages"] = self._prepare_messages_for_anthropic(messages)

        # system message - first system message is passed as instructions
        if messages and isinstance(messages[0], ChatMessage) and messages[0].role == Role.SYSTEM:
            run_options["system"] = messages[0].text

        # betas
        run_options["betas"] = self._prepare_betas(options)

        # extra headers
        run_options["extra_headers"] = {"User-Agent": AGENT_FRAMEWORK_USER_AGENT}

        # Handle user option -> metadata.user_id (Anthropic uses metadata.user_id instead of user)
        if user := run_options.pop("user", None):
            metadata = run_options.get("metadata", {})
            if "user_id" not in metadata:
                metadata["user_id"] = user
            run_options["metadata"] = metadata

        # tools, mcp servers and tool choice
        if tools_config := self._prepare_tools_for_anthropic(options):
            run_options.update(tools_config)

        # response_format - use native output_format for structured outputs
        response_format = options.get("response_format")
        if response_format is not None:
            run_options["output_format"] = self._prepare_response_format(response_format)
            # Add the structured outputs beta flag
            run_options["betas"].add(STRUCTURED_OUTPUTS_BETA_FLAG)

        run_options.update(kwargs)
        return run_options

    def _prepare_betas(self, options: dict[str, Any]) -> set[str]:
        """Prepare the beta flags for the Anthropic API request.

        Args:
            options: The options dict that may contain additional beta flags.

        Returns:
            A set of beta flag strings to include in the request.
        """
        return {
            *BETA_FLAGS,
            *self.additional_beta_flags,
            *options.get("additional_beta_flags", []),
        }

    def _prepare_response_format(self, response_format: type[BaseModel] | dict[str, Any]) -> dict[str, Any]:
        """Prepare the output_format parameter for structured output.

        Args:
            response_format: Either a Pydantic model class or a dict with the schema specification.
                If a dict, it can be in OpenAI-style format with "json_schema" key,
                or direct format with "schema" key, or the raw schema dict itself.

        Returns:
            A dictionary representing the output_format for Anthropic's structured outputs.
        """
        if isinstance(response_format, dict):
            if "json_schema" in response_format:
                schema = response_format["json_schema"].get("schema", {})
            elif "schema" in response_format:
                schema = response_format["schema"]
            else:
                schema = response_format

            if isinstance(schema, dict):
                schema["additionalProperties"] = False

            return {
                "type": "json_schema",
                "schema": schema,
            }

        schema = response_format.model_json_schema()
        schema["additionalProperties"] = False

        return {
            "type": "json_schema",
            "schema": schema,
        }

    def _prepare_messages_for_anthropic(self, messages: MutableSequence[ChatMessage]) -> list[dict[str, Any]]:
        """Prepare a list of ChatMessages for the Anthropic client.

        This skips the first message if it is a system message,
        as Anthropic expects system instructions as a separate parameter.
        """
        # first system message is passed as instructions
        if messages and isinstance(messages[0], ChatMessage) and messages[0].role == Role.SYSTEM:
            return [self._prepare_message_for_anthropic(msg) for msg in messages[1:]]
        return [self._prepare_message_for_anthropic(msg) for msg in messages]

    def _prepare_message_for_anthropic(self, message: ChatMessage) -> dict[str, Any]:
        """Prepare a ChatMessage for the Anthropic client.

        Args:
            message: The ChatMessage to convert.

        Returns:
            A dictionary representing the message in Anthropic format.
        """
        a_content: list[dict[str, Any]] = []
        for content in message.contents:
            match content.type:
                case "text":
                    # Skip empty text content blocks - Anthropic API rejects them
                    if content.text:
                        a_content.append({"type": "text", "text": content.text})
                case "data":
                    if content.has_top_level_media_type("image"):
                        a_content.append({
                            "type": "image",
                            "source": {
                                "data": content.get_data_bytes_as_str(),  # type: ignore[attr-defined]
                                "media_type": content.media_type,
                                "type": "base64",
                            },
                        })
                    else:
                        logger.debug(f"Ignoring unsupported data content media type: {content.media_type} for now")
                case "uri":
                    if content.has_top_level_media_type("image"):
                        a_content.append({
                            "type": "image",
                            "source": {"type": "url", "url": content.uri},
                        })
                    else:
                        logger.debug(f"Ignoring unsupported data content media type: {content.media_type} for now")
                case "function_call":
                    a_content.append({
                        "type": "tool_use",
                        "id": content.call_id,
                        "name": content.name,
                        "input": content.parse_arguments(),
                    })
                case "function_result":
                    a_content.append({
                        "type": "tool_result",
                        "tool_use_id": content.call_id,
                        "content": prepare_function_call_results(content.result),
                        "is_error": content.exception is not None,
                    })
                case "text_reasoning":
                    a_content.append({"type": "thinking", "thinking": content.text})
                case _:
                    logger.debug(f"Ignoring unsupported content type: {content.type} for now")

        return {
            "role": ROLE_MAP.get(message.role, "user"),
            "content": a_content,
        }

    def _prepare_tools_for_anthropic(self, options: dict[str, Any]) -> dict[str, Any] | None:
        """Prepare tools and tool choice configuration for the Anthropic API request.

        Args:
            options: The options dict containing tools and tool choice settings.

        Returns:
            A dictionary with tools, mcp_servers, and tool_choice configuration, or None if empty.
        """
        from agent_framework._types import validate_tool_mode

        result: dict[str, Any] = {}
        tools = options.get("tools")

        # Process tools
        if tools:
            tool_list: list[MutableMapping[str, Any]] = []
            mcp_server_list: list[MutableMapping[str, Any]] = []
            for tool in tools:
                match tool:
                    case MutableMapping():
                        tool_list.append(tool)
                    case FunctionTool():
                        tool_list.append({
                            "type": "custom",
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.parameters(),
                        })
                    case HostedWebSearchTool():
                        search_tool: dict[str, Any] = {
                            "type": "web_search_20250305",
                            "name": "web_search",
                        }
                        if tool.additional_properties:
                            search_tool.update(tool.additional_properties)
                        tool_list.append(search_tool)
                    case HostedCodeInterpreterTool():
                        code_tool: dict[str, Any] = {
                            "type": "code_execution_20250825",
                            "name": "code_execution",
                        }
                        tool_list.append(code_tool)
                    case HostedMCPTool():
                        server_def: dict[str, Any] = {
                            "type": "url",
                            "name": tool.name,
                            "url": str(tool.url),
                        }
                        if tool.allowed_tools:
                            server_def["tool_configuration"] = {"allowed_tools": list(tool.allowed_tools)}
                        if tool.headers and (auth := tool.headers.get("authorization")):
                            server_def["authorization_token"] = auth
                        mcp_server_list.append(server_def)
                    case _:
                        logger.debug(f"Ignoring unsupported tool type: {type(tool)} for now")

            if tool_list:
                result["tools"] = tool_list
            if mcp_server_list:
                result["mcp_servers"] = mcp_server_list

        # Process tool choice
        if options.get("tool_choice") is None:
            return result or None
        tool_mode = validate_tool_mode(options.get("tool_choice"))
        allow_multiple = options.get("allow_multiple_tool_calls")
        match tool_mode.get("mode"):
            case "auto":
                tool_choice: dict[str, Any] = {"type": "auto"}
                if allow_multiple is not None:
                    tool_choice["disable_parallel_tool_use"] = not allow_multiple
                result["tool_choice"] = tool_choice
            case "required":
                if "required_function_name" in tool_mode:
                    tool_choice = {
                        "type": "tool",
                        "name": tool_mode["required_function_name"],
                    }
                else:
                    tool_choice = {"type": "any"}
                if allow_multiple is not None:
                    tool_choice["disable_parallel_tool_use"] = not allow_multiple
                result["tool_choice"] = tool_choice
            case "none":
                result["tool_choice"] = {"type": "none"}
            case _:
                logger.debug(f"Ignoring unsupported tool choice mode: {tool_mode} for now")

        return result or None

    # region Response Processing Methods

    def _process_message(self, message: BetaMessage, options: dict[str, Any]) -> ChatResponse:
        """Process the response from the Anthropic client.

        Args:
            message: The message returned by the Anthropic client.
            options: The options dict used for the request.

        Returns:
            A ChatResponse object containing the processed response.
        """
        return ChatResponse(
            response_id=message.id,
            messages=[
                ChatMessage(
                    role=Role.ASSISTANT,
                    contents=self._parse_contents_from_anthropic(message.content),
                    raw_representation=message,
                )
            ],
            usage_details=self._parse_usage_from_anthropic(message.usage),
            model_id=message.model,
            finish_reason=FINISH_REASON_MAP.get(message.stop_reason) if message.stop_reason else None,
            response_format=options.get("response_format"),
            raw_representation=message,
        )

    def _process_stream_event(self, event: BetaRawMessageStreamEvent) -> ChatResponseUpdate | None:
        """Process a streaming event from the Anthropic client.

        Args:
            event: The streaming event returned by the Anthropic client.

        Returns:
            A ChatResponseUpdate object containing the processed update.
        """
        match event.type:
            case "message_start":
                usage_details: list[Content] = []
                if event.message.usage and (details := self._parse_usage_from_anthropic(event.message.usage)):
                    usage_details.append(Content.from_usage(usage_details=details))

                return ChatResponseUpdate(
                    response_id=event.message.id,
                    contents=[
                        *self._parse_contents_from_anthropic(event.message.content),
                        *usage_details,
                    ],
                    model_id=event.message.model,
                    finish_reason=FINISH_REASON_MAP.get(event.message.stop_reason)
                    if event.message.stop_reason
                    else None,
                    raw_representation=event,
                )
            case "message_delta":
                usage = self._parse_usage_from_anthropic(event.usage)
                return ChatResponseUpdate(
                    contents=[Content.from_usage(usage_details=usage, raw_representation=event.usage)] if usage else [],
                    finish_reason=FINISH_REASON_MAP.get(event.delta.stop_reason) if event.delta.stop_reason else None,
                    raw_representation=event,
                )
            case "message_stop":
                logger.debug("Received message_stop event; no content to process.")
            case "content_block_start":
                contents = self._parse_contents_from_anthropic([event.content_block])
                return ChatResponseUpdate(
                    contents=contents,
                    raw_representation=event,
                )
            case "content_block_delta":
                contents = self._parse_contents_from_anthropic([event.delta])
                return ChatResponseUpdate(
                    contents=contents,
                    raw_representation=event,
                )
            case "content_block_stop":
                logger.debug("Received content_block_stop event; no content to process.")
            case _:
                logger.debug(f"Ignoring unsupported event type: {event.type}")
        return None

    def _parse_usage_from_anthropic(self, usage: BetaUsage | BetaMessageDeltaUsage | None) -> UsageDetails | None:
        """Parse usage details from the Anthropic message usage."""
        if not usage:
            return None
        usage_details = UsageDetails(output_token_count=usage.output_tokens)
        if usage.input_tokens is not None:
            usage_details["input_token_count"] = usage.input_tokens
        if usage.cache_creation_input_tokens is not None:
            usage_details["anthropic.cache_creation_input_tokens"] = usage.cache_creation_input_tokens  # type: ignore[typeddict-unknown-key]
        if usage.cache_read_input_tokens is not None:
            usage_details["anthropic.cache_read_input_tokens"] = usage.cache_read_input_tokens  # type: ignore[typeddict-unknown-key]
        return usage_details

    def _parse_contents_from_anthropic(
        self,
        content: Sequence[BetaContentBlock | BetaRawContentBlockDelta | BetaTextBlock],
    ) -> list[Content]:
        """Parse contents from the Anthropic message."""
        contents: list[Content] = []
        for content_block in content:
            match content_block.type:
                case "text" | "text_delta":
                    contents.append(
                        Content.from_text(
                            text=content_block.text,
                            raw_representation=content_block,
                            annotations=self._parse_citations_from_anthropic(content_block),
                        )
                    )
                case "tool_use" | "mcp_tool_use" | "server_tool_use":
                    self._last_call_id_name = (content_block.id, content_block.name)
                    if content_block.type == "mcp_tool_use":
                        contents.append(
                            Content.from_mcp_server_tool_call(
                                call_id=content_block.id,
                                tool_name=content_block.name,
                                server_name=None,
                                arguments=content_block.input,
                                raw_representation=content_block,
                            )
                        )
                    elif "code_execution" in (content_block.name or ""):
                        contents.append(
                            Content.from_code_interpreter_tool_call(
                                call_id=content_block.id,
                                inputs=[
                                    Content.from_text(
                                        text=str(content_block.input),
                                        raw_representation=content_block,
                                    )
                                ],
                                raw_representation=content_block,
                            )
                        )
                    else:
                        contents.append(
                            Content.from_function_call(
                                call_id=content_block.id,
                                name=content_block.name,
                                arguments=content_block.input,
                                raw_representation=content_block,
                            )
                        )
                case "mcp_tool_result":
                    call_id, _ = self._last_call_id_name or (None, None)
                    parsed_output: list[Content] | None = None
                    if content_block.content:
                        if isinstance(content_block.content, list):
                            parsed_output = self._parse_contents_from_anthropic(content_block.content)
                        elif isinstance(content_block.content, (str, bytes)):
                            parsed_output = [
                                Content.from_text(
                                    text=str(content_block.content),
                                    raw_representation=content_block,
                                )
                            ]
                        else:
                            parsed_output = self._parse_contents_from_anthropic([content_block.content])
                    contents.append(
                        Content.from_mcp_server_tool_result(
                            call_id=content_block.tool_use_id,
                            output=parsed_output,
                            raw_representation=content_block,
                        )
                    )
                case "web_search_tool_result" | "web_fetch_tool_result":
                    call_id, _ = self._last_call_id_name or (None, None)
                    contents.append(
                        Content.from_function_result(
                            call_id=content_block.tool_use_id,
                            result=content_block.content,
                            raw_representation=content_block,
                        )
                    )
                case "code_execution_tool_result":
                    code_outputs: list[Content] = []
                    if content_block.content:
                        if isinstance(content_block.content, BetaCodeExecutionToolResultError):
                            code_outputs.append(
                                Content.from_error(
                                    message=content_block.content.error_code,
                                    raw_representation=content_block.content,
                                )
                            )
                        else:
                            if content_block.content.stdout:
                                code_outputs.append(
                                    Content.from_text(
                                        text=content_block.content.stdout,
                                        raw_representation=content_block.content,
                                    )
                                )
                            if content_block.content.stderr:
                                code_outputs.append(
                                    Content.from_error(
                                        message=content_block.content.stderr,
                                        raw_representation=content_block.content,
                                    )
                                )
                            for code_file_content in content_block.content.content:
                                code_outputs.append(
                                    Content.from_hosted_file(
                                        file_id=code_file_content.file_id,
                                        raw_representation=code_file_content,
                                    )
                                )
                    contents.append(
                        Content.from_code_interpreter_tool_result(
                            call_id=content_block.tool_use_id,
                            raw_representation=content_block,
                            outputs=code_outputs,
                        )
                    )
                case "bash_code_execution_tool_result":
                    bash_outputs: list[Content] = []
                    if content_block.content:
                        if isinstance(
                            content_block.content,
                            BetaBashCodeExecutionToolResultError,
                        ):
                            bash_outputs.append(
                                Content.from_error(
                                    message=content_block.content.error_code,
                                    raw_representation=content_block.content,
                                )
                            )
                        else:
                            if content_block.content.stdout:
                                bash_outputs.append(
                                    Content.from_text(
                                        text=content_block.content.stdout,
                                        raw_representation=content_block.content,
                                    )
                                )
                            if content_block.content.stderr:
                                bash_outputs.append(
                                    Content.from_error(
                                        message=content_block.content.stderr,
                                        raw_representation=content_block.content,
                                    )
                                )
                            for bash_file_content in content_block.content.content:
                                contents.append(
                                    Content.from_hosted_file(
                                        file_id=bash_file_content.file_id,
                                        raw_representation=bash_file_content,
                                    )
                                )
                    contents.append(
                        Content.from_function_result(
                            call_id=content_block.tool_use_id,
                            result=bash_outputs,
                            raw_representation=content_block,
                        )
                    )
                case "text_editor_code_execution_tool_result":
                    text_editor_outputs: list[Content] = []
                    match content_block.content.type:
                        case "text_editor_code_execution_tool_result_error":
                            text_editor_outputs.append(
                                Content.from_error(
                                    message=content_block.content.error_code
                                    and getattr(content_block.content, "error_message", ""),
                                    raw_representation=content_block.content,
                                )
                            )
                        case "text_editor_code_execution_view_result":
                            annotations = (
                                [
                                    Annotation(
                                        type="citation",
                                        raw_representation=content_block.content,
                                        annotated_regions=[
                                            TextSpanRegion(
                                                type="text_span",
                                                start_index=content_block.content.start_line,
                                                end_index=content_block.content.start_line
                                                + (content_block.content.num_lines or 0),
                                            )
                                        ],
                                    )
                                ]
                                if content_block.content.num_lines is not None
                                and content_block.content.start_line is not None
                                else None
                            )
                            text_editor_outputs.append(
                                Content.from_text(
                                    text=content_block.content.content,
                                    annotations=annotations,
                                    raw_representation=content_block.content,
                                )
                            )
                        case "text_editor_code_execution_str_replace_result":
                            old_annotation = (
                                Annotation(
                                    type="citation",
                                    raw_representation=content_block.content,
                                    annotated_regions=[
                                        TextSpanRegion(
                                            type="text_span",
                                            start_index=content_block.content.old_start or 0,
                                            end_index=(
                                                (content_block.content.old_start or 0)
                                                + (content_block.content.old_lines or 0)
                                            ),
                                        )
                                    ],
                                )
                                if content_block.content.old_lines is not None
                                and content_block.content.old_start is not None
                                else None
                            )
                            new_annotation = (
                                Annotation(
                                    type="citation",
                                    raw_representation=content_block.content,
                                    snippet="\n".join(content_block.content.lines)  # type: ignore[typeddict-item]
                                    if content_block.content.lines
                                    else None,
                                    annotated_regions=[
                                        TextSpanRegion(
                                            type="text_span",
                                            start_index=content_block.content.new_start or 0,
                                            end_index=(
                                                (content_block.content.new_start or 0)
                                                + (content_block.content.new_lines or 0)
                                            ),
                                        )
                                    ],
                                )
                                if content_block.content.new_lines is not None
                                and content_block.content.new_start is not None
                                else None
                            )
                            annotations = [ann for ann in [old_annotation, new_annotation] if ann is not None]

                            text_editor_outputs.append(
                                Content.from_text(
                                    text=(
                                        "\n".join(content_block.content.lines) if content_block.content.lines else ""
                                    ),
                                    annotations=annotations or None,
                                    raw_representation=content_block.content,
                                )
                            )
                        case "text_editor_code_execution_create_result":
                            text_editor_outputs.append(
                                Content.from_text(
                                    text=f"File update: {content_block.content.is_file_update}",
                                    raw_representation=content_block.content,
                                )
                            )
                    contents.append(
                        Content.from_function_result(
                            call_id=content_block.tool_use_id,
                            result=text_editor_outputs,
                            raw_representation=content_block,
                        )
                    )
                case "input_json_delta":
                    # For streaming argument deltas, only pass call_id and arguments.
                    # Pass empty string for name - it causes ag-ui to emit duplicate ToolCallStartEvents
                    # since it triggers on `if content.name:`. The initial tool_use event already
                    # provides the name, so deltas should only carry incremental arguments.
                    # This matches OpenAI's behavior where streaming chunks have name="".
                    call_id, _name = self._last_call_id_name if self._last_call_id_name else ("", "")
                    contents.append(
                        Content.from_function_call(
                            call_id=call_id,
                            name="",
                            arguments=content_block.partial_json,
                            raw_representation=content_block,
                        )
                    )
                case "thinking" | "thinking_delta":
                    contents.append(
                        Content.from_text_reasoning(
                            text=content_block.thinking,
                            raw_representation=content_block,
                        )
                    )
                case _:
                    logger.debug(f"Ignoring unsupported content type: {content_block.type} for now")
        return contents

    def _parse_citations_from_anthropic(
        self, content_block: BetaContentBlock | BetaRawContentBlockDelta | BetaTextBlock
    ) -> list[Annotation] | None:
        content_blocks = getattr(content_block, "citations", None)
        if not content_blocks:
            return None
        annotations: list[Annotation] = []
        for citation in content_blocks:
            cit = Annotation(type="citation", raw_representation=citation)
            match citation.type:
                case "char_location":
                    cit["title"] = citation.title
                    cit["snippet"] = citation.cited_text
                    if citation.file_id:
                        cit["file_id"] = citation.file_id
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_char_index,
                            end_index=citation.end_char_index,
                        )
                    )
                case "page_location":
                    cit["title"] = citation.document_title
                    cit["snippet"] = citation.cited_text
                    if citation.file_id:
                        cit["file_id"] = citation.file_id
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_page_number,
                            end_index=citation.end_page_number,
                        )
                    )
                case "content_block_location":
                    cit["title"] = citation.document_title
                    cit["snippet"] = citation.cited_text
                    if citation.file_id:
                        cit["file_id"] = citation.file_id
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_block_index,
                            end_index=citation.end_block_index,
                        )
                    )
                case "web_search_result_location":
                    cit["title"] = citation.title
                    cit["snippet"] = citation.cited_text
                    cit["url"] = citation.url
                case "search_result_location":
                    cit["title"] = citation.title
                    cit["snippet"] = citation.cited_text
                    cit["url"] = citation.source
                    cit.setdefault("annotated_regions", [])
                    cit["annotated_regions"].append(  # type: ignore[attr-defined]
                        TextSpanRegion(
                            type="text_span",
                            start_index=citation.start_block_index,
                            end_index=citation.end_block_index,
                        )
                    )
                case _:
                    logger.debug(f"Unknown citation type encountered: {citation.type}")
            annotations.append(cit)
        return annotations or None

    def service_url(self) -> str:
        """Get the service URL for the chat client.

        Returns:
            The service URL for the chat client, or None if not set.
        """
        return str(self.anthropic_client.base_url)
