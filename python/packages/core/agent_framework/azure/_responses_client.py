# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Generic
from urllib.parse import urljoin, urlparse

from azure.ai.projects.aio import AIProjectClient
from openai import AsyncOpenAI

from .._middleware import ChatMiddlewareLayer
from .._settings import load_settings
from .._telemetry import AGENT_FRAMEWORK_USER_AGENT
from .._tools import FunctionInvocationConfiguration, FunctionInvocationLayer
from ..observability import ChatTelemetryLayer
from ..openai._responses_client import RawOpenAIResponsesClient
from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider
from ._shared import (
    AzureOpenAIConfigMixin,
    AzureOpenAISettings,
    _apply_azure_defaults,
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from .._middleware import MiddlewareTypes
    from ..openai._responses_client import OpenAIResponsesOptions


AzureOpenAIResponsesOptionsT = TypeVar(
    "AzureOpenAIResponsesOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIResponsesOptions",
    covariant=True,
)


class AzureOpenAIResponsesClient(  # type: ignore[misc]
    AzureOpenAIConfigMixin,
    ChatMiddlewareLayer[AzureOpenAIResponsesOptionsT],
    FunctionInvocationLayer[AzureOpenAIResponsesOptionsT],
    ChatTelemetryLayer[AzureOpenAIResponsesOptionsT],
    RawOpenAIResponsesClient[AzureOpenAIResponsesOptionsT],
    Generic[AzureOpenAIResponsesOptionsT],
):
    """Azure Responses completion class with middleware, telemetry, and function invocation support."""

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
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure OpenAI Responses client.

        The client can be created in two ways:

        1. **Direct Azure OpenAI** (default): Provide endpoint, api_key, or credential
           to connect directly to an Azure OpenAI deployment.
        2. **Foundry project endpoint**: Provide a ``project_client`` or ``project_endpoint``
           (with ``credential``) to create the client via an Azure AI Foundry project.
           This requires the ``azure-ai-projects`` package to be installed.

        Keyword Args:
            api_key: The API key. If provided, will override the value in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_API_KEY.
            deployment_name: The deployment name. If provided, will override the value
                (responses_deployment_name) in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME.
            endpoint: The deployment endpoint. If provided will override the value
                in the env vars or .env file.
                Can also be set via environment variable AZURE_OPENAI_ENDPOINT.
            base_url: The deployment base URL. If provided will override the value
                in the env vars or .env file. Currently, the base_url must end with "/openai/v1/".
                Can also be set via environment variable AZURE_OPENAI_BASE_URL.
            api_version: The deployment API version. If provided will override the value
                in the env vars or .env file. Currently, the api_version must be "preview".
                Can also be set via environment variable AZURE_OPENAI_API_VERSION.
            token_endpoint: The token endpoint to request an Azure token.
                Can also be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.
            credential: Azure credential or token provider for authentication. Accepts a
                ``TokenCredential``, ``AsyncTokenCredential``, or a callable that returns a
                bearer token string (sync or async), for example from
                ``azure.identity.get_bearer_token_provider()``.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests.
            async_client: An existing client to use.
            project_client: An existing ``AIProjectClient`` (from ``azure.ai.projects.aio``) to use.
                The OpenAI client will be obtained via ``project_client.get_openai_client()``.
                Requires the ``azure-ai-projects`` package.
            project_endpoint: The Azure AI Foundry project endpoint URL.
                When provided with ``credential``, an ``AIProjectClient`` will be created
                and used to obtain the OpenAI client. Requires the ``azure-ai-projects`` package.
            env_file_path: Use the environment settings file as a fallback to using env vars.
            env_file_encoding: The encoding of the environment settings file, defaults to 'utf-8'.
            instruction_role: The role to use for 'instruction' messages, for example, summarization
                prompts could use `developer` or `system`.
            middleware: Optional sequence of middleware to apply to requests.
            function_invocation_configuration: Optional configuration for function invocation behavior.
            kwargs: Additional keyword arguments.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureOpenAIResponsesClient

                # Using environment variables
                # Set AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
                # Set AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-4o
                # Set AZURE_OPENAI_API_KEY=your-key
                client = AzureOpenAIResponsesClient()

                # Or passing parameters directly
                client = AzureOpenAIResponsesClient(
                    endpoint="https://your-endpoint.openai.azure.com", deployment_name="gpt-4o", api_key="your-key"
                )

                # Or loading from a .env file
                client = AzureOpenAIResponsesClient(env_file_path="path/to/.env")

                # Using a Foundry project endpoint
                from azure.identity import DefaultAzureCredential

                client = AzureOpenAIResponsesClient(
                    project_endpoint="https://your-project.services.ai.azure.com",
                    deployment_name="gpt-4o",
                    credential=DefaultAzureCredential(),
                )

                # Or using an existing AIProjectClient
                from azure.ai.projects.aio import AIProjectClient

                project_client = AIProjectClient(
                    endpoint="https://your-project.services.ai.azure.com",
                    credential=DefaultAzureCredential(),
                )
                client = AzureOpenAIResponsesClient(
                    project_client=project_client,
                    deployment_name="gpt-4o",
                )

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.azure import AzureOpenAIResponsesOptions


                class MyOptions(AzureOpenAIResponsesOptions, total=False):
                    my_custom_option: str


                client: AzureOpenAIResponsesClient[MyOptions] = AzureOpenAIResponsesClient()
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        if (model_id := kwargs.pop("model_id", None)) and not deployment_name:
            deployment_name = str(model_id)

        # Project client path: create OpenAI client from an Azure AI Foundry project
        if async_client is None and (project_client is not None or project_endpoint is not None):
            async_client = self._create_client_from_project(
                project_client=project_client,
                project_endpoint=project_endpoint,
                credential=credential,
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
        # TODO(peterychang): This is a temporary hack to ensure that the base_url is set correctly
        # while this feature is in preview.
        # But we should only do this if we're on azure. Private deployments may not need this.
        if (
            not azure_openai_settings.get("base_url")
            and azure_openai_settings.get("endpoint")
            and (hostname := urlparse(str(azure_openai_settings["endpoint"])).hostname)
            and hostname.endswith(".openai.azure.com")
        ):
            azure_openai_settings["base_url"] = urljoin(str(azure_openai_settings["endpoint"]), "/openai/v1/")

        if not azure_openai_settings["responses_deployment_name"]:
            raise ValueError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME' environment variable."
            )

        super().__init__(
            deployment_name=azure_openai_settings["responses_deployment_name"],
            endpoint=azure_openai_settings["endpoint"],
            base_url=azure_openai_settings["base_url"],
            api_version=azure_openai_settings["api_version"],  # type: ignore
            api_key=azure_openai_settings["api_key"].get_secret_value() if azure_openai_settings["api_key"] else None,
            token_endpoint=azure_openai_settings["token_endpoint"],
            credential=credential,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )

    @staticmethod
    def _create_client_from_project(
        *,
        project_client: AIProjectClient | None,
        project_endpoint: str | None,
        credential: AzureCredentialTypes | AzureTokenProvider | None,
    ) -> AsyncOpenAI:
        """Create an AsyncOpenAI client from an Azure AI Foundry project.

        Args:
            project_client: An existing AIProjectClient to use.
            project_endpoint: The Azure AI Foundry project endpoint URL.
            credential: Azure credential for authentication.

        Returns:
            An AsyncAzureOpenAI client obtained from the project client.

        Raises:
            ValueError: If required parameters are missing or
                the azure-ai-projects package is not installed.
        """
        if project_client is not None:
            return project_client.get_openai_client()

        if not project_endpoint:
            raise ValueError("Azure AI project endpoint is required when project_client is not provided.")
        if not credential:
            raise ValueError("Azure credential is required when using project_endpoint without a project_client.")
        project_client = AIProjectClient(
            endpoint=project_endpoint,
            credential=credential,  # type: ignore[arg-type]
            user_agent=AGENT_FRAMEWORK_USER_AGENT,
        )
        return project_client.get_openai_client()

    @override
    def _check_model_presence(self, options: dict[str, Any]) -> None:
        if not options.get("model"):
            if not self.model_id:
                raise ValueError("deployment_name must be a non-empty string")
            options["model"] = self.model_id
