# Copyright (c) Microsoft. All rights reserved.

import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from copy import copy
from typing import Any, ClassVar, Final

from agent_framework._pydantic import AFBaseSettings, HTTPsUrl
from agent_framework._telemetry import APP_INFO, USER_AGENT_KEY, prepend_agent_framework_to_user_agent
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.openai._shared import OpenAIBase
from azure.core.credentials import TokenCredential
from openai.lib.azure import AsyncAzureOpenAI
from pydantic import ConfigDict, SecretStr, model_validator, validate_call

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

    Attributes:
        chat_deployment_name: The name of the Azure Chat deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_CHAT_DEPLOYMENT_NAME)
        responses_deployment_name: The name of the Azure Responses deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME)
        text_deployment_name: The name of the Azure Text deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_TEXT_DEPLOYMENT_NAME)
        embedding_deployment_name: The name of the Azure Embedding deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME)
        text_to_image_deployment_name: The name of the Azure Text to Image deployment. This
            value will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_TEXT_TO_IMAGE_DEPLOYMENT_NAME)
        audio_to_text_deployment_name: The name of the Azure Audio to Text deployment. This
            value will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_AUDIO_TO_TEXT_DEPLOYMENT_NAME)
        text_to_audio_deployment_name: The name of the Azure Text to Audio deployment. This
            value will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_TEXT_TO_AUDIO_DEPLOYMENT_NAME)
        realtime_deployment_name: The name of the Azure Realtime deployment. This value
            will correspond to the custom name you chose for your deployment
            when you deployed a model. This value can be found under
            Resource Management > Deployments in the Azure portal or, alternatively,
            under Management > Deployments in Azure AI Foundry.
            (Env var AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME)
        api_key: The API key for the Azure deployment. This value can be
            found in the Keys & Endpoint section when examining your resource in
            the Azure portal. You can use either KEY1 or KEY2.
            (Env var AZURE_OPENAI_API_KEY)
        base_url: The url of the Azure deployment. This value
            can be found in the Keys & Endpoint section when examining
            your resource from the Azure portal, the base_url consists of the endpoint,
            followed by /openai/deployments/{deployment_name}/,
            use endpoint if you only want to supply the endpoint.
            (Env var AZURE_OPENAI_BASE_URL)
        endpoint: The endpoint of the Azure deployment. This value
            can be found in the Keys & Endpoint section when examining
            your resource from the Azure portal, the endpoint should end in openai.azure.com.
            If both base_url and endpoint are supplied, base_url will be used.
            (Env var AZURE_OPENAI_ENDPOINT)
        api_version: The API version to use. The default value is `default_api_version`.
            (Env var AZURE_OPENAI_API_VERSION)
        token_endpoint: The token endpoint to use to retrieve the authentication token.
            The default value is `default_token_endpoint`.
            (Env var AZURE_OPENAI_TOKEN_ENDPOINT)
        default_api_version: The default API version to use if not specified.
            The default value is "2024-10-21".
        default_token_endpoint: The default token endpoint to use if not specified.
            The default value is "https://cognitiveservices.azure.com/.default".

    Parameters:
        env_file_path: The path to the .env file to load settings from.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.
    """

    env_prefix: ClassVar[str] = "AZURE_OPENAI_"

    chat_deployment_name: str | None = None
    responses_deployment_name: str | None = None
    text_deployment_name: str | None = None
    embedding_deployment_name: str | None = None
    text_to_image_deployment_name: str | None = None
    audio_to_text_deployment_name: str | None = None
    text_to_audio_deployment_name: str | None = None
    realtime_deployment_name: str | None = None
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


class AzureOpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an Azure OpenAI service."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure_openai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def __init__(
        self,
        deployment_name: str,
        endpoint: HTTPsUrl | None = None,
        base_url: HTTPsUrl | None = None,
        api_version: str = DEFAULT_AZURE_API_VERSION,
        api_key: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: Callable[[], str | Awaitable[str]] | None = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncAzureOpenAI | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Internal class for configuring a connection to an Azure OpenAI service.

        The `validate_call` decorator is used with a configuration that allows arbitrary types.
        This is necessary for types like `HTTPsUrl` and `OpenAIModelTypes`.

        Args:
            deployment_name: Name of the deployment.
            ai_model_type: The type of OpenAI model to deploy.
            endpoint: The specific endpoint URL for the deployment.
            base_url: The base URL for Azure services.
            api_version: Azure API version. Defaults to the defined DEFAULT_AZURE_API_VERSION.
            api_key: API key for Azure services.
            ad_token: Azure AD token for authentication.
            ad_token_provider: A callable or coroutine function providing Azure AD tokens.
            token_endpoint: Azure AD token endpoint use to get the token.
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
            # If the client is None, the api_key is none, the ad_token is none, and the ad_token_provider is none,
            # then we will attempt to get the ad_token using the default endpoint specified in the Azure OpenAI
            # settings.
            if not api_key and not ad_token_provider and not ad_token and token_endpoint and credential:
                ad_token = get_entra_auth_token(credential, token_endpoint)

            if not api_key and not ad_token and not ad_token_provider:
                raise ServiceInitializationError(
                    "Please provide either api_key, ad_token or ad_token_provider or a client."
                )

            if not endpoint and not base_url:
                raise ServiceInitializationError("Please provide an endpoint or a base_url")

            args: dict[str, Any] = {
                "default_headers": merged_headers,
            }
            if api_version:
                args["api_version"] = api_version
            if ad_token:
                args["azure_ad_token"] = ad_token
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
        args = {
            "ai_model_id": deployment_name,
            "client": client,
        }
        if instruction_role:
            args["instruction_role"] = instruction_role
        super().__init__(**args, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """Convert the configuration to a dictionary."""
        client_settings = {
            "base_url": str(self.client.base_url),
            "api_version": self.client._custom_query["api-version"],  # type: ignore
            "api_key": self.client.api_key,
            "ad_token": getattr(self.client, "_azure_ad_token", None),
            "ad_token_provider": getattr(self.client, "_azure_ad_token_provider", None),
            "default_headers": {k: v for k, v in self.client.default_headers.items() if k != USER_AGENT_KEY},
        }
        base = self.model_dump(
            exclude={
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "api_type",
                "org_id",
                "service_id",
                "client",
            },
            by_alias=True,
            exclude_none=True,
        )
        base.update(client_settings)
        return base
