# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal

from agent_framework import (
    ChatMiddlewareLayer,
    ChatResponseUpdate,
    Content,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    load_settings,
)
from agent_framework._compaction import CompactionStrategy, TokenizerProtocol
from agent_framework._feature_stage import ExperimentalFeature, experimental
from agent_framework._telemetry import get_user_agent
from agent_framework.observability import ChatTelemetryLayer
from agent_framework_openai._chat_client import OpenAIChatOptions, RawOpenAIChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    A2APreviewTool,
    AISearchIndexResource,
    AutoCodeInterpreterToolParam,
    AzureAISearchTool,
    AzureAISearchToolResource,
    BingCustomSearchConfiguration,
    BingCustomSearchPreviewTool,
    BingCustomSearchToolParameters,
    BingGroundingSearchConfiguration,
    BingGroundingSearchToolParameters,
    BingGroundingTool,
    BrowserAutomationPreviewTool,
    BrowserAutomationToolConnectionParameters,
    BrowserAutomationToolParameters,
    CodeInterpreterTool,
    ComputerUsePreviewTool,
    FabricDataAgentToolParameters,
    ImageGenTool,
    MemorySearchPreviewTool,
    MicrosoftFabricPreviewTool,
    SharepointGroundingToolParameters,
    SharepointPreviewTool,
    ToolProjectConnection,
    WebSearchApproximateLocation,
    WebSearchTool,
    WebSearchToolFilters,
)
from azure.ai.projects.models import FileSearchTool as ProjectsFileSearchTool
from azure.ai.projects.models import MCPTool as FoundryMCPTool
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from agent_framework_foundry._oauth_helpers import try_parse_oauth_consent_event

from ._tools import _sanitize_foundry_response_tool  # pyright: ignore[reportPrivateUsage]

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover

if TYPE_CHECKING:
    from agent_framework import ChatAndFunctionMiddlewareTypes, ToolTypes

logger: logging.Logger = logging.getLogger("agent_framework.foundry")

AzureTokenProvider = Callable[[], str | Awaitable[str]]
AzureCredentialTypes = TokenCredential | AsyncTokenCredential


class FoundrySettings(TypedDict, total=False):
    """Settings for Microsoft FoundryChatClient resolved from args and environment.

    Keyword Args:
        model: The model deployment name.
            Can be set via environment variable FOUNDRY_MODEL.
        project_endpoint: The Microsoft Foundry project endpoint URL.
            Can be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
    """

    model: str | None
    project_endpoint: str | None


def resolve_file_ids(file_ids: Sequence[str | Content] | None) -> list[str] | None:
    """Resolve file IDs from strings or hosted-file Content objects."""
    if not file_ids:
        return None

    resolved: list[str] = []
    for item in file_ids:
        if isinstance(item, str):
            if not item:
                raise ValueError("file_ids must not contain empty strings.")
            resolved.append(item)
        elif isinstance(item, Content):
            if item.type != "hosted_file":
                raise ValueError(
                    f"Unsupported Content type {item.type!r} for code interpreter file_ids. "
                    "Only Content.from_hosted_file() is supported."
                )
            if item.file_id is None:
                raise ValueError(
                    "Content.from_hosted_file() item is missing a file_id. "
                    "Ensure the Content object has a valid file_id before using it in file_ids."
                )
            resolved.append(item.file_id)

    return resolved if resolved else None


FoundryChatOptionsT = TypeVar(
    "FoundryChatOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIChatOptions",
    covariant=True,
)

FoundryChatOptions = OpenAIChatOptions


