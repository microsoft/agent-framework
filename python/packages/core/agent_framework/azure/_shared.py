# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, Sequence
from copy import copy
from typing import Any, ClassVar, Final, Literal, cast

from azure.ai.projects.models import (
    ApproximateLocation,
    CodeInterpreterTool,
    CodeInterpreterToolAuto,
    ImageGenTool,
    MCPTool,
    WebSearchPreviewTool,
)
from azure.ai.projects.models import FileSearchTool as ProjectsFileSearchTool
from openai import AsyncOpenAI
from openai.lib.azure import AsyncAzureOpenAI

from .._settings import SecretString, load_settings
from .._telemetry import APP_INFO, prepend_agent_framework_to_user_agent
from .._types import Content
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


class FoundryProjectSettings(TypedDict, total=False):
    """Environment-backed Foundry project settings."""

    project_endpoint: str | None
    model_deployment_name: str | None


class FoundryToolSettings(TypedDict, total=False):
    """Environment-backed Foundry tool settings."""

    fabric_project_connection_id: str | None
    sharepoint_project_connection_id: str | None
    bing_project_connection_id: str | None
    bing_custom_search_project_connection_id: str | None
    bing_custom_search_instance_name: str | None
    ai_search_project_connection_id: str | None
    ai_search_index_name: str | None
    browser_automation_project_connection_id: str | None
    a2a_project_connection_id: str | None
    a2a_endpoint: str | None


def load_foundry_project_settings(
    *,
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
) -> FoundryProjectSettings:
    """Load Foundry project settings from ``FOUNDRY_*`` environment variables.

    This resolves the following variables (or matching entries in ``env_file_path``
    when provided):

    - ``FOUNDRY_PROJECT_ENDPOINT``
    - ``FOUNDRY_MODEL_DEPLOYMENT_NAME``
    """
    return load_settings(
        FoundryProjectSettings,
        env_prefix="FOUNDRY_",
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )


def _load_foundry_tool_settings(
    *,
    env_file_path: str | None = None,
    env_file_encoding: str | None = None,
) -> FoundryToolSettings:
    """Load shared Foundry tool settings from environment variables.

    With an empty ``env_prefix``, ``load_settings`` reads these variable names
    directly (or from ``env_file_path`` when provided):

    - ``FABRIC_PROJECT_CONNECTION_ID``
    - ``SHAREPOINT_PROJECT_CONNECTION_ID``
    - ``BING_PROJECT_CONNECTION_ID``
    - ``BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID``
    - ``BING_CUSTOM_SEARCH_INSTANCE_NAME``
    - ``AI_SEARCH_PROJECT_CONNECTION_ID``
    - ``AI_SEARCH_INDEX_NAME``
    - ``BROWSER_AUTOMATION_PROJECT_CONNECTION_ID``
    - ``A2A_PROJECT_CONNECTION_ID``
    - ``A2A_ENDPOINT``
    """
    return load_settings(
        FoundryToolSettings,
        env_prefix="",
        env_file_path=env_file_path,
        env_file_encoding=env_file_encoding,
    )


def _require_string(value: str | None, param_name: str) -> str:
    if not value:
        raise ValueError(f"'{param_name}' is required.")
    return value


def _normalize_hosted_ids(
    value: str | Content | Sequence[str | Content] | None,
    *,
    expected_content_type: Literal["hosted_file", "hosted_vector_store"],
    content_id_field: Literal["file_id", "vector_store_id"],
    parameter_name: Literal["file_ids", "vector_store_ids"],
) -> list[str] | None:
    """Normalize string/Content id inputs with strict hosted content validation."""
    if value is None:
        return None

    items: list[str | Content] = [value] if isinstance(value, (str, Content)) else list(value)

    normalized_ids: list[str] = []
    for item in items:
        if isinstance(item, str):
            normalized_ids.append(item)
            continue

        if isinstance(item, Content):
            if item.type != expected_content_type:
                raise TypeError(
                    f"{parameter_name} accepts string IDs or Content of type {expected_content_type}."
                )
            content_id = getattr(item, content_id_field)
            if not content_id:
                raise ValueError(
                    f"{parameter_name} Content items must include '{content_id_field}'."
                )
            normalized_ids.append(content_id)
            continue

        raise TypeError(
            f"{parameter_name} accepts string IDs or Content of type {expected_content_type}."
        )

    return normalized_ids


