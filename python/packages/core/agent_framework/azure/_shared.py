# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from copy import copy
from typing import Any, ClassVar, Final

from openai import AsyncOpenAI
from openai.lib.azure import AsyncAzureOpenAI

from .._settings import SecretString
from .._telemetry import APP_INFO, prepend_agent_framework_to_user_agent
from ..openai._shared import OpenAIBase
from ._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider, resolve_credential_to_token_provider

logger: logging.Logger = logging.getLogger(__name__)

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


DEFAULT_AZURE_API_VERSION: Final[str] = "2024-10-21"
DEFAULT_AZURE_TOKEN_ENDPOINT: Final[str] = "https://cognitiveservices.azure.com/.default"  # noqa: S105


class AzureOpenAISettings(TypedDict, total=False):
    """AzureOpenAI model settings.

    Settings are resolved in this order: explicit keyword arguments, values from an
    explicitly provided .env file, then environment variables with the prefix
    'AZURE_OPENAI_'. If settings are missing after resolution, validation will fail.

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
        embedding_deployment_name: The name of the Azure Embedding deployment.
            Can be set via environment variable AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME.
        api_key: The API key for the Azure deployment. This value can be
            found in the Keys & Endpoint section when examining your resource in
            the Azure portal. You can use either KEY1 or KEY2.
            Can be set via environment variable AZURE_OPENAI_API_KEY.
        api_version: The API version to use. The default value is `DEFAULT_AZURE_API_VERSION`.
            Can be set via environment variable AZURE_OPENAI_API_VERSION.
        base_url: The url of the Azure deployment. This value
            can be found in the Keys & Endpoint section when examining
            your resource from the Azure portal, the base_url consists of the endpoint,
            followed by /openai/deployments/{deployment_name}/,
            use endpoint if you only want to supply the endpoint.
            Can be set via environment variable AZURE_OPENAI_BASE_URL.
        token_endpoint: The token endpoint to use to retrieve the authentication token.
            The default value is `DEFAULT_AZURE_TOKEN_ENDPOINT`.
            Can be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.

    Examples:
        .. code-block:: python

            from agent_framework.azure import AzureOpenAISettings

            # Using environment variables
            # Set AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
            # Set AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4
            # Set AZURE_OPENAI_API_KEY=your-key
            settings = load_settings(AzureOpenAISettings, env_prefix="AZURE_OPENAI_")

            # Or passing parameters directly
            settings = load_settings(
                AzureOpenAISettings,
                env_prefix="AZURE_OPENAI_",
                endpoint="https://your-endpoint.openai.azure.com",
                chat_deployment_name="gpt-4",
                api_key="your-key",
            )

            # Or loading from a .env file
            settings = load_settings(AzureOpenAISettings, env_prefix="AZURE_OPENAI_", env_file_path="path/to/.env")
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


class AzureOpenAIConfigMixin(OpenAIBase):
    """Internal class for configuring a connection to an Azure OpenAI service."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.openai"
    # Note: INJECTABLE = {"client"} is inherited from OpenAIBase

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
        """Internal class for configuring a connection to an Azure OpenAI service.

        The `validate_call` decorator is used with a configuration that allows arbitrary types.
        This is necessary for types like `str` and `OpenAIModelTypes`.

        Args:
            deployment_name: Name of the deployment.
            endpoint: The specific endpoint URL for the deployment.
            base_url: The base URL for Azure services.
            api_version: Azure API version. Defaults to the defined DEFAULT_AZURE_API_VERSION.
            api_key: API key for Azure services.
            token_endpoint: Azure AD token scope used to obtain a bearer token from a credential.
            credential: Azure credential or token provider for authentication. Accepts a
                ``TokenCredential``, ``AsyncTokenCredential``, or a callable that returns a
                bearer token string (sync or async).
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
            # Resolve credential to a token provider if needed
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

        # Store configuration as instance attributes for serialization
        self.endpoint = str(endpoint)
        self.base_url = str(base_url)
        self.api_version = api_version
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
