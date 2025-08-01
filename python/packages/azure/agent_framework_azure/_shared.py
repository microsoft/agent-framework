# Copyright (c) Microsoft. All rights reserved.


import logging
from collections.abc import Awaitable, Callable, Mapping
from copy import copy
from typing import Any, ClassVar, Final

from agent_framework._pydantic import AFBaseSettings, HttpsUrl
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.openai._shared import OpenAIHandler, OpenAIModelTypes
from agent_framework.telemetry import USER_AGENT_KEY
from openai.lib.azure import AsyncAzureOpenAI
from pydantic import ConfigDict, SecretStr, validate_call

from ._entra_id_authentication import get_entra_auth_token

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
        api_version: The API version to use. The default value is "2024-02-01".
            (Env var AZURE_OPENAI_API_VERSION)
        token_endpoint: The token endpoint to use to retrieve the authentication token.
            The default value is "https://cognitiveservices.azure.com/.default".
            (Env var AZURE_OPENAI_TOKEN_ENDPOINT)

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
    endpoint: HttpsUrl | None = None
    base_url: HttpsUrl | None = None
    api_key: SecretStr | None = None
    api_version: str = DEFAULT_AZURE_API_VERSION
    token_endpoint: str = DEFAULT_AZURE_TOKEN_ENDPOINT

    def get_azure_openai_auth_token(self, token_endpoint: str | None = None) -> str | None:
        """Retrieve a Microsoft Entra Auth Token for a given token endpoint for the use with Azure OpenAI.

        The required role for the token is `Cognitive Services OpenAI Contributor`.
        The token endpoint may be specified as an environment variable, via the .env
        file or as an argument. If the token endpoint is not provided, the default is None.
        The `token_endpoint` argument takes precedence over the `token_endpoint` attribute.

        Args:
            token_endpoint: The token endpoint to use. Defaults to `https://cognitiveservices.azure.com/.default`.

        Returns:
            The Azure token or None if the token could not be retrieved.

        Raises:
            ServiceInitializationError: If the token endpoint is not provided.
        """
        endpoint_to_use = token_endpoint or self.token_endpoint
        if endpoint_to_use is None:  # type: ignore
            raise ServiceInitializationError("Please provide a token endpoint to retrieve the authentication token.")
        return get_entra_auth_token(endpoint_to_use)


class AzureOpenAIConfigBase(OpenAIHandler):
    """Internal class for configuring a connection to an Azure OpenAI service."""

    @validate_call(config=ConfigDict(arbitrary_types_allowed=True))
    def __init__(
        self,
        deployment_name: str,
        ai_model_type: OpenAIModelTypes,
        endpoint: HttpsUrl | None = None,
        base_url: HttpsUrl | None = None,
        api_version: str = DEFAULT_AZURE_API_VERSION,
        api_key: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: Callable[[], str | Awaitable[str]] | None = None,
        token_endpoint: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        client: AsyncAzureOpenAI | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Internal class for configuring a connection to an Azure OpenAI service.

        The `validate_call` decorator is used with a configuration that allows arbitrary types.
        This is necessary for types like `HttpsUrl` and `OpenAIModelTypes`.

        Args:
            deployment_name (str): Name of the deployment.
            ai_model_type (OpenAIModelTypes): The type of OpenAI model to deploy.
            endpoint (HttpsUrl): The specific endpoint URL for the deployment. (Optional)
            base_url (Url): The base URL for Azure services. (Optional)
            api_version (str): Azure API version. Defaults to the defined DEFAULT_AZURE_API_VERSION.
            api_key (str): API key for Azure services. (Optional)
            ad_token (str): Azure AD token for authentication. (Optional)
            ad_token_provider (Callable[[], Union[str, Awaitable[str]]]): A callable
                or coroutine function providing Azure AD tokens. (Optional)
            token_endpoint (str): Azure AD token endpoint use to get the token. (Optional)
            default_headers (Union[Mapping[str, str], None]): Default headers for HTTP requests. (Optional)
            client (AsyncAzureOpenAI): An existing client to use. (Optional)
            instruction_role (str | None): The role to use for 'instruction' messages, for example, summarization
                prompts could use `developer` or `system`. (Optional)
            kwargs: Additional keyword arguments.

        """
        # Merge APP_INFO into the headers if it exists
        merged_headers = dict(copy(default_headers)) if default_headers else {}

        if not client:
            # If the client is None, the api_key is none, the ad_token is none, and the ad_token_provider is none,
            # then we will attempt to get the ad_token using the default endpoint specified in the Azure OpenAI
            # settings.
            if not api_key and not ad_token_provider and not ad_token and token_endpoint:
                ad_token = get_entra_auth_token(token_endpoint)

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
            # TODO (eavanvalkenburg): Remove the check on model type when the package fixes: https://github.com/openai/openai-python/issues/2120
            if deployment_name and ai_model_type != OpenAIModelTypes.REALTIME:
                args["azure_deployment"] = deployment_name

            if "websocket_base_url" in kwargs:
                args["websocket_base_url"] = kwargs.pop("websocket_base_url")

            client = AsyncAzureOpenAI(**args)
        args = {
            "ai_model_id": deployment_name,
            "client": client,
            "ai_model_type": ai_model_type,
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
                "ai_model_type",
                "service_id",
                "client",
            },
            by_alias=True,
            exclude_none=True,
        )
        base.update(client_settings)
        return base
