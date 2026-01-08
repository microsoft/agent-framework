# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Mapping
from typing import Any, Generic, TypedDict, TypeVar
from urllib.parse import urljoin

from azure.core.credentials import TokenCredential
from openai.lib.azure import AsyncAzureADTokenProvider, AsyncAzureOpenAI
from pydantic import ValidationError

from agent_framework import use_chat_middleware, use_function_invocation
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_instrumentation
from agent_framework.openai._responses_client import (
    OpenAIBaseResponsesClient,
    OpenAIResponsesOptions,
)

from ._shared import (
    AzureOpenAIConfigMixin,
    AzureOpenAISettings,
)

__all__ = ["AzureOpenAIResponsesClient", "AzureOpenAIResponsesOptions"]


# region Azure OpenAI Responses Options TypedDict


class AzureOpenAIResponsesOptions(OpenAIResponsesOptions, total=False):
    """Azure OpenAI Responses API-specific options dict.

    Extends OpenAIResponsesOptions for Azure-hosted OpenAI Responses API.
    Azure's Responses API supports the same options as the OpenAI Responses API.

    See: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/responses

    Keys:
        # Inherited from OpenAIResponsesOptions/ChatOptions:
        model_id: The model to use for the request.
        temperature: Sampling temperature between 0 and 2.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum number of tokens to generate.
        stop: Stop sequences.
        seed: Random seed for reproducibility.
        frequency_penalty: Frequency penalty between -2.0 and 2.0.
        presence_penalty: Presence penalty between -2.0 and 2.0.
        tools: List of tools (functions) available to the model.
        tool_choice: How the model should use tools.
        allow_multiple_tool_calls: Whether to allow parallel tool calls.
        response_format: Structured output schema.
        metadata: Request metadata for tracking.
        user: End-user identifier for abuse monitoring.
        store: Whether to store the response.
        instructions: System instructions for the model.

        # Responses API-specific options (inherited):
        include: Additional output data to include.
        max_tool_calls: Maximum number of tool calls.
        prompt: Reference to prompt template.
        reasoning: Configuration for reasoning models.
        service_tier: Processing tier.
        stream_options: Streaming options.
        top_logprobs: Number of top log probabilities.
        truncation: Truncation strategy.

    Examples:
        .. code-block:: python

            from agent_framework.azure import AzureOpenAIResponsesOptions

            # Basic usage
            options: AzureOpenAIResponsesOptions = {
                "temperature": 0.7,
                "max_tokens": 1000,
            }

            # With reasoning model configuration
            options: AzureOpenAIResponsesOptions = {
                "model_id": "gpt-4o",
                "reasoning": {"effort": "high", "summary": "detailed"},
            }
    """

    pass  # Currently no Azure-specific options; uses OpenAIResponsesOptions


TAzureOpenAIResponsesOptions = TypeVar(
    "TAzureOpenAIResponsesOptions",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AzureOpenAIResponsesOptions",
    contravariant=True,
)


# endregion


TAzureOpenAIResponsesClient = TypeVar("TAzureOpenAIResponsesClient", bound="AzureOpenAIResponsesClient")


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class AzureOpenAIResponsesClient(
    AzureOpenAIConfigMixin,
    OpenAIBaseResponsesClient[TAzureOpenAIResponsesOptions],
    Generic[TAzureOpenAIResponsesOptions],
):
    """Azure Responses completion class."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        deployment_name: str | None = None,
        endpoint: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        ad_token: str | None = None,
        ad_token_provider: AsyncAzureADTokenProvider | None = None,
        token_endpoint: str | None = None,
        credential: TokenCredential | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncAzureOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure OpenAI Responses client.

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
            ad_token: The Azure Active Directory token.
            ad_token_provider: The Azure Active Directory token provider.
            token_endpoint: The token endpoint to request an Azure token.
                Can also be set via environment variable AZURE_OPENAI_TOKEN_ENDPOINT.
            credential: The Azure credential for authentication.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests.
            async_client: An existing client to use.
            env_file_path: Use the environment settings file as a fallback to using env vars.
            env_file_encoding: The encoding of the environment settings file, defaults to 'utf-8'.
            instruction_role: The role to use for 'instruction' messages, for example, summarization
                prompts could use `developer` or `system`.
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

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework.azure import AzureOpenAIResponsesOptions


                class MyOptions(AzureOpenAIResponsesOptions, total=False):
                    my_custom_option: str


                client: AzureOpenAIResponsesClient[MyOptions] = AzureOpenAIResponsesClient()
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        if model_id := kwargs.pop("model_id", None) and not deployment_name:
            deployment_name = str(model_id)
        try:
            azure_openai_settings = AzureOpenAISettings(
                # pydantic settings will see if there is a value, if not, will try the env var or .env file
                api_key=api_key,  # type: ignore
                base_url=base_url,  # type: ignore
                endpoint=endpoint,  # type: ignore
                responses_deployment_name=deployment_name,
                api_version=api_version,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
                token_endpoint=token_endpoint,
                default_api_version="preview",
            )
            # TODO(peterychang): This is a temporary hack to ensure that the base_url is set correctly
            # while this feature is in preview.
            # But we should only do this if we're on azure. Private deployments may not need this.
            if (
                not azure_openai_settings.base_url
                and azure_openai_settings.endpoint
                and azure_openai_settings.endpoint.host
                and azure_openai_settings.endpoint.host.endswith(".openai.azure.com")
            ):
                azure_openai_settings.base_url = urljoin(str(azure_openai_settings.endpoint), "/openai/v1/")  # type: ignore
        except ValidationError as exc:
            raise ServiceInitializationError(f"Failed to validate settings: {exc}") from exc

        if not azure_openai_settings.responses_deployment_name:
            raise ServiceInitializationError(
                "Azure OpenAI deployment name is required. Set via 'deployment_name' parameter "
                "or 'AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME' environment variable."
            )

        super().__init__(
            deployment_name=azure_openai_settings.responses_deployment_name,
            endpoint=azure_openai_settings.endpoint,
            base_url=azure_openai_settings.base_url,
            api_version=azure_openai_settings.api_version,  # type: ignore
            api_key=azure_openai_settings.api_key.get_secret_value() if azure_openai_settings.api_key else None,
            ad_token=ad_token,
            ad_token_provider=ad_token_provider,
            token_endpoint=azure_openai_settings.token_endpoint,
            credential=credential,
            default_headers=default_headers,
            client=async_client,
            instruction_role=instruction_role,
        )