class RawFoundryChatClient(
    RawOpenAIChatClient[FoundryChatOptionsT],
    Generic[FoundryChatOptionsT],
):
    """Raw Microsoft Foundry chat client using the OpenAI Responses API via a Foundry project.

    This client creates an OpenAI-compatible client from a Foundry project
    and delegates to ``RawOpenAIChatClient`` for request handling.

    Environment variables:
        - ``FOUNDRY_PROJECT_ENDPOINT`` to provide the Foundry project endpoint.
        - ``FOUNDRY_MODEL`` to provide the Foundry model deployment name.

    Warning:
        **This class should not normally be used directly.** Use ``FoundryChatClient``
        for a fully-featured client with middleware, telemetry, and function invocation.
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"
    SUPPORTS_RICH_FUNCTION_OUTPUT: ClassVar[bool] = False

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        project_client: AIProjectClient | None = None,
        model: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a raw Microsoft Foundry chat client.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
                Can also be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
            project_client: An existing AIProjectClient to use. If provided,
                the OpenAI client will be obtained via ``project_client.get_openai_client()``.
            model: The model deployment name.
                Can also be set via environment variable FOUNDRY_MODEL.
            credential: Azure credential or token provider for authentication.
                Required when using ``project_endpoint`` without a ``project_client``.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            default_headers: Additional HTTP headers for requests made through the OpenAI client.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            instruction_role: The role to use for 'instruction' messages.
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
        """
        foundry_settings = load_settings(
            FoundrySettings,
            env_prefix="FOUNDRY_",
            model=model,
            project_endpoint=project_endpoint,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        resolved_model = foundry_settings.get("model")
        if not resolved_model:
            raise ValueError("Model is required. Set via 'model' parameter or 'FOUNDRY_MODEL' environment variable.")

        project_endpoint = foundry_settings.get("project_endpoint")

        if project_endpoint is None and project_client is None:
            raise ValueError(
                "Either 'project_endpoint' or 'project_client' is required. "
                "Set project_endpoint via parameter or 'FOUNDRY_PROJECT_ENDPOINT' environment variable."
            )
        if not project_client:
            if not project_endpoint:
                raise ValueError(
                    "Azure AI project endpoint is required. Set via 'project_endpoint' parameter "
                    "or 'FOUNDRY_PROJECT_ENDPOINT' environment variable,"
                    "or pass in a AIProjectClient."
                )
            if not credential:
                raise ValueError("Azure credential is required when using project_endpoint without a project_client.")
            project_client_kwargs: dict[str, Any] = {
                "endpoint": project_endpoint,
                "credential": credential,
                "user_agent": get_user_agent(),
            }
            if allow_preview is not None:
                project_client_kwargs["allow_preview"] = allow_preview
            project_client = AIProjectClient(**project_client_kwargs)

        openai_kwargs: dict[str, Any] = {}
        if default_headers:
            openai_kwargs["default_headers"] = default_headers

        super().__init__(
            model=resolved_model,
            async_client=project_client.get_openai_client(**openai_kwargs),
            default_headers=default_headers,
            instruction_role=instruction_role,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
        )
        self.project_client = project_client

    @override
    def _check_model_presence(self, options: dict[str, Any]) -> None:
        if not options.get("model"):
            if not self.model:
                raise ValueError("model must be a non-empty string")
            options["model"] = self.model

    @override
    def _prepare_tools_for_openai(
        self,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
    ) -> list[Any]:
        response_tools = super()._prepare_tools_for_openai(tools)
        return [_sanitize_foundry_response_tool(tool_item) for tool_item in response_tools]

    @override
    def _parse_chunk_from_openai(
        self,
        event: Any,
        options: dict[str, Any],
        function_call_ids: dict[int, tuple[str, str]],
        seen_reasoning_delta_item_ids: set[str] | None = None,
    ) -> ChatResponseUpdate:
        """Parse streaming event, intercepting oauth_consent_request items."""
        update = try_parse_oauth_consent_event(event, self.model)
        if update is not None:
            return update
        return super()._parse_chunk_from_openai(event, options, function_call_ids, seen_reasoning_delta_item_ids)

    async def configure_azure_monitor(
        self,
        enable_sensitive_data: bool = False,
        **kwargs: Any,
    ) -> None:
        """Setup observability with Azure Monitor (Microsoft Foundry integration).

        This method configures Azure Monitor for telemetry collection using the
        connection string from the Foundry project client.

        Args:
            enable_sensitive_data: Enable sensitive data logging (prompts, responses).
                Should only be enabled in development/test environments. Default is False.
            **kwargs: Additional arguments passed to configure_azure_monitor().
                Common options include:
                - enable_live_metrics (bool): Enable Azure Monitor Live Metrics
                - credential (TokenCredential): Azure credential for Entra ID auth
                - resource (Resource): Custom OpenTelemetry resource

        Raises:
            ImportError: If azure-monitor-opentelemetry-exporter is not installed.
        """
        from agent_framework.observability import (
            OBSERVABILITY_SETTINGS,
            create_metric_views,
            create_resource,
            enable_instrumentation,
        )
        from azure.core.exceptions import ResourceNotFoundError

        if OBSERVABILITY_SETTINGS.is_user_disabled:
            logger.info(
                "FoundryChatClient.configure_azure_monitor(): Skipping setup because instrumentation was "
                "explicitly disabled via disable_instrumentation(). Call enable_instrumentation(force=True) "
                "to re-enable, then re-invoke configure_azure_monitor()."
            )
            return

        try:
            conn_string = await self.project_client.telemetry.get_application_insights_connection_string()
        except ResourceNotFoundError:
            logger.warning(
                "No Application Insights connection string found for the Foundry project. "
                "Please ensure Application Insights is configured in your project, "
                "or call configure_otel_providers() manually with custom exporters."
            )
            return

        try:
            from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "azure-monitor-opentelemetry is required for Azure Monitor integration. "
                "Install it with: pip install azure-monitor-opentelemetry"
            ) from exc

        if "resource" not in kwargs:
            kwargs["resource"] = create_resource()

        configure_azure_monitor(
            connection_string=conn_string,
            views=create_metric_views(),
            **kwargs,
        )

        enable_instrumentation(enable_sensitive_data=enable_sensitive_data)

    # region Tool factory methods (override OpenAI defaults with Foundry versions)

    @staticmethod
    def get_code_interpreter_tool(  # type: ignore[override]
        *,
        file_ids: list[str | Content] | None = None,
        container: Literal["auto"] | dict[str, Any] = "auto",
        **kwargs: Any,
    ) -> CodeInterpreterTool:
        """Create a code interpreter tool configuration for Foundry.

        Keyword Args:
            file_ids: Optional list of file IDs or Content objects to make available.
            container: Container configuration. Use "auto" for automatic management.
            **kwargs: Additional arguments passed to the SDK CodeInterpreterTool constructor.

        Returns:
            A CodeInterpreterTool ready to pass to an Agent.
        """
        if file_ids is None and isinstance(container, dict):
            file_ids = container.get("file_ids")
        resolved = resolve_file_ids(file_ids)
        tool_container = AutoCodeInterpreterToolParam(file_ids=resolved)
        return CodeInterpreterTool(container=tool_container, **kwargs)

    @staticmethod
    def get_file_search_tool(
        *,
        vector_store_ids: list[str],
        max_num_results: int | None = None,
        ranking_options: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ProjectsFileSearchTool:
        """Create a file search tool configuration for Foundry.

        Keyword Args:
            vector_store_ids: List of vector store IDs to search.
            max_num_results: Maximum number of results to return (1-50).
            ranking_options: Ranking options for search results.
            filters: A filter to apply (ComparisonFilter or CompoundFilter).
            **kwargs: Additional arguments passed to the SDK FileSearchTool constructor.

        Returns:
            A FileSearchTool ready to pass to an Agent.
        """
        if not vector_store_ids:
            raise ValueError("File search tool requires 'vector_store_ids' to be specified.")
        return ProjectsFileSearchTool(
            vector_store_ids=vector_store_ids,
            max_num_results=max_num_results,
            ranking_options=ranking_options,  # type: ignore[arg-type]
            filters=filters,  # type: ignore[arg-type]
            **kwargs,
        )

    @staticmethod
    def get_web_search_tool(
        *,
        user_location: dict[str, str] | None = None,
        search_context_size: Literal["low", "medium", "high"] | None = None,
        allowed_domains: list[str] | None = None,
        custom_search_configuration: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> WebSearchTool:
        """Create a Web Search tool configuration for Microsoft Foundry.

        **Choosing a web grounding tool.** Foundry exposes three options that all reach
        the public web via Bing. Pick the one that matches your scenario:

        * :py:meth:`get_web_search_tool` (this one, GA) — recommended starting point.
          The Bing resource is managed by Microsoft, no extra Azure setup is required,
          and only Azure OpenAI models are supported. Parameters are limited to
          ``user_location`` and ``search_context_size``.
        * :py:meth:`get_bing_grounding_tool` (preview) — use when you need finer Bing parameters (``count``,
          ``freshness``, ``market``, ``set_lang``), want to ground non-OpenAI
          Foundry models, or are migrating from Grounding with Bing Search on the
          classic agents platform. You manage the Grounding with Bing Search
          resource yourself (Contributor/Owner to create the resource, Foundry
          Project Manager to wire the connection).
        * :py:meth:`get_bing_custom_search_tool` (preview) — use when you need to
          restrict grounding to a curated set of domains defined in a Bing Custom
          Search instance.

        For all three, search data flows outside the Azure compliance boundary. See
        https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-overview for
        the full comparison.

        Keyword Args:
            user_location: Location context with keys like ``"city"``, ``"country"``,
                ``"region"``, ``"timezone"``.
            search_context_size: Amount of context from search results
                (``"low"``, ``"medium"``, ``"high"``).
            allowed_domains: List of domains to restrict search results to. Wrapped
                into ``WebSearchToolFilters`` and passed as the ``filters`` field on
                the SDK ``WebSearchTool``.
            custom_search_configuration: Custom Bing search configuration for
                domain-restricted scenarios.
            **kwargs: Additional arguments passed to the SDK ``WebSearchTool``
                constructor.

        Returns:
            A ``WebSearchTool`` ready to pass to an Agent.
        """
        ws_kwargs: dict[str, Any] = {**kwargs}
        if search_context_size:
            ws_kwargs["search_context_size"] = search_context_size
        if allowed_domains:
            ws_kwargs["filters"] = WebSearchToolFilters(allowed_domains=allowed_domains)
        if custom_search_configuration:
            ws_kwargs["custom_search_configuration"] = custom_search_configuration
        if user_location:
            ws_kwargs["user_location"] = WebSearchApproximateLocation(
                city=user_location.get("city"),
                country=user_location.get("country"),
                region=user_location.get("region"),
                timezone=user_location.get("timezone"),
            )
        return WebSearchTool(**ws_kwargs)

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_TOOLS)
    def get_bing_grounding_tool(
        *,
        connection_id: str,
        market: str | None = None,
        set_lang: str | None = None,
        count: int | None = None,
        freshness: str | None = None,
        **kwargs: Any,
    ) -> BingGroundingTool:
        """Create a Grounding with Bing Search tool configuration for Foundry.

        Use this factory when :py:meth:`get_web_search_tool` is too restrictive — for
        example when you need ``count``/``freshness``/``market``/``set_lang``
        parameters, want to ground a non-OpenAI Foundry model, or are migrating an
        agent that already uses Grounding with Bing Search on the classic agents
        platform. You manage the Grounding with Bing Search Azure resource yourself
        (Contributor or Owner to create the resource, Foundry Project Manager to
        create the project connection). Search data flows outside the Azure
        compliance boundary.

        For domain-restricted grounding to a curated allow-list, use
        :py:meth:`get_bing_custom_search_tool` instead. For a zero-setup default that
        works for most agents, see :py:meth:`get_web_search_tool`. The full
        comparison lives at
        https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-overview.

        Keyword Args:
            connection_id: The Foundry project connection ID for the Grounding with
                Bing Search resource.
            market: Optional Bing market identifier (e.g. ``"en-US"``).
            set_lang: Optional UI language code passed to the Bing API.
            count: Optional number of search results to return.
            freshness: Optional time-range filter for search results. See
                https://learn.microsoft.com/bing/search-apis/bing-web-search/reference/query-parameters
                for accepted values.
            **kwargs: Additional arguments forwarded to the SDK
                ``BingGroundingSearchConfiguration``.

        Returns:
            A ``BingGroundingTool`` ready to pass to an Agent.
        """
        config_kwargs: dict[str, Any] = {
            **kwargs,
            "project_connection_id": connection_id,
        }
        if market is not None:
            config_kwargs["market"] = market
        if set_lang is not None:
            config_kwargs["set_lang"] = set_lang
        if count is not None:
            config_kwargs["count"] = count
        if freshness is not None:
            config_kwargs["freshness"] = freshness
        return BingGroundingTool(
            bing_grounding=BingGroundingSearchToolParameters(
                search_configurations=[BingGroundingSearchConfiguration(**config_kwargs)],
            ),
        )

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS)
    def get_bing_custom_search_tool(
        *,
        connection_id: str,
        instance_name: str,
        market: str | None = None,
        set_lang: str | None = None,
        count: int | None = None,
        freshness: str | None = None,
        **kwargs: Any,
    ) -> BingCustomSearchPreviewTool:
        """Create a Grounding with Bing Custom Search tool configuration for Foundry.

        Use this factory (preview) when you need to restrict grounding to a curated
        list of domains. The allow/block list is defined ahead of time on a Bing
        Custom Search resource (in the Bing portal) and referenced here by
        ``instance_name``. Like the other Bing-backed tools, search data flows
        outside the Azure compliance boundary, and you must create the Bing Custom
        Search resource yourself.

        For unrestricted public-web grounding with no extra Azure setup, prefer
        :py:meth:`get_web_search_tool`. For unrestricted grounding with finer Bing
        parameters or non-OpenAI models, prefer :py:meth:`get_bing_grounding_tool`.
        See
        https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-overview
        for the full comparison.

        Keyword Args:
            connection_id: The Foundry project connection ID for the Grounding with
                Bing Custom Search resource.
            instance_name: The custom configuration instance name defined on the
                Bing Custom Search resource.
            market: Optional Bing market identifier (e.g. ``"en-US"``).
            set_lang: Optional UI language code passed to the Bing API.
            count: Optional number of search results to return.
            freshness: Optional time-range filter for search results.
            **kwargs: Additional arguments forwarded to the SDK
                ``BingCustomSearchConfiguration``.

        Returns:
            A ``BingCustomSearchPreviewTool`` ready to pass to an Agent.
        """
        config_kwargs: dict[str, Any] = {
            **kwargs,
            "project_connection_id": connection_id,
            "instance_name": instance_name,
        }
        if market is not None:
            config_kwargs["market"] = market
        if set_lang is not None:
            config_kwargs["set_lang"] = set_lang
        if count is not None:
            config_kwargs["count"] = count
        if freshness is not None:
            config_kwargs["freshness"] = freshness
        return BingCustomSearchPreviewTool(
            bing_custom_search_preview=BingCustomSearchToolParameters(
                search_configurations=[BingCustomSearchConfiguration(**config_kwargs)],
            ),
        )

    @staticmethod
    def get_image_generation_tool(
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
        """Create an image generation tool configuration for Foundry.

        Keyword Args:
            model: The model to use for image generation.
            size: Output image size.
            output_format: Output image format.
            quality: Output image quality.
            background: Background transparency setting.
            partial_images: Number of partial images to return during generation.
            moderation: Moderation level.
            output_compression: Compression level.
            **kwargs: Additional arguments passed to the SDK ImageGenTool constructor.

        Returns:
            An ImageGenTool ready to pass to an Agent.
        """
        return ImageGenTool(
            model=model,
            size=size,
            output_format=output_format,
            quality=quality,
            background=background,
            partial_images=partial_images,
            moderation=moderation,
            output_compression=output_compression,
            **kwargs,
        )

    @staticmethod
    def get_mcp_tool(
        *,
        name: str,
        url: str | None = None,
        description: str | None = None,
        approval_mode: Literal["always_require", "never_require"] | dict[str, list[str]] | None = None,
        allowed_tools: list[str] | None = None,
        headers: dict[str, str] | None = None,
        project_connection_id: str | None = None,
        **kwargs: Any,
    ) -> FoundryMCPTool:
        """Create a hosted MCP tool configuration for Foundry.

        This configures an MCP server that runs remotely on Azure AI, not locally.

        Keyword Args:
            name: A label/name for the MCP server.
            url: The URL of the MCP server. Required if project_connection_id is not provided.
            description: A description of what the MCP server provides.
            approval_mode: Tool approval mode ("always_require", "never_require", or dict).
            allowed_tools: List of allowed tool names from this MCP server.
            headers: HTTP headers to include in requests to the MCP server.
            project_connection_id: Foundry connection ID for managed MCP connections.
            **kwargs: Additional arguments passed to the SDK MCPTool constructor.

        Returns:
            An MCPTool configuration ready to pass to an Agent.

        Raises:
            ValueError: If neither ``url`` nor ``project_connection_id`` is supplied
                — one is required by the Foundry Responses API.
        """
        if not url and not project_connection_id:
            raise ValueError("MCP tool requires either 'url' or 'project_connection_id' to be specified.")

        mcp_kwargs: dict[str, Any] = {"server_label": name.replace(" ", "_"), **kwargs}
        if url:
            mcp_kwargs["server_url"] = url
        mcp = FoundryMCPTool(**mcp_kwargs)

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

    # endregion

    # region Experimental Foundry tool factories (preview SDK types)

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_TOOLS)
    def get_azure_ai_search_tool(
        *,
        index_connection_id: str,
        index_name: str,
        query_type: str | None = None,
        top_k: int | None = None,
        filter: str | None = None,
        index_asset_id: str | None = None,
        **kwargs: Any,
    ) -> AzureAISearchTool:
        """Create an Azure AI Search tool configuration for Foundry.

        Keyword Args:
            index_connection_id: The Foundry project connection ID for the Azure AI Search index.
            index_name: The name of the index to search.
            query_type: Optional query type (``"simple"``, ``"semantic"``, ``"vector"``,
                ``"vector_simple_hybrid"``, or ``"vector_semantic_hybrid"``).
            top_k: Optional number of documents to retrieve.
            filter: Optional OData filter expression.
            index_asset_id: Optional index asset id for the search resource.
            **kwargs: Additional arguments forwarded to the SDK ``AISearchIndexResource``.

        Returns:
            An ``AzureAISearchTool`` ready to pass to an Agent.
        """
        index_kwargs: dict[str, Any] = {
            **kwargs,
            "project_connection_id": index_connection_id,
            "index_name": index_name,
        }
        if query_type is not None:
            index_kwargs["query_type"] = query_type
        if top_k is not None:
            index_kwargs["top_k"] = top_k
        if filter is not None:
            index_kwargs["filter"] = filter
        if index_asset_id is not None:
            index_kwargs["index_asset_id"] = index_asset_id
        return AzureAISearchTool(
            azure_ai_search=AzureAISearchToolResource(indexes=[AISearchIndexResource(**index_kwargs)]),
        )

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS)
    def get_sharepoint_tool(
        *,
        connection_id: str,
        **kwargs: Any,
    ) -> SharepointPreviewTool:
        """Create a SharePoint grounding tool configuration for Foundry.

        Keyword Args:
            connection_id: The Foundry project connection ID for the SharePoint resource.
            **kwargs: Additional arguments forwarded to the SDK
                ``SharepointGroundingToolParameters``.

        Returns:
            A ``SharepointPreviewTool`` ready to pass to an Agent.
        """
        return SharepointPreviewTool(
            sharepoint_grounding_preview=SharepointGroundingToolParameters(
                project_connections=[ToolProjectConnection(project_connection_id=connection_id)],
                **kwargs,
            )
        )

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS)
    def get_fabric_tool(
        *,
        connection_id: str,
        **kwargs: Any,
    ) -> MicrosoftFabricPreviewTool:
        """Create a Microsoft Fabric data agent tool configuration for Foundry.

        Keyword Args:
            connection_id: The Foundry project connection ID for the Fabric data agent.
            **kwargs: Additional arguments forwarded to the SDK
                ``FabricDataAgentToolParameters``.

        Returns:
            A ``MicrosoftFabricPreviewTool`` ready to pass to an Agent.
        """
        return MicrosoftFabricPreviewTool(
            fabric_dataagent_preview=FabricDataAgentToolParameters(
                project_connections=[ToolProjectConnection(project_connection_id=connection_id)],
                **kwargs,
            )
        )

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS)
    def get_memory_search_tool(
        *,
        memory_store_name: str,
        scope: str,
        search_options: Any | None = None,
        update_delay: int | None = None,
        **kwargs: Any,
    ) -> MemorySearchPreviewTool:
        """Create a Memory Search tool configuration for Foundry.

        Keyword Args:
            memory_store_name: The name of the memory store to use.
            scope: The namespace used to group and isolate memories (e.g. a user ID).
                Use ``"{{$userId}}"`` to scope memories to the current signed-in user.
            search_options: Optional ``MemorySearchOptions`` instance.
            update_delay: Optional seconds to wait before updating memories after inactivity.
            **kwargs: Additional arguments forwarded to the SDK ``MemorySearchPreviewTool``.

        Returns:
            A ``MemorySearchPreviewTool`` ready to pass to an Agent.
        """
        params: dict[str, Any] = {
            **kwargs,
            "memory_store_name": memory_store_name,
            "scope": scope,
        }
        if search_options is not None:
            params["search_options"] = search_options
        if update_delay is not None:
            params["update_delay"] = update_delay
        return MemorySearchPreviewTool(**params)

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS)
    def get_computer_use_tool(
        *,
        environment: str,
        display_width: int,
        display_height: int,
        **kwargs: Any,
    ) -> ComputerUsePreviewTool:
        """Create a Computer Use tool configuration for Foundry.

        Keyword Args:
            environment: The computer environment to control. One of ``"windows"``,
                ``"mac"``, ``"linux"``, ``"ubuntu"``, or ``"browser"``.
            display_width: The width of the computer display.
            display_height: The height of the computer display.
            **kwargs: Additional arguments forwarded to the SDK ``ComputerUsePreviewTool``.

        Returns:
            A ``ComputerUsePreviewTool`` ready to pass to an Agent.
        """
        return ComputerUsePreviewTool(
            environment=environment,
            display_width=display_width,
            display_height=display_height,
            **kwargs,
        )

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS)
    def get_browser_automation_tool(
        *,
        connection_id: str,
        **kwargs: Any,
    ) -> BrowserAutomationPreviewTool:
        """Create a Browser Automation tool configuration for Foundry.

        Keyword Args:
            connection_id: The Foundry project connection ID for the Azure Playwright resource.
            **kwargs: Additional arguments forwarded to the SDK
                ``BrowserAutomationToolParameters``.

        Returns:
            A ``BrowserAutomationPreviewTool`` ready to pass to an Agent.
        """
        return BrowserAutomationPreviewTool(
            browser_automation_preview=BrowserAutomationToolParameters(
                connection=BrowserAutomationToolConnectionParameters(project_connection_id=connection_id),
                **kwargs,
            )
        )

    @staticmethod
    @experimental(feature_id=ExperimentalFeature.FOUNDRY_PREVIEW_TOOLS)
    def get_a2a_tool(
        *,
        base_url: str | None = None,
        agent_card_path: str | None = None,
        project_connection_id: str | None = None,
        **kwargs: Any,
    ) -> A2APreviewTool:
        """Create an Agent-to-Agent (A2A) tool configuration for Foundry.

        Keyword Args:
            base_url: Base URL of the remote A2A agent.
            agent_card_path: Path to the agent card relative to ``base_url``.
                Defaults to ``"/.well-known/agent-card.json"`` server-side.
            project_connection_id: Foundry connection ID for the A2A server. Stores
                authentication and other connection details.
            **kwargs: Additional arguments forwarded to the SDK ``A2APreviewTool``.

        Returns:
            An ``A2APreviewTool`` ready to pass to an Agent.
        """
        params: dict[str, Any] = dict(kwargs)
        if base_url is not None:
            params["base_url"] = base_url
        if agent_card_path is not None:
            params["agent_card_path"] = agent_card_path
        if project_connection_id is not None:
            params["project_connection_id"] = project_connection_id
        return A2APreviewTool(**params)

    # endregion


