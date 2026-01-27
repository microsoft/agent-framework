# Copyright (c) Microsoft. All rights reserved.

import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from copy import copy
from typing import Any, ClassVar, Final
from urllib.parse import urljoin

from azure.core.credentials import TokenCredential
from openai import AsyncOpenAI
from pydantic import SecretStr, model_validator

from .._pydantic import AFBaseSettings, HTTPsUrl
from .._telemetry import APP_INFO, prepend_agent_framework_to_user_agent
from ..exceptions import ServiceInitializationError
from ..openai._shared import OpenAIBase
from ._entra_id_authentication import get_entra_auth_token

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger: logging.Logger = logging.getLogger(__name__)


DEFAULT_AZURE_API_VERSION: Final[str] = "2024-10-21"
DEFAULT_AZURE_TOKEN_ENDPOINT: Final[str] = "https://cognitiveservices.azure.com/.default"  # noqa: S105


class AzureOpenAISettings(AFBaseSettings):
    """AzureOpenAI model settings.

    The settings are first loaded from environment variables with the prefix 'AZURE_OPENAI_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        endpoint: The endpoint of the Azure deployment. This value
            can be found in the Keys & Endpoint section when examining
            your resource from the Azure portal, the endpoint should end in openai.azure.com.
            If both base_url and endpoint are supplied, base_url will be used.
            Can be set via environment variable AZURE_OPENAI_ENDPOINT.
        chat_deployment_name: The name of the Azure Chat deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            Can be set via environment variable AZURE_OPENAI_CHAT_DEPLOYMENT_NAME.
        responses_deployment_name: The name of the Azure Responses deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            Can be set via environment variable AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME.
        api_key: The API key for the Azure deployment. This value can be
            found in the Keys & Endpoint section when examining your resource in
            the Azure portal. You can use either KEY1 or KEY2.
            Can be set via environment variable AZURE_OPENAI_API_KEY.
        api_version: The API version to use. The default value is `default_api_version`.
            Can be set via environment variable AZURE_OPENAI_API_VERSION.
        base_url: The url of the Azure deployment. This value
            can be found in the Keys & Endpoint section when examining
            your resource from the Azure portal, the base_url consists of the endpoint,
            followed by /openai/deployments/{deployment_name}/,
            use endpoint if you only want to supply the endpoint.
            Can be set via environment variable AZURE_OPENAI_BASE_URL.
        token_endpoint: The token endpoint to use to retrieve the authentication token.
            The default value is `default_token_endpoint`.
            Can be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.
        default_api_version: The default API version to use if not specified.
            The default value is "2024-10-21".
        default_token_endpoint: The default token endpoint to use if not specified.
            The default value is "https://cognitiveservices.azure.com/.default".
        env_file_path: The path to the .env file to load settings from.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework.azure import AzureOpenAISettings

            # Using environment variables
            # Set AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
            # Set AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4
            # Set AZURE_OPENAI_API_KEY=your-key
            settings = AzureOpenAISettings()

            # Or passing parameters directly
            settings = AzureOpenAISettings(
                endpoint="https://your-endpoint.openai.azure.com", chat_deployment_name="gpt-4", api_key="your-key"
            )

            # Or loading from a .env file
            settings = AzureOpenAISettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "AZURE_OPENAI_"

    chat_deployment_name: str | None = None
    responses_deployment_name: str | None = None
    endpoint: HTTPsUrl | None = None
    base_url: HTTPsUrl | None = None
    api_key: SecretStr | None = None
    api_version: str | None = None
    token_endpoint: str | None = None
    default_api_version: str = DEFAULT_AZURE_API_VERSION
    default_token_endpoint: str = DEFAULT_AZURE_TOKEN_ENDPOINT

    def get_azure_auth_token(
        self, credential: "TokenCredential", token_endpoint: str | None = None, **kwargs: Any
    ) -> str | None:
        """Retrieve a Microsoft Entra Auth Token for a given token endpoint for the use with Azure OpenAI.

        The required role for the token is `Cognitive Services OpenAI Contributor`.
        The token endpoint may be specified as an environment variable, via the .env
        file or as an argument. If the token endpoint is not provided, the default is None.
        The `token_endpoint` argument takes precedence over the `token_endpoint` attribute.

        Args:
            credential: The Azure AD credential to use.
            token_endpoint: The token endpoint to use. Defaults to `https://cognitiveservices.azure.com/.default`.

        Keyword Args:
            **kwargs: Additional keyword arguments to pass to the token retrieval method.

        Returns:
            The Azure token or None if the token could not be retrieved.

        Raises:
            ServiceInitializationError: If the token endpoint is not provided.
        """
        endpoint_to_use = token_endpoint or self.token_endpoint or self.default_token_endpoint
        return get_entra_auth_token(credential, endpoint_to_use, **kwargs)

    @model_validator(mode="after")
    def _validate_fields(self) -> Self:
        self.api_version = self.api_version or self.default_api_version
        self.token_endpoint = self.token_endpoint or self.default_token_endpoint
        return self


def _construct_v1_base_url(endpoint: HTTPsUrl | None, base_url: HTTPsUrl | None) -> str | None:
    """Construct the v1 API base URL from endpoint if not explicitly provided.

    For standard Azure OpenAI endpoints, automatically appends /openai/v1/ path.
    Custom/private deployments can provide their own base_url.

    Args:
        endpoint: The Azure OpenAI endpoint URL.
        base_url: Explicit base URL if provided by user.

    Returns:
        The base URL to use, or None if neither endpoint nor base_url is valid.
    """
    if base_url:
        return str(base_url)

    # Standard Azure OpenAI endpoints
    if endpoint and endpoint.host and endpoint.host.endswith((".openai.azure.com", ".services.ai.azure.com")):
        return urljoin(str(endpoint), "/openai/v1/")

    return None


class AzureOpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an Azure OpenAI service."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.openai"
    # Note: INJECTABLE = {"client"} is inherited from OpenAIBase

    def __init__(
        self,
        deployment_name: str,
        endpoint: HTTPsUrl | None = None,
        base_url: HTTPsUrl | None = None,
        api_key: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: Callable[[], str | Awaitable[str]] | None = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncOpenAI | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Internal class for configuring a connection to an Azure OpenAI service.

        Args:
            deployment_name: Name of the deployment.
            endpoint: The specific endpoint URL for the deployment.
            base_url: The base URL for Azure services. If not provided and endpoint is a
                standard Azure OpenAI endpoint, /openai/v1/ will be appended automatically.
            api_key: API key for Azure services. Can also be a token provider callable.
            ad_token: Azure AD token for authentication.
            ad_token_provider: A callable or coroutine function providing Azure AD tokens.
            token_endpoint: Azure AD token endpoint used to get the token.
            credential: Azure credential for authentication.
            default_headers: Default headers for HTTP requests.
            client: An existing client to use.
            instruction_role: The role to use for 'instruction' messages, for example, summarization
                prompts could use `developer` or `system`.
            kwargs: Additional keyword arguments.

        """
        # Merge APP_INFO into the headers if it exists
        merged_headers = dict(copy(default_headers)) if default_headers else {}
        if APP_INFO:
            merged_headers.update(APP_INFO)
            merged_headers = prepend_agent_framework_to_user_agent(merged_headers)

        if not client:
            # Construct v1 base URL from endpoint if not explicitly provided
            v1_base_url = _construct_v1_base_url(endpoint, base_url)

            # If the client is None, the api_key is none, the ad_token is none, and the ad_token_provider is none,
            # then we will attempt to get the ad_token using the default endpoint specified in the Azure OpenAI
            # settings.
            if not api_key and not ad_token_provider and not ad_token and token_endpoint and credential:
                ad_token = get_entra_auth_token(credential, token_endpoint)

            if not api_key and not ad_token and not ad_token_provider:
                raise ServiceInitializationError(
                    "Please provide either api_key, ad_token or ad_token_provider or a client."
                )

            if not v1_base_url:
                raise ServiceInitializationError(
                    "Please provide an endpoint or a base_url. "
                    "For standard Azure OpenAI endpoints (*.openai.azure.com and *.services.ai.azure.com), "
                    "the v1 API path will be appended automatically; for non-standard or private deployments, "
                    "you must provide a base_url that already includes the desired API path."
                )

            # Determine the effective api_key for AsyncOpenAI
            effective_api_key: str | Callable[[], str | Awaitable[str]] | None = None
            if api_key:
                effective_api_key = api_key
            elif ad_token_provider:
                effective_api_key = ad_token_provider
            elif ad_token:
                effective_api_key = ad_token

            args: dict[str, Any] = {
                "base_url": v1_base_url,
                "api_key": effective_api_key,
                "default_headers": merged_headers,
            }
            if "websocket_base_url" in kwargs:
                args["websocket_base_url"] = kwargs.pop("websocket_base_url")

            client = AsyncOpenAI(**args)

        # Store configuration as instance attributes for serialization
        self.endpoint = str(endpoint) if endpoint else None
        self.base_url = str(base_url) if base_url else None
        self.deployment_name = deployment_name
        self.instruction_role = instruction_role
        # Store default_headers but filter out USER_AGENT_KEY for serialization
        if default_headers:
            from .._telemetry import USER_AGENT_KEY

            def_headers = {k: v for k, v in default_headers.items() if k != USER_AGENT_KEY}
        else:
            def_headers = None
        self.default_headers = def_headers

        super().__init__(model_id=deployment_name, client=client, **kwargs)
