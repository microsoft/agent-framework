# Copyright (c) Microsoft. All rights reserved.

"""Deprecated Azure OpenAI client classes.

All classes in this module are deprecated and will be removed in a future release.
Migrate to the ``agent_framework_openai`` package equivalents with an ``AsyncAzureOpenAI`` client,
or use ``FoundryChatClient`` for Azure AI Foundry projects.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from copy import copy
from typing import TYPE_CHECKING, Any, ClassVar, Final, Generic, cast
from urllib.parse import urljoin, urlparse

from agent_framework._middleware import ChatMiddlewareLayer
from agent_framework._settings import SecretString, load_settings
from agent_framework._telemetry import AGENT_FRAMEWORK_USER_AGENT, APP_INFO, prepend_agent_framework_to_user_agent
from agent_framework._tools import FunctionInvocationConfiguration, FunctionInvocationLayer
from agent_framework._types import Annotation, Content
from agent_framework.observability import ChatTelemetryLayer, EmbeddingTelemetryLayer
from agent_framework_openai._assistants_client import (
    OpenAIAssistantsClient,  # type: ignore[reportDeprecated]
    OpenAIAssistantsOptions,
)
from agent_framework_openai._chat_client import OpenAIChatOptions, RawOpenAIChatClient
from agent_framework_openai._chat_completion_client import OpenAIChatCompletionOptions, RawOpenAIChatCompletionClient
from agent_framework_openai._embedding_client import OpenAIEmbeddingOptions, RawOpenAIEmbeddingClient
from agent_framework_openai._shared import OpenAIBase
from azure.ai.projects.aio import AIProjectClient
from openai import AsyncOpenAI
from openai.lib.azure import AsyncAzureOpenAI
from pydantic import BaseModel

from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider, resolve_credential_to_token_provider

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
    from warnings import deprecated  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar, deprecated  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._middleware import MiddlewareTypes
    from openai.types.chat.chat_completion import Choice
    from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice

logger: logging.Logger = logging.getLogger(__name__)


# region Constants and Settings

DEFAULT_AZURE_API_VERSION: Final[str] = "2024-10-21"
DEFAULT_AZURE_TOKEN_ENDPOINT: Final[str] = "https://cognitiveservices.azure.com/.default"  # noqa: S105


class AzureOpenAISettings(TypedDict, total=False):
    """AzureOpenAI model settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'AZURE_OPENAI_'. If settings are missing after resolution, validation will fail.

    Keyword Args:
        endpoint: The endpoint of the Azure deployment.
        chat_deployment_name: The name of the Azure Chat deployment.
        responses_deployment_name: The name of the Azure Responses deployment.
        embedding_deployment_name: The name of the Azure Embedding deployment.
        api_key: The API key for the Azure deployment.
        api_version: The API version to use.
        base_url: The url of the Azure deployment.
        token_endpoint: The token endpoint to use to retrieve the authentication token.
    """

    chat_deployment_name: str | None
    responses_deployment_name: str | None
    embedding_deployment_name: str | None
    endpoint: str | None
    base_url: str | None
    api_key: SecretString | None
    api_version: str | None
    token_endpoint: str | None


def _apply_azure_defaults(
    settings: AzureOpenAISettings,
    default_api_version: str = DEFAULT_AZURE_API_VERSION,
    default_token_endpoint: str = DEFAULT_AZURE_TOKEN_ENDPOINT,
) -> None:
    """Apply default values for api_version and token_endpoint after loading settings.

    Args:
        settings: The loaded Azure OpenAI settings dict.
        default_api_version: The default API version to use if not set.
        default_token_endpoint: The default token endpoint to use if not set.
    """
    if not settings.get("api_version"):
        settings["api_version"] = default_api_version
    if not settings.get("token_endpoint"):
        settings["token_endpoint"] = default_token_endpoint


@contextmanager
def _prefer_single_azure_endpoint_env(*, endpoint: str | None, base_url: str | None) -> Any:
    """Preserve the legacy call shape without mutating process-wide environment state."""
    yield


# endregion


# region AzureOpenAIConfigMixin


class AzureOpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an Azure OpenAI service."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.openai"

    def __init__(
        self,
        deployment_name: str,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str = DEFAULT_AZURE_API_VERSION,
        api_key: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Configure a connection to an Azure OpenAI service.

        Args:
            deployment_name: Name of the deployment.
            endpoint: The specific endpoint URL for the deployment.
            base_url: The base URL for Azure services.
            api_version: Azure API version.
            api_key: API key for Azure services.
            token_endpoint: Azure AD token scope.
            credential: Azure credential or token provider for authentication.
            default_headers: Default headers for HTTP requests.
            client: An existing client to use.
            instruction_role: The role to use for 'instruction' messages.
            kwargs: Additional keyword arguments.
        """
        merged_headers = dict(copy(default_headers)) if default_headers else {}
        if APP_INFO:
            merged_headers.update(APP_INFO)
            merged_headers = prepend_agent_framework_to_user_agent(merged_headers)
        if not client:
            ad_token_provider = None
            if not api_key and credential:
                ad_token_provider = resolve_credential_to_token_provider(credential, token_endpoint)

            if not api_key and not ad_token_provider:
                raise ValueError("Please provide either api_key, credential, or a client.")

            if not endpoint and not base_url:
                raise ValueError("Please provide an endpoint or a base_url")

            args: dict[str, Any] = {
                "default_headers": merged_headers,
            }
            if api_version:
                args["api_version"] = api_version
            if ad_token_provider:
                args["azure_ad_token_provider"] = ad_token_provider
            if api_key:
                args["api_key"] = api_key
            if base_url:
                args["base_url"] = str(base_url)
            if endpoint and not base_url:
                args["azure_endpoint"] = str(endpoint)
            if deployment_name:
                args["azure_deployment"] = deployment_name
            if "websocket_base_url" in kwargs:
                args["websocket_base_url"] = kwargs.pop("websocket_base_url")

            client = AsyncAzureOpenAI(**args)

        self.endpoint = str(endpoint)
        self.base_url = str(base_url)
        self.api_version = api_version
        self.deployment_name = deployment_name
        self.instruction_role = instruction_role
        if default_headers:
            from agent_framework._telemetry import USER_AGENT_KEY

            def_headers = {k: v for k, v in default_headers.items() if k != USER_AGENT_KEY}
        else:
            def_headers = None
        self.default_headers = def_headers

        super().__init__(model_id=deployment_name, client=client, **kwargs)


