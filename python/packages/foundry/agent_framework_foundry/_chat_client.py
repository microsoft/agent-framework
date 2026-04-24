# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Literal

from agent_framework import (
    ChatMiddlewareLayer,
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
    AutoCodeInterpreterToolParam,
    CodeInterpreterTool,
    ImageGenTool,
    WebSearchApproximateLocation,
    WebSearchTool,
    WebSearchToolFilters,
)
from azure.ai.projects.models import FileSearchTool as ProjectsFileSearchTool
from azure.ai.projects.models import MCPTool as FoundryMCPTool
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from ._tools import _sanitize_foundry_response_tool, fetch_toolbox  # pyright: ignore[reportPrivateUsage]

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
    from agent_framework import ChatAndFunctionMiddlewareTypes, ToolTypes
    from azure.ai.projects.models import ToolboxVersionObject

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


class RawFoundryChatClient(  # type: ignore[misc]
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

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"  # type: ignore[reportIncompatibleVariableOverride, misc]
    SUPPORTS_RICH_FUNCTION_OUTPUT: ClassVar[bool] = False  # type: ignore[reportIncompatibleVariableOverride, misc]

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
                "credential": credential,  # type: ignore[arg-type]
                "user_agent": get_user_agent(),
            }
            if allow_preview is not None:
                project_client_kwargs["allow_preview"] = allow_preview
            project_client = AIProjectClient(**project_client_kwargs)

        super().__init__(
            model=resolved_model,
            async_client=project_client.get_openai_client(),
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
        """Prepare tools for Foundry Responses API calls.

        Foundry toolbox reads can surface MCP tool objects with extra fields
        (for example ``name``) that are accepted by the toolbox API but rejected
        by the Responses API. Sanitize those hosted-tool payloads before sending
        them downstream.
        """
        response_tools = super()._prepare_tools_for_openai(tools)
        return [_sanitize_foundry_response_tool(tool_item) for tool_item in response_tools]

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
        from azure.core.exceptions import ResourceNotFoundError

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

        from agent_framework.observability import create_metric_views, create_resource, enable_instrumentation

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
    def get_web_search_tool(  # type: ignore[override]
        *,
        user_location: dict[str, str] | None = None,
        search_context_size: Literal["low", "medium", "high"] | None = None,
        allowed_domains: list[str] | None = None,
        custom_search_configuration: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> WebSearchTool:
        """Create a web search tool configuration for Microsoft Foundry.

        Keyword Args:
            user_location: Location context with keys like "city", "country", "region", "timezone".
            search_context_size: Amount of context from search results ("low", "medium", "high").
            allowed_domains: List of domains to restrict search results to.
            custom_search_configuration: Custom Bing search configuration.
            **kwargs: Additional arguments passed to the SDK WebSearchTool constructor.

        Returns:
            A WebSearchTool ready to pass to an Agent.
        """
        ws_kwargs: dict[str, Any] = {**kwargs}
        if search_context_size:
            ws_kwargs["search_context_size"] = search_context_size
        if allowed_domains:
            ws_kwargs["filters"] = WebSearchToolFilters(allowed_domains=allowed_domains)
        if custom_search_configuration:
            ws_kwargs["custom_search_configuration"] = custom_search_configuration
        ws_tool = WebSearchTool(**ws_kwargs)
        if user_location:
            ws_tool.user_location = WebSearchApproximateLocation(
                city=user_location.get("city"),
                country=user_location.get("country"),
                region=user_location.get("region"),
                timezone=user_location.get("timezone"),
            )
        return ws_tool

    @staticmethod
    def get_image_generation_tool(  # type: ignore[override]
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

    # region Toolbox methods (instance methods — these hit the network)

    @experimental(feature_id=ExperimentalFeature.TOOLBOXES)
    async def get_toolbox(
        self,
        name: str,
        *,
        version: str | None = None,
    ) -> ToolboxVersionObject:
        """Fetch a Foundry toolbox by name.

        If ``version`` is omitted, resolves the toolbox's current default version
        (two requests). If ``version`` is specified, fetches that version directly
        (single request).

        Args:
            name: The name of the toolbox.

        Keyword Args:
            version: Optional immutable version identifier to pin to.

        Returns:
            A ``ToolboxVersionObject``. Pass its ``tools`` attribute to
            ``Agent(tools=toolbox.tools)``.

        Raises:
            azure.core.exceptions.ResourceNotFoundError: If the toolbox or
                the requested version does not exist.
        """
        return await fetch_toolbox(self.project_client, name, version)


class FoundryChatClient(  # type: ignore[misc]
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

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"  # type: ignore[reportIncompatibleVariableOverride, misc]

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
