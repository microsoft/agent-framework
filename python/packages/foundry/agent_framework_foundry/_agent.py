# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Foundry Agent for connecting to pre-configured agents in Foundry.

This module provides ``RawFoundryAgent`` and ``FoundryAgent`` — Agent subclasses
that connect to existing PromptAgents or HostedAgents in Foundry. Use
``FoundryAgent`` for the recommended experience with full middleware and telemetry.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, cast

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AgentMiddlewareLayer,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ContextProvider,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    RawAgent,
    load_settings,
)
from agent_framework._compaction import CompactionStrategy, TokenizerProtocol
from agent_framework.observability import AgentTelemetryLayer, ChatTelemetryLayer
from agent_framework_openai._chat_client import OpenAIChatOptions, RawOpenAIChatClient
from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from ._tools import sanitize_foundry_response_tool

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from agent_framework import (
        Agent,
        ChatAndFunctionMiddlewareTypes,
        ContextProvider,
        MiddlewareTypes,
        ToolTypes,
    )

logger: logging.Logger = logging.getLogger("agent_framework.foundry")

AzureTokenProvider = Callable[[], str | Awaitable[str]]
AzureCredentialTypes = TokenCredential | AsyncTokenCredential


class FoundryAgentSettings(TypedDict, total=False):
    """Settings for Microsoft FoundryAgentClient resolved from args and environment.

    Keyword Args:
        project_endpoint: The Foundry project endpoint URL.
            Can be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
        agent_name: The name of the Foundry agent to connect to.
            Can be set via environment variable FOUNDRY_AGENT_NAME.
        agent_version: The version of the Foundry agent (for PromptAgents).
            Can be set via environment variable FOUNDRY_AGENT_VERSION.
    """

    project_endpoint: str | None
    agent_name: str | None
    agent_version: str | None


FoundryAgentOptionsT = TypeVar(
    "FoundryAgentOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIChatOptions",
    covariant=True,
)