# endregion


# region AzureOpenAIResponsesClient


AzureOpenAIResponsesOptionsT = TypeVar(
    "AzureOpenAIResponsesOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIChatOptions",
    covariant=True,
)

AzureOpenAIResponsesOptions = OpenAIChatOptions


@deprecated(
    "AzureOpenAIResponsesClient is deprecated. "
    "Use OpenAIChatClient with an AsyncAzureOpenAI client, or FoundryChatClient for Foundry projects."
)
class AzureOpenAIResponsesClient(  # type: ignore[misc]
    FunctionInvocationLayer[AzureOpenAIResponsesOptionsT],
    ChatMiddlewareLayer[AzureOpenAIResponsesOptionsT],
    ChatTelemetryLayer[AzureOpenAIResponsesOptionsT],
    RawOpenAIChatClient[AzureOpenAIResponsesOptionsT],
    Generic[AzureOpenAIResponsesOptionsT],
):
    """Deprecated Azure Responses client. Use OpenAIChatClient with an AsyncAzureOpenAI client instead."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        project_client: Any | None = None,
        project_endpoint: str | None = None,
        allow_preview: bool | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure OpenAI Responses client.

        Keyword Args:
            api_key: The API key.
            deployment_name: The deployment name.
            endpoint: The deployment endpoint.
            base_url: The deployment base URL.
            api_version: The deployment API version.
            token_endpoint: The token endpoint to request an Azure token.
            credential: Azure credential or token provider for authentication.
            default_headers: Default headers for HTTP requests.
            async_client: An existing client to use.
            project_client: An existing AIProjectClient to use.
            project_endpoint: The Azure AI Foundry project endpoint URL.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            instruction_role: The role to use for 'instruction' messages.
            middleware: Optional sequence of middleware.
            function_invocation_configuration: Optional function invocation configuration.
            kwargs: Additional keyword arguments.
        """
        if (model_id := kwargs.pop("model_id", None)) and not deployment_name:
            deployment_name = str(model_id)

        if async_client is None and (project_client is not None or project_endpoint is not None):
            async_client = self._create_client_from_project(
                project_client=project_client,
                project_endpoint=project_endpoint,
                credential=credential,
                allow_preview=allow_preview,
            )

        azure_openai_settings = load_settings(
            AzureOpenAISettings,
            env_prefix="AZURE_OPENAI_",
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            responses_deployment_name=deployment_name,
            api_version=api_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            token_endpoint=token_endpoint,
        )
        _apply_azure_defaults(azure_openai_settings, default_api_version="preview")
        endpoint_value = azure_openai_settings.get("endpoint")
        if (
            not azure_openai_settings.get("base_url")
            and endpoint_value
            and (hostname := urlparse(str(endpoint_value)).hostname)
            and hostname.endswith(".openai.azure.com")
        ):
            azure_openai_settings["base_url"] = urljoin(str(endpoint_value), "/openai/v1/")

        responses_deployment_name = azure_openai_settings.get("responses_deployment_name")
        if not responses_deployment_name:
            raise ValueError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME' environment variable."
            )

        endpoint_value = azure_openai_settings.get("endpoint")
        client_base_url = azure_openai_settings.get("base_url")
        if not async_client:
            # Create the Azure OpenAI client directly
            merged_headers = dict(copy(default_headers)) if default_headers else {}
            if APP_INFO:
                merged_headers.update(APP_INFO)
                merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

            api_key_secret = azure_openai_settings.get("api_key")
            ad_token_provider = None
            if not api_key_secret and credential:
                ad_token_provider = resolve_credential_to_token_provider(
                    credential, azure_openai_settings.get("token_endpoint")
                )

            if not api_key_secret and not ad_token_provider:
                raise ValueError("Please provide either api_key, credential, or a client.")

            if not endpoint_value and not client_base_url:
                raise ValueError("Please provide an endpoint or a base_url")

            client_args: dict[str, Any] = {"default_headers": merged_headers}
            if resolved_api_version := azure_openai_settings.get("api_version"):
                client_args["api_version"] = resolved_api_version
            if ad_token_provider:
                client_args["azure_ad_token_provider"] = ad_token_provider
            if api_key_secret:
                client_args["api_key"] = api_key_secret.get_secret_value()
            if client_base_url:
                client_args["base_url"] = str(client_base_url)
            if endpoint_value and not client_base_url:
                client_args["azure_endpoint"] = str(endpoint_value)
            if responses_deployment_name:
                client_args["azure_deployment"] = responses_deployment_name
            if "websocket_base_url" in kwargs:
                client_args["websocket_base_url"] = kwargs.pop("websocket_base_url")

            async_client = AsyncAzureOpenAI(**client_args)

        # Store Azure-specific attributes for serialization
        self.endpoint = str(endpoint_value) if endpoint_value else None
        self.api_version = azure_openai_settings.get("api_version") or ""
        self.deployment_name = responses_deployment_name

        with _prefer_single_azure_endpoint_env(endpoint=endpoint_value, base_url=client_base_url):
            super().__init__(
                async_client=async_client,
                model=responses_deployment_name,
                azure_endpoint=str(endpoint_value) if endpoint_value else None,
                base_url=str(client_base_url) if client_base_url else None,
                api_version=azure_openai_settings.get("api_version"),
                instruction_role=instruction_role,
                default_headers=default_headers,
                middleware=middleware,  # type: ignore[arg-type]
                function_invocation_configuration=function_invocation_configuration,
                **kwargs,
            )

    @staticmethod
    def _create_client_from_project(
        *,
        project_client: AIProjectClient | None,
        project_endpoint: str | None,
        credential: AzureCredentialTypes | AzureTokenProvider | None,
        allow_preview: bool | None = None,
    ) -> AsyncOpenAI:
        """Create an AsyncOpenAI client from an Azure AI Foundry project."""
        if project_client is not None:
            return project_client.get_openai_client()

        if not project_endpoint:
            raise ValueError("Azure AI project endpoint is required when project_client is not provided.")
        if not credential:
            raise ValueError("Azure credential is required when using project_endpoint without a project_client.")
        project_client_kwargs: dict[str, Any] = {
            "endpoint": project_endpoint,
            "credential": credential,  # type: ignore[arg-type]
            "user_agent": AGENT_FRAMEWORK_USER_AGENT,
        }
        if allow_preview is not None:
            project_client_kwargs["allow_preview"] = allow_preview
        project_client = AIProjectClient(**project_client_kwargs)
        return project_client.get_openai_client()

    @override
    def _check_model_presence(self, options: dict[str, Any]) -> None:
        if not options.get("model"):
            if not self.model:
                raise ValueError("deployment_name must be a non-empty string")
            options["model"] = self.model