class FoundryChatClient(
    FunctionInvocationLayer[FoundryChatOptionsT],
    ChatMiddlewareLayer[FoundryChatOptionsT],
    ChatTelemetryLayer[FoundryChatOptionsT],
    RawFoundryChatClient[FoundryChatOptionsT],
    Generic[FoundryChatOptionsT],
):
    """Microsoft Foundry chat client using the OpenAI Responses API.

    Creates an OpenAI-compatible client from a Foundry project
    with middleware, telemetry, and function invocation support.

    Environment variables:
        - ``FOUNDRY_PROJECT_ENDPOINT`` to provide the Foundry project endpoint.
        - ``FOUNDRY_MODEL`` to provide the Foundry model deployment name.

    Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
                Can also be set via environment variable ``FOUNDRY_PROJECT_ENDPOINT``.
            project_client: An existing AIProjectClient to use.
            model: The model deployment name.
                Can also be set via environment variable ``FOUNDRY_MODEL``.
            credential: Azure credential or token provider for authentication.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            env_file_path: Path to .env file for settings.
        env_file_encoding: Encoding for .env file.
        instruction_role: The role to use for 'instruction' messages.
        middleware: Optional sequence of middleware.
        function_invocation_configuration: Optional function invocation configuration.

    Examples:
        .. code-block:: python

            from azure.identity import AzureCliCredential
            from agent_framework_foundry import FoundryChatClient

            client = FoundryChatClient(
                project_endpoint="https://your-project.services.ai.azure.com",
                model="gpt-4o",
                credential=AzureCliCredential(),
            )

            # Or using an existing AIProjectClient
            from azure.ai.projects.aio import AIProjectClient

            project_client = AIProjectClient(
                endpoint="https://your-project.services.ai.azure.com",
                credential=AzureCliCredential(),
            )
            client = FoundryChatClient(
                project_client=project_client,
                model="gpt-4o",
            )
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        project_client: AIProjectClient | None = None,
        model: str | None = None,
        credential: AzureCredentialTypes | AzureTokenProvider | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
        middleware: (Sequence[ChatAndFunctionMiddlewareTypes] | None) = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    ) -> None:
        """Initialize a Foundry chat client.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
                Can also be set via environment variable ``FOUNDRY_PROJECT_ENDPOINT``.
            project_client: An existing AIProjectClient to use.
            model: The model deployment name.
                Can also be set via environment variable ``FOUNDRY_MODEL``.
            credential: Azure credential or token provider for authentication.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            default_headers: Additional HTTP headers for requests made through the OpenAI client.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            instruction_role: The role to use for 'instruction' messages.
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
            middleware: Optional sequence of middleware.
            function_invocation_configuration: Optional function invocation configuration.
        """
        super().__init__(
            project_endpoint=project_endpoint,
            project_client=project_client,
            model=model,
            credential=credential,
            allow_preview=allow_preview,
            default_headers=default_headers,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            instruction_role=instruction_role,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
        )