def create_code_interpreter_tool(
    *,
    file_ids: str | Content | Sequence[str | Content] | None = None,
    container: Literal["auto"] | dict[str, Any] = "auto",
    **kwargs: Any,
) -> CodeInterpreterTool:
    """Create a code interpreter tool configuration for Azure AI Projects.

    Keyword Args:
        file_ids: File IDs for the code interpreter. Accepts a string ID,
            hosted_file Content, or a sequence containing either form.
        container: Existing container payload.
        **kwargs: Additional arguments passed to the SDK CodeInterpreterTool constructor.
    """
    if file_ids is None and isinstance(container, dict):
        file_ids = cast("str | Content | Sequence[str | Content] | None", container.get("file_ids"))

    normalized_file_ids = _normalize_hosted_ids(
        file_ids,
        expected_content_type="hosted_file",
        content_id_field="file_id",
        parameter_name="file_ids",
    )

    tool_container = CodeInterpreterToolAuto(file_ids=normalized_file_ids if normalized_file_ids else None)
    return CodeInterpreterTool(container=tool_container, **kwargs)


def create_file_search_tool(
    *,
    vector_store_ids: str | Content | Sequence[str | Content] | None = None,
    max_num_results: int | None = None,
    ranking_options: dict[str, Any] | None = None,
    filters: dict[str, Any] | None = None,
    **kwargs: Any,
) -> ProjectsFileSearchTool:
    """Create a file search tool configuration for Azure AI Projects.

    Keyword Args:
        vector_store_ids: Vector store IDs to search. Accepts a string ID,
            hosted_vector_store Content, or a sequence containing either form.
        max_num_results: Maximum number of results to return (1-50).
        ranking_options: Ranking options for search results.
        filters: A filter to apply (ComparisonFilter or CompoundFilter).
        **kwargs: Additional arguments passed to the SDK FileSearchTool constructor.
    """
    normalized_vector_store_ids = _normalize_hosted_ids(
        vector_store_ids,
        expected_content_type="hosted_vector_store",
        content_id_field="vector_store_id",
        parameter_name="vector_store_ids",
    )

    if not normalized_vector_store_ids:
        raise ValueError("File search tool requires 'vector_store_ids' to be specified.")

    return ProjectsFileSearchTool(
        vector_store_ids=normalized_vector_store_ids,
        max_num_results=max_num_results,
        ranking_options=ranking_options,  # type: ignore[arg-type]
        filters=filters,  # type: ignore[arg-type]
        **kwargs,
    )

def create_web_search_tool(
    *,
    user_location: dict[str, str] | None = None,
    search_context_size: Literal["low", "medium", "high"] | None = None,
    **kwargs: Any,
) -> WebSearchPreviewTool:
    """Create a generic web search preview tool.

    Keyword Args:
        user_location: Location context for search results.
        search_context_size: Search context size ("low", "medium", or "high").
        **kwargs: Additional arguments passed to ``WebSearchPreviewTool``.
    """
    ws_tool = WebSearchPreviewTool(search_context_size=search_context_size, **kwargs)
    if user_location:
        ws_tool.user_location = ApproximateLocation(
            city=user_location.get("city"),
            country=user_location.get("country"),
            region=user_location.get("region"),
            timezone=user_location.get("timezone"),
        )
    return ws_tool