class RawFoundryAgentChatClient(  # type: ignore[misc]
    RawOpenAIChatClient[FoundryAgentOptionsT],
    Generic[FoundryAgentOptionsT],
):
    """Raw Microsoft Foundry Agent chat client for connecting to pre-configured agents in Foundry.

    Connects to existing PromptAgents or HostedAgents via the Responses API.
    Does not create or delete agents — the agent must already exist in Foundry.

    This is a raw client without function invocation, chat middleware, or telemetry layers.
    Tools passed in options are validated (only ``FunctionTool`` allowed) but **not invoked** —
    the function invocation loop is handled by ``_FoundryAgentChatClient`` or a custom subclass
    that includes ``FunctionInvocationLayer``.

    Use this class as an extension point when building a custom client with specific middleware
    layers via subclassing::

        from agent_framework._tools import FunctionInvocationLayer
        from agent_framework.foundry import RawFoundryAgentChatClient


        class MyClient(FunctionInvocationLayer, RawFoundryAgentChatClient):
            pass


        agent = FoundryAgent(..., client_type=MyClient)
    """

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
        allow_preview: bool | None = None,
        default_headers: Mapping[str, str] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        instruction_role: str | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a raw Foundry Agent client.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
                Can also be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
            agent_name: The name of the Foundry agent to connect to.
                Can also be set via environment variable FOUNDRY_AGENT_NAME.
            agent_version: The version of the agent (required for PromptAgents, optional for HostedAgents).
                Can also be set via environment variable FOUNDRY_AGENT_VERSION.
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            default_headers: Additional HTTP headers for requests made through the OpenAI client.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            instruction_role: The role to use for 'instruction' messages.
            compaction_strategy: Optional per-client compaction override.
            tokenizer: Optional tokenizer for compaction strategies.
            additional_properties: Additional properties stored on the client instance.
        """
        settings = load_settings(
            FoundryAgentSettings,
            env_prefix="FOUNDRY_",
            project_endpoint=project_endpoint,
            agent_name=agent_name,
            agent_version=agent_version,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        resolved_endpoint = settings.get("project_endpoint")
        self.agent_name = settings.get("agent_name")
        self.agent_version = settings.get("agent_version")

        if not self.agent_name:
            raise ValueError(
                "Agent name is required. Set via 'agent_name' parameter or 'FOUNDRY_AGENT_NAME' environment variable."
            )

        # Create or use provided project client
        self._should_close_client = False
        if project_client is not None:
            self.project_client = project_client
        else:
            if not resolved_endpoint:
                raise ValueError(
                    "Either 'project_endpoint' or 'project_client' is required. "
                    "Set project_endpoint via parameter or 'FOUNDRY_PROJECT_ENDPOINT' environment variable."
                )
            if not credential:
                raise ValueError("Azure credential is required when using project_endpoint without a project_client.")
            project_client_kwargs: dict[str, Any] = {
                "endpoint": resolved_endpoint,
                "credential": credential,
                "user_agent": AGENT_FRAMEWORK_USER_AGENT,
            }
            if allow_preview is not None:
                project_client_kwargs["allow_preview"] = allow_preview
            self.project_client = AIProjectClient(**project_client_kwargs)
            self._should_close_client = True

        # Get OpenAI client from project
        async_client = self.project_client.get_openai_client()

        super().__init__(
            async_client=async_client,
            default_headers=default_headers,
            instruction_role=instruction_role,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
        )

    def _get_agent_reference(self) -> dict[str, str]:
        """Build the agent reference dict for the Responses API."""
        ref: dict[str, str] = {"name": self.agent_name, "type": "agent_reference"}  # type: ignore[dict-item]
        if self.agent_version:
            ref["version"] = self.agent_version
        return ref

    @override
    def as_agent(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: FoundryAgentOptionsT | Mapping[str, Any] | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        require_per_service_call_history_persistence: bool = False,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: Mapping[str, Any] | None = None,
    ) -> Agent[FoundryAgentOptionsT]:
        """Create a FoundryAgent that reuses this client's Foundry configuration."""
        function_tools = cast(
            FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None,
            tools,
        )

        return cast(
            "Agent[FoundryAgentOptionsT]",
            FoundryAgent(
                project_client=self.project_client,
                agent_name=self.agent_name,
                agent_version=self.agent_version,
                tools=function_tools,
                context_providers=context_providers,
                middleware=middleware,
                require_per_service_call_history_persistence=require_per_service_call_history_persistence,
                client_type=cast(type[RawFoundryAgentChatClient], self.__class__),
                id=id,
                name=self.agent_name if name is None else name,
                description=description,
                instructions=instructions,
                default_options=default_options,
                function_invocation_configuration=function_invocation_configuration,
                compaction_strategy=compaction_strategy,
                tokenizer=tokenizer,
                additional_properties=additional_properties,
            ),
        )

    @override
    async def _prepare_options(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Prepare options for the Responses API, injecting agent reference and validating tools."""
        # Validate tools — only FunctionTool allowed
        tools = options.get("tools", [])
        if tools:
            for tool_item in tools:
                if not isinstance(tool_item, FunctionTool):
                    raise TypeError(
                        f"Only FunctionTool objects are accepted for Foundry agents, "
                        f"got {type(tool_item).__name__}. Other tool types (MCPTool, dict schemas, "
                        f"hosted tools) must be defined on the Foundry agent definition in the service."
                    )

        # Prepare messages: extract system/developer messages as instructions
        prepared_messages, _instructions = self._prepare_messages_for_azure_ai(messages)

        # Call parent prepare_options (OpenAI Responses API format)
        run_options = await super()._prepare_options(prepared_messages, options, **kwargs)

        # Apply Azure AI schema transforms
        if "input" in run_options and isinstance(run_options["input"], list):
            run_options["input"] = self._transform_input_for_azure_ai(cast(list[dict[str, Any]], run_options["input"]))

        # Inject agent reference
        run_options["extra_body"] = {"agent_reference": self._get_agent_reference()}

        # Strip tools from request body - Foundry API rejects requests with both
        # agent_reference and tools present. FunctionTools are invoked client-side
        # by the function invocation layer, not sent to the service.
        run_options.pop("tools", None)
        run_options.pop("tool_choice", None)
        run_options.pop("parallel_tool_calls", None)

        return run_options

    @override
    def _check_model_presence(self, options: dict[str, Any]) -> None:
        """Skip model check — model is configured on the Foundry agent."""
        pass

    @override
    def _prepare_tools_for_openai(
        self,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None,
    ) -> list[Any]:
        """Prepare tools for Foundry agent Responses API calls.

        Mirrors ``RawFoundryChatClient`` sanitization so toolbox-fetched MCP
        tools with extra read-model fields continue to work through the agent
        surface.
        """
        response_tools = super()._prepare_tools_for_openai(tools)
        return [sanitize_foundry_response_tool(tool_item) for tool_item in response_tools]

    def _prepare_messages_for_azure_ai(self, messages: Sequence[Message]) -> tuple[list[Message], str | None]:
        """Extract system/developer messages as instructions for Azure AI.

        Foundry agents may not support system/developer messages directly.
        Instead, extract them as instructions to prepend.
        """
        prepared: list[Message] = []
        instructions_parts: list[str] = []
        for msg in messages:
            if msg.role in ("system", "developer"):
                if msg.text:
                    instructions_parts.append(msg.text)
            else:
                prepared.append(msg)
        instructions = "\n".join(instructions_parts) if instructions_parts else None
        return prepared, instructions

    def _transform_input_for_azure_ai(self, input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform input items to match Azure AI Projects expected schema.

        Azure AI Projects 'create responses' API expects 'type' at item level
        and 'annotations' for output_text content items.
        """
        transformed: list[dict[str, Any]] = []
        for item in input_items:
            new_item: dict[str, Any] = dict(item)

            if "role" in new_item and "type" not in new_item:
                new_item["type"] = "message"

            if (content := new_item.get("content")) and isinstance(content, list):
                new_content: list[Any] = []
                for content_item in content:  # type: ignore[union-attr]
                    if isinstance(content_item, MutableMapping):
                        if content_item.get("type") == "output_text" and "annotations" not in content_item:  # type: ignore[operator]
                            content_item["annotations"] = []
                        new_content.append(content_item)
                    else:
                        new_content.append(content_item)
                new_item["content"] = new_content

            transformed.append(new_item)

        return transformed

    async def close(self) -> None:
        """Close the project client if we created it."""
        if self._should_close_client:
            await self.project_client.close()


class _FoundryAgentChatClient(  # type: ignore[misc]
    FunctionInvocationLayer[FoundryAgentOptionsT],
    ChatMiddlewareLayer[FoundryAgentOptionsT],
    ChatTelemetryLayer[FoundryAgentOptionsT],
    RawFoundryAgentChatClient[FoundryAgentOptionsT],
    Generic[FoundryAgentOptionsT],
):
    """Microsoft Foundry Agent client with middleware, telemetry, and function invocation support.

    Connects to existing PromptAgents or HostedAgents in Foundry.

    Examples:
        .. code-block:: python

            from agent_framework import Agent
            from agent_framework.foundry import FoundryAgentClient
            from azure.identity import AzureCliCredential

            client = FoundryAgentClient(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-prompt-agent",
                agent_version="1.0",
                credential=AzureCliCredential(),
            )

            agent = Agent(client=client, tools=[my_function_tool])
            result = await agent.run("Hello!")
    """

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
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
        """Initialize a Foundry Agent client with full middleware support.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
            agent_name: The name of the Foundry agent to connect to.
            agent_version: The version of the agent (for PromptAgents).
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
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
            agent_name=agent_name,
            agent_version=agent_version,
            credential=credential,
            project_client=project_client,
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


class RawFoundryAgent(  # type: ignore[misc]
    RawAgent[FoundryAgentOptionsT],
):
    """Raw Microsoft Foundry Agent without agent-level middleware or telemetry.

    Connects to an existing PromptAgent or HostedAgent in Foundry.
    For full middleware and telemetry support, use :class:`FoundryAgent`.

    Examples:
        .. code-block:: python

            from agent_framework.foundry import RawFoundryAgent
            from azure.identity import AzureCliCredential

            agent = RawFoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-prompt-agent",
                agent_version="1.0",
                credential=AzureCliCredential(),
            )
            result = await agent.run("Hello!")
    """

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
        allow_preview: bool | None = None,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        client_type: type[RawFoundryAgentChatClient] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        default_options: FoundryAgentOptionsT | Mapping[str, Any] | None = None,
        require_per_service_call_history_persistence: bool = False,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize a Foundry Agent.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
                Can also be set via environment variable FOUNDRY_PROJECT_ENDPOINT.
            agent_name: The name of the Foundry agent to connect to.
                Can also be set via environment variable FOUNDRY_AGENT_NAME.
            agent_version: The version of the agent (required for PromptAgents, optional for HostedAgents).
                Can also be set via environment variable FOUNDRY_AGENT_VERSION.
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            tools: Function tools to provide to the agent. Only ``FunctionTool`` objects are accepted.
            context_providers: Optional context providers for injecting dynamic context.
            middleware: Optional agent-level middleware.
            client_type: Custom client class to use (must be a subclass of ``RawFoundryAgentChatClient``).
                Defaults to ``_FoundryAgentChatClient`` (full client middleware).
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            id: Optional local agent identifier.
            name: Optional display name for the local agent wrapper.
            description: Optional local description for the local agent wrapper.
            instructions: Optional instructions for the local agent wrapper.
            default_options: Default chat options for the local agent wrapper.
            require_per_service_call_history_persistence: Whether to require per-service-call
                chat history persistence when using local history providers.
            function_invocation_configuration: Optional function invocation configuration override.
            compaction_strategy: Optional agent-level in-run compaction override.
            tokenizer: Optional agent-level tokenizer override.
            additional_properties: Additional properties stored on the local agent wrapper.
        """
        # Create the client
        actual_client_type = client_type or _FoundryAgentChatClient
        if not issubclass(actual_client_type, RawFoundryAgentChatClient):
            raise TypeError(
                f"client_type must be a subclass of RawFoundryAgentChatClient, got {actual_client_type.__name__}"
            )

        client_kwargs: dict[str, Any] = {
            "project_endpoint": project_endpoint,
            "agent_name": agent_name,
            "agent_version": agent_version,
            "credential": credential,
            "project_client": project_client,
            "allow_preview": allow_preview,
            "env_file_path": env_file_path,
            "env_file_encoding": env_file_encoding,
        }
        if function_invocation_configuration is not None:
            if not issubclass(actual_client_type, FunctionInvocationLayer):
                raise TypeError(
                    "function_invocation_configuration requires a FunctionInvocationLayer-based client_type."
                )
            client_kwargs["function_invocation_configuration"] = function_invocation_configuration

        client = actual_client_type(**client_kwargs)

        super().__init__(
            client=client,  # type: ignore[arg-type]
            instructions=instructions,
            id=id,
            name=name,
            description=description,
            tools=tools,  # type: ignore[arg-type]
            default_options=cast(FoundryAgentOptionsT | None, default_options),
            context_providers=context_providers,
            middleware=middleware,
            require_per_service_call_history_persistence=require_per_service_call_history_persistence,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=dict(additional_properties) if additional_properties is not None else None,
        )

    async def configure_azure_monitor(
        self,
        enable_sensitive_data: bool = False,
        **kwargs: Any,
    ) -> None:
        """Setup observability with Azure Monitor (Microsoft Foundry integration).

        This method configures Azure Monitor for telemetry collection using the
        connection string from the Foundry project client (accessed via the internal client).

        Args:
            enable_sensitive_data: Enable sensitive data logging (prompts, responses).
                Should only be enabled in development/test environments. Default is False.
            **kwargs: Additional arguments passed to configure_azure_monitor().

        Raises:
            ImportError: If azure-monitor-opentelemetry-exporter is not installed.
        """
        from azure.core.exceptions import ResourceNotFoundError

        client = self.client
        if not isinstance(client, RawFoundryAgentChatClient):
            raise TypeError("configure_azure_monitor requires a RawFoundryAgentChatClient-based client.")

        try:
            conn_string = await client.project_client.telemetry.get_application_insights_connection_string()
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