# endregion


# region AzureOpenAIChatClient


ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


class AzureUserSecurityContext(TypedDict, total=False):
    """User security context for Azure AI applications.

    These fields help security operations teams investigate and mitigate security
    incidents by providing context about the application and end user.
    """

    application_name: str
    """Name of the application making the request."""

    end_user_id: str
    """Unique identifier for the end user (recommend hashing username/email)."""

    end_user_tenant_id: str
    """Microsoft 365 tenant ID the end user belongs to. Required for multi-tenant apps."""

    source_ip: str
    """The original client's IP address."""


class AzureOpenAIChatOptions(OpenAIChatCompletionOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """Azure OpenAI-specific chat options dict.

    Extends OpenAIChatCompletionOptions with Azure-specific options including
    the "On Your Data" feature and enhanced security context.
    """

    data_sources: list[dict[str, Any]]
    """Azure "On Your Data" data sources for retrieval-augmented generation."""

    user_security_context: AzureUserSecurityContext
    """Enhanced security context for Azure Defender integration."""

    n: int
    """Number of chat completion choices to generate for each input message."""


AzureOpenAIChatOptionsT = TypeVar(
    "AzureOpenAIChatOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AzureOpenAIChatOptions",
    covariant=True,
)


@deprecated("AzureOpenAIChatClient is deprecated. Use OpenAIChatCompletionClient with an AsyncAzureOpenAI client.")
class AzureOpenAIChatClient(  # type: ignore[misc]
    FunctionInvocationLayer[AzureOpenAIChatOptionsT],
    ChatMiddlewareLayer[AzureOpenAIChatOptionsT],
    ChatTelemetryLayer[AzureOpenAIChatOptionsT],
    RawOpenAIChatCompletionClient[AzureOpenAIChatOptionsT],
    Generic[AzureOpenAIChatOptionsT],
):
    """Deprecated Azure OpenAI Chat client. Use OpenAIChatCompletionClient with AsyncAzureOpenAI instead."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        additional_properties: dict[str, Any] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    ) -> None:
        """Initialize an Azure OpenAI Chat completion client.

        Keyword Args:
            api_key: The API key.
            deployment_name: The deployment name.
            endpoint: The deployment endpoint.
            base_url: The deployment base URL.
            api_version: The deployment API version.
            token_endpoint: The token endpoint to request an Azure token.
            credential: Azure credential or token provider for authentication.
            default_headers: Default headers for HTTP requests.
            async_client: An existing client to use.
            additional_properties: Additional properties stored on the client instance.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            instruction_role: The role to use for 'instruction' messages.
            middleware: Optional sequence of middleware.
            function_invocation_configuration: Optional function invocation configuration.
        """
        azure_openai_settings = load_settings(
            AzureOpenAISettings,
            env_prefix="AZURE_OPENAI_",
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            chat_deployment_name=deployment_name,
            api_version=api_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            token_endpoint=token_endpoint,
        )
        _apply_azure_defaults(azure_openai_settings)

        chat_deployment_name = azure_openai_settings.get("chat_deployment_name")
        if not chat_deployment_name:
            raise ValueError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME' environment variable."
            )

        endpoint_value = azure_openai_settings.get("endpoint")
        base_url_value = azure_openai_settings.get("base_url")
        if not async_client:
            # Create the Azure OpenAI client directly
            merged_headers = dict(copy(default_headers)) if default_headers else {}
            if APP_INFO:
                merged_headers.update(APP_INFO)
                merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

            api_key_secret = azure_openai_settings.get("api_key")
            ad_token_provider = None
            if not api_key_secret and credential:
                ad_token_provider = resolve_credential_to_token_provider(
                    credential, azure_openai_settings.get("token_endpoint")
                )

            if not api_key_secret and not ad_token_provider:
                raise ValueError("Please provide either api_key, credential, or a client.")

            if not endpoint_value and not base_url_value:
                raise ValueError("Please provide an endpoint or a base_url")

            client_args: dict[str, Any] = {"default_headers": merged_headers}
            if resolved_api_version := azure_openai_settings.get("api_version"):
                client_args["api_version"] = resolved_api_version
            if ad_token_provider:
                client_args["azure_ad_token_provider"] = ad_token_provider
            if api_key_secret:
                client_args["api_key"] = api_key_secret.get_secret_value()
            if base_url_value:
                client_args["base_url"] = str(base_url_value)
            if endpoint_value and not base_url_value:
                client_args["azure_endpoint"] = str(endpoint_value)
            if chat_deployment_name:
                client_args["azure_deployment"] = chat_deployment_name

            async_client = AsyncAzureOpenAI(**client_args)

        # Store Azure-specific attributes for serialization
        self.endpoint = str(azure_openai_settings.get("endpoint") or "")
        self.api_version = azure_openai_settings.get("api_version") or ""
        self.deployment_name = chat_deployment_name

        with _prefer_single_azure_endpoint_env(endpoint=endpoint_value, base_url=base_url_value):
            super().__init__(
                async_client=async_client,
                model=chat_deployment_name,
                azure_endpoint=str(endpoint_value) if endpoint_value else None,
                base_url=str(base_url_value) if base_url_value else None,
                api_version=azure_openai_settings.get("api_version"),
                instruction_role=instruction_role,
                default_headers=default_headers,
                additional_properties=additional_properties,
                middleware=middleware,  # type: ignore[arg-type]
                function_invocation_configuration=function_invocation_configuration,
            )

    @override
    def _parse_text_from_openai(self, choice: Choice | ChunkChoice) -> Content | None:
        """Parse the choice into a Content object with type='text'.

        Overwritten from RawOpenAIChatCompletionClient to deal with Azure On Your Data function.
        """
        message = getattr(choice, "message", None)
        if message is None:
            message = getattr(choice, "delta", None)
        if message is None:  # type: ignore
            return None
        if hasattr(message, "refusal") and message.refusal:
            return Content.from_text(text=message.refusal, raw_representation=choice)
        if not message.content:
            return None
        text_content = Content.from_text(text=message.content, raw_representation=choice)
        if not message.model_extra or "context" not in message.model_extra:
            return text_content

        context_raw: object = cast(object, message.context)  # type: ignore[union-attr]
        if isinstance(context_raw, str):
            try:
                context_raw = json.loads(context_raw)
            except json.JSONDecodeError:
                logger.warning("Context is not a valid JSON string, ignoring context.")
                return text_content
        if not isinstance(context_raw, dict):
            logger.warning("Context is not a valid dictionary, ignoring context.")
            return text_content
        context = cast(dict[str, Any], context_raw)
        if intent := context.get("intent"):
            text_content.additional_properties = {"intent": intent}
        citations = context.get("citations")
        if isinstance(citations, list) and citations:
            annotations: list[Annotation] = []
            for citation_raw in cast(list[object], citations):
                if not isinstance(citation_raw, dict):
                    continue
                citation = cast(dict[str, Any], citation_raw)
                annotations.append(
                    Annotation(
                        type="citation",
                        title=citation.get("title", ""),
                        url=citation.get("url", ""),
                        snippet=citation.get("content", ""),
                        file_id=citation.get("filepath", ""),
                        tool_name="Azure-on-your-Data",
                        additional_properties={"chunk_id": citation.get("chunk_id", "")},
                        raw_representation=citation,
                    )
                )
            text_content.annotations = annotations
        return text_content


# endregion


# region AzureOpenAIAssistantsClient


AzureOpenAIAssistantsOptionsT = TypeVar(
    "AzureOpenAIAssistantsOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIAssistantsOptions",
    covariant=True,
)

AzureOpenAIAssistantsOptions = OpenAIAssistantsOptions


@deprecated(
    "AzureOpenAIAssistantsClient is deprecated. "
    "Use OpenAIAssistantsClient (also deprecated) or migrate to OpenAIChatClient."
)
class AzureOpenAIAssistantsClient(
    OpenAIAssistantsClient[AzureOpenAIAssistantsOptionsT],  # type: ignore[reportDeprecated]
    Generic[AzureOpenAIAssistantsOptionsT],
):
    """Deprecated Azure OpenAI Assistants client. Use OpenAIAssistantsClient or migrate to OpenAIChatClient."""

    DEFAULT_AZURE_API_VERSION: ClassVar[str] = "2024-05-01-preview"

    def __init__(
        self,
        *,
        deployment_name: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        assistant_description: str | None = None,
        thread_id: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Azure OpenAI Assistants client.

        Keyword Args:
            deployment_name: The Azure OpenAI deployment name.
            assistant_id: The ID of an Azure OpenAI assistant to use.
            assistant_name: The name to use when creating new assistants.
            assistant_description: The description to use when creating new assistants.
            thread_id: Default thread ID to use for conversations.
            api_key: The API key to use.
            endpoint: The deployment endpoint.
            base_url: The deployment base URL.
            api_version: The deployment API version.
            token_endpoint: The token endpoint to request an Azure token.
            credential: Azure credential or token provider for authentication.
            default_headers: Default headers for HTTP requests.
            async_client: An existing client to use.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
        """
        azure_openai_settings = load_settings(
            AzureOpenAISettings,
            env_prefix="AZURE_OPENAI_",
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            chat_deployment_name=deployment_name,
            api_version=api_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            token_endpoint=token_endpoint,
        )
        _apply_azure_defaults(azure_openai_settings, default_api_version=self.DEFAULT_AZURE_API_VERSION)

        chat_deployment_name = azure_openai_settings.get("chat_deployment_name")
        if not chat_deployment_name:
            raise ValueError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME' environment variable."
            )

        api_key_secret = azure_openai_settings.get("api_key")
        token_scope = azure_openai_settings.get("token_endpoint")

        ad_token_provider = None
        if not async_client and not api_key_secret and credential:
            ad_token_provider = resolve_credential_to_token_provider(credential, token_scope)

        if not async_client and not api_key_secret and not ad_token_provider:
            raise ValueError("Please provide either api_key, credential, or a client.")

        if not async_client:
            client_params: dict[str, Any] = {
                "default_headers": default_headers,
            }
            if resolved_api_version := azure_openai_settings.get("api_version"):
                client_params["api_version"] = resolved_api_version

            if api_key_secret:
                client_params["api_key"] = api_key_secret.get_secret_value()
            elif ad_token_provider:
                client_params["azure_ad_token_provider"] = ad_token_provider

            if resolved_base_url := azure_openai_settings.get("base_url"):
                client_params["base_url"] = str(resolved_base_url)
            elif resolved_endpoint := azure_openai_settings.get("endpoint"):
                client_params["azure_endpoint"] = str(resolved_endpoint)

            async_client = AsyncAzureOpenAI(**client_params)

        super().__init__(
            model_id=chat_deployment_name,
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            assistant_description=assistant_description,
            thread_id=thread_id,
            async_client=async_client,  # type: ignore[reportArgumentType]
            default_headers=default_headers,
        )