def create_bing_tool(
    *,
    variant: Literal[
        "grounding",
        "custom_search",
    ] = "grounding",
    project_connection_id: str | None = None,
    instance_name: str | None = None,
    count: int | None = None,
    market: str | None = None,
    set_lang: str | None = None,
    freshness: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create a Bing grounding/custom search tool.

    Environment-backed fallbacks (used when optional arguments are omitted):

    - For ``variant`` in ``{"grounding"}``: ``project_connection_id`` falls
      back to ``BING_PROJECT_CONNECTION_ID``.
    - For ``variant`` in ``{"custom_search"}``:
      ``project_connection_id`` falls back to
      ``BING_CUSTOM_SEARCH_PROJECT_CONNECTION_ID`` and ``instance_name`` falls back
      to ``BING_CUSTOM_SEARCH_INSTANCE_NAME``.

    Notes:
        ``custom_search`` emits the ``bing_custom_search_preview`` tool payload, which is
        the currently supported schema for Bing Custom Search in Foundry tools.
    """
    if not project_connection_id:
        settings = _load_foundry_tool_settings()
        if variant == "custom_search":
            project_connection_id = settings.get("bing_custom_search_project_connection_id")
            instance_name = instance_name or settings.get("bing_custom_search_instance_name")
        else:
            project_connection_id = settings.get("bing_project_connection_id")
    project_connection_id = _require_string(project_connection_id, "project_connection_id")
    config: dict[str, Any] = {"project_connection_id": project_connection_id}
    if count is not None:
        config["count"] = count
    if market:
        config["market"] = market
    if set_lang:
        config["set_lang"] = set_lang
    if freshness:
        config["freshness"] = freshness
    config.update(kwargs)

    if variant == "custom_search":
        instance_name = _require_string(instance_name, "instance_name")
        config["instance_name"] = instance_name
        return {
            "type": "bing_custom_search_preview",
            "bing_custom_search_preview": {"search_configurations": [config]},
        }

    return {
        "type": "bing_grounding",
        "bing_grounding": {"search_configurations": [config]},
    }


def create_image_generation_tool(
    *,
    model: Literal["gpt-image-1"] | str | None = None,
    size: Literal["1024x1024", "1024x1536", "1536x1024", "auto"] | None = None,
    output_format: Literal["png", "webp", "jpeg"] | None = None,
    quality: Literal["low", "medium", "high", "auto"] | None = None,
    background: Literal["transparent", "opaque", "auto"] | None = None,
    partial_images: int | None = None,
    moderation: Literal["auto", "low"] | None = None,
    output_compression: int | None = None,
    **kwargs: Any,
) -> ImageGenTool:
    """Create an image generation tool configuration for Azure AI Projects."""
    return ImageGenTool(  # type: ignore[misc]
        model=model,  # type: ignore[arg-type]
        size=size,
        output_format=output_format,
        quality=quality,
        background=background,
        partial_images=partial_images,
        moderation=moderation,
        output_compression=output_compression,
        **kwargs,
    )


def create_mcp_tool(
    *,
    name: str,
    url: str | None = None,
    description: str | None = None,
    approval_mode: Literal["always_require", "never_require"] | dict[str, list[str]] | None = None,
    allowed_tools: list[str] | None = None,
    headers: dict[str, str] | None = None,
    project_connection_id: str | None = None,
    **kwargs: Any,
) -> MCPTool:
    """Create a hosted MCP tool configuration for Azure AI."""
    _require_string(name, "name")
    mcp = MCPTool(server_label=name.replace(" ", "_"), server_url=url or "", **kwargs)

    if description:
        mcp["server_description"] = description

    if project_connection_id:
        mcp["project_connection_id"] = project_connection_id
    elif headers:
        mcp["headers"] = headers

    if allowed_tools:
        mcp["allowed_tools"] = allowed_tools

    if approval_mode:
        if isinstance(approval_mode, str):
            mcp["require_approval"] = "always" if approval_mode == "always_require" else "never"
        else:
            if always_require := approval_mode.get("always_require_approval"):
                mcp["require_approval"] = {"always": {"tool_names": always_require}}
            if never_require := approval_mode.get("never_require_approval"):
                mcp["require_approval"] = {"never": {"tool_names": never_require}}

    return mcp


def create_fabric_data_agent_tool(*, project_connection_id: str | None = None) -> dict[str, Any]:
    """Create a Microsoft Fabric data agent tool payload.

    If ``project_connection_id`` is omitted, it falls back to
    ``FABRIC_PROJECT_CONNECTION_ID``.
    """
    if not project_connection_id:
        project_connection_id = _load_foundry_tool_settings().get("fabric_project_connection_id")
    project_connection_id = _require_string(project_connection_id, "project_connection_id")
    return {
        "type": "fabric_dataagent_preview",
        "fabric_dataagent_preview": {
            "project_connections": [{"project_connection_id": project_connection_id}],
        },
    }


def create_sharepoint_grounding_tool(*, project_connection_id: str | None = None) -> dict[str, Any]:
    """Create a SharePoint grounding tool payload.

    If ``project_connection_id`` is omitted, it falls back to
    ``SHAREPOINT_PROJECT_CONNECTION_ID``.
    """
    if not project_connection_id:
        project_connection_id = _load_foundry_tool_settings().get("sharepoint_project_connection_id")
    project_connection_id = _require_string(project_connection_id, "project_connection_id")
    return {
        "type": "sharepoint_grounding_preview",
        "sharepoint_grounding_preview": {
            "project_connections": [{"project_connection_id": project_connection_id}],
        },
    }


def create_azure_ai_search_tool(
    *,
    project_connection_id: str | None = None,
    index_name: str | None = None,
    query_type: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create an Azure AI Search tool payload.

    Environment-backed fallbacks (used when optional arguments are omitted):

    - ``project_connection_id`` falls back to ``AI_SEARCH_PROJECT_CONNECTION_ID``.
    - ``index_name`` falls back to ``AI_SEARCH_INDEX_NAME``.
    """
    if not project_connection_id or not index_name:
        settings = _load_foundry_tool_settings()
        project_connection_id = project_connection_id or settings.get("ai_search_project_connection_id")
        index_name = index_name or settings.get("ai_search_index_name")
    project_connection_id = _require_string(project_connection_id, "project_connection_id")
    index_name = _require_string(index_name, "index_name")
    index: dict[str, Any] = {
        "project_connection_id": project_connection_id,
        "index_name": index_name,
    }
    if query_type:
        index["query_type"] = query_type
    index.update(kwargs)
    return {
        "type": "azure_ai_search",
        "azure_ai_search": {"indexes": [index]},
    }


def create_browser_automation_tool(*, project_connection_id: str | None = None) -> dict[str, Any]:
    """Create a browser automation tool payload.

    If ``project_connection_id`` is omitted, it falls back to
    ``BROWSER_AUTOMATION_PROJECT_CONNECTION_ID``.
    """
    if not project_connection_id:
        project_connection_id = _load_foundry_tool_settings().get("browser_automation_project_connection_id")
    project_connection_id = _require_string(project_connection_id, "project_connection_id")
    return {
        "type": "browser_automation_preview",
        "browser_automation_preview": {
            "connection": {"project_connection_id": project_connection_id},
        },
    }


def create_openapi_tool(
    *,
    name: str,
    spec: Mapping[str, Any],
    description: str | None = None,
    auth: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create an OpenAPI tool payload."""
    _require_string(name, "name")
    config: dict[str, Any] = {"name": name, "spec": dict(spec)}
    if description:
        config["description"] = description
    if auth:
        config["auth"] = dict(auth)
    config.update(kwargs)
    return {"type": "openapi", "openapi": config}


def create_a2a_tool(
    *,
    project_connection_id: str | None = None,
    base_url: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create an A2A tool payload.

    Environment-backed fallbacks (used when optional arguments are omitted):

    - ``project_connection_id`` falls back to ``A2A_PROJECT_CONNECTION_ID``.
    - ``base_url`` falls back to ``A2A_ENDPOINT``.
    """
    if not project_connection_id or not base_url:
        settings = _load_foundry_tool_settings()
        project_connection_id = project_connection_id or settings.get("a2a_project_connection_id")
        base_url = base_url or settings.get("a2a_endpoint")
    project_connection_id = _require_string(project_connection_id, "project_connection_id")
    result: dict[str, Any] = {"type": "a2a_preview", "project_connection_id": project_connection_id}
    if base_url:
        result["base_url"] = base_url
    result.update(kwargs)
    return result