class FoundryAgent(  # type: ignore[misc]
    AgentMiddlewareLayer,
    AgentTelemetryLayer,
    RawFoundryAgent[FoundryAgentOptionsT],
):
    """Microsoft Foundry Agent with full middleware and telemetry support.

    Connects to an existing PromptAgent or HostedAgent in Foundry.
    This is the recommended class for production use.

    Examples:
        .. code-block:: python

            from agent_framework.foundry import FoundryAgent
            from azure.identity import AzureCliCredential

            # Connect to a PromptAgent
            agent = FoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-prompt-agent",
                agent_version="1.0",
                credential=AzureCliCredential(),
                tools=[my_function_tool],
            )
            result = await agent.run("Hello!")

            # Connect to a HostedAgent (no version needed)
            agent = FoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-hosted-agent",
                credential=AzureCliCredential(),
            )

            # Custom client (e.g., raw client without client middleware)
            agent = FoundryAgent(
                project_endpoint="https://your-project.services.ai.azure.com",
                agent_name="my-agent",
                credential=AzureCliCredential(),
                client_type=RawFoundryAgentChatClient,
            )
    """

    def __init__(
        self,
        *,
        project_endpoint: str | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        credential: AzureCredentialTypes | None = None,
        project_client: AIProjectClient | None = None,
        allow_preview: bool | None = None,
        tools: FunctionTool | Callable[..., Any] | Sequence[FunctionTool | Callable[..., Any]] | None = None,
        context_providers: Sequence[ContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        client_type: type[RawFoundryAgentChatClient] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        default_options: FoundryAgentOptionsT | Mapping[str, Any] | None = None,
        require_per_service_call_history_persistence: bool = False,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        compaction_strategy: CompactionStrategy | None = None,
        tokenizer: TokenizerProtocol | None = None,
        additional_properties: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize a Foundry Agent with full middleware and telemetry.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
            agent_name: The name of the Foundry agent to connect to.
            agent_version: The version of the agent (for PromptAgents).
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            tools: Function tools to provide to the agent. Only ``FunctionTool`` objects are accepted.
            context_providers: Optional context providers.
            middleware: Optional agent-level middleware.
            client_type: Custom client class (must subclass ``RawFoundryAgentChatClient``).
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            id: Optional local agent identifier.
            name: Optional display name for the local agent wrapper.
            description: Optional local description for the local agent wrapper.
            instructions: Optional instructions for the local agent wrapper.
            default_options: Default chat options for the local agent wrapper.
            require_per_service_call_history_persistence: Whether to require per-service-call
                chat history persistence when using local history providers.
            function_invocation_configuration: Optional function invocation configuration override.
            compaction_strategy: Optional agent-level in-run compaction override.
            tokenizer: Optional agent-level tokenizer override.
            additional_properties: Additional properties stored on the local agent wrapper.
        """
        super().__init__(
            project_endpoint=project_endpoint,
            agent_name=agent_name,
            agent_version=agent_version,
            credential=credential,
            project_client=project_client,
            allow_preview=allow_preview,
            tools=tools,
            context_providers=context_providers,
            middleware=middleware,
            client_type=client_type,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            id=id,
            name=name,
            description=description,
            instructions=instructions,
            default_options=default_options,
            require_per_service_call_history_persistence=require_per_service_call_history_persistence,
            function_invocation_configuration=function_invocation_configuration,
            compaction_strategy=compaction_strategy,
            tokenizer=tokenizer,
            additional_properties=additional_properties,
        )