# endregion


# region AzureOpenAIEmbeddingClient


AzureOpenAIEmbeddingOptionsT = TypeVar(
    "AzureOpenAIEmbeddingOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIEmbeddingOptions",
    covariant=True,
)


@deprecated("AzureOpenAIEmbeddingClient is deprecated. Use OpenAIEmbeddingClient with an AsyncAzureOpenAI client.")
class AzureOpenAIEmbeddingClient(
    EmbeddingTelemetryLayer[str, list[float], AzureOpenAIEmbeddingOptionsT],
    RawOpenAIEmbeddingClient[AzureOpenAIEmbeddingOptionsT],
    Generic[AzureOpenAIEmbeddingOptionsT],
):
    """Deprecated Azure OpenAI embedding client. Use OpenAIEmbeddingClient with AsyncAzureOpenAI instead."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        token_endpoint: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        otel_provider_name: str | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Azure OpenAI embedding client.

        Keyword Args:
            api_key: The API key.
            deployment_name: The deployment name.
            endpoint: The deployment endpoint.
            base_url: The deployment base URL.
            api_version: The deployment API version.
            token_endpoint: The token endpoint to request an Azure token.
            credential: Azure credential or token provider for authentication.
            default_headers: Default headers for HTTP requests.
            async_client: An existing client to use.
            otel_provider_name: Override the OpenTelemetry provider name.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
        """
        azure_openai_settings = load_settings(
            AzureOpenAISettings,
            env_prefix="AZURE_OPENAI_",
            api_key=api_key,
            base_url=base_url,
            endpoint=endpoint,
            embedding_deployment_name=deployment_name,
            api_version=api_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            token_endpoint=token_endpoint,
        )
        _apply_azure_defaults(azure_openai_settings)

        embedding_deployment_name = azure_openai_settings.get("embedding_deployment_name")
        if not embedding_deployment_name:
            raise ValueError(
                "Azure OpenAI embedding deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME' environment variable."
            )

        endpoint_value = azure_openai_settings.get("endpoint")
        base_url_value = azure_openai_settings.get("base_url")
        if not async_client:
            # Create the Azure OpenAI client directly
            merged_headers = dict(copy(default_headers)) if default_headers else {}
            if APP_INFO:
                merged_headers.update(APP_INFO)
                merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

            api_key_secret = azure_openai_settings.get("api_key")
            ad_token_provider = None
            if not api_key_secret and credential:
                ad_token_provider = resolve_credential_to_token_provider(
                    credential, azure_openai_settings.get("token_endpoint")
                )

            if not api_key_secret and not ad_token_provider:
                raise ValueError("Please provide either api_key, credential, or a client.")

            if not endpoint_value and not base_url_value:
                raise ValueError("Please provide an endpoint or a base_url")

            client_args: dict[str, Any] = {"default_headers": merged_headers}
            if resolved_api_version := azure_openai_settings.get("api_version"):
                client_args["api_version"] = resolved_api_version
            if ad_token_provider:
                client_args["azure_ad_token_provider"] = ad_token_provider
            if api_key_secret:
                client_args["api_key"] = api_key_secret.get_secret_value()
            if base_url_value:
                client_args["base_url"] = str(base_url_value)
            if endpoint_value and not base_url_value:
                client_args["azure_endpoint"] = str(endpoint_value)
            if embedding_deployment_name:
                client_args["azure_deployment"] = embedding_deployment_name

            async_client = AsyncAzureOpenAI(**client_args)

        # Store Azure-specific attributes for serialization
        self.endpoint = str(azure_openai_settings.get("endpoint") or "")
        self.api_version = azure_openai_settings.get("api_version") or ""
        self.deployment_name = embedding_deployment_name

        with _prefer_single_azure_endpoint_env(endpoint=endpoint_value, base_url=base_url_value):
            super().__init__(
                async_client=async_client,
                model=embedding_deployment_name,
                azure_endpoint=str(endpoint_value) if endpoint_value else None,
                base_url=str(base_url_value) if base_url_value else None,
                api_version=azure_openai_settings.get("api_version"),
                default_headers=default_headers,
            )
        if otel_provider_name is not None:
            self.OTEL_PROVIDER_NAME = otel_provider_name  # type: ignore[misc]


# endregion
