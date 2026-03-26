# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Foundry Agent for connecting to pre-configured agents in Foundry.

This module provides ``RawFoundryAgent`` and ``FoundryAgent`` — Agent subclasses
that connect to existing PromptAgents or HostedAgents in Foundry. Use
``FoundryAgent`` for the recommended experience with full middleware and telemetry.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from agent_framework import (
    AgentMiddlewareLayer,
    BaseContextProvider,
    RawAgent,
)
from agent_framework.observability import AgentTelemetryLayer
from azure.ai.projects.aio import AIProjectClient

from ._entra_id_authentication import AzureCredentialTypes
from ._foundry_agent_client import (
    RawFoundryAgentChatClient,
    _FoundryAgentChatClient,  # pyright: ignore[reportPrivateUsage]
)

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from agent_framework._middleware import MiddlewareTypes
    from agent_framework._tools import FunctionTool
    from agent_framework_openai._chat_client import OpenAIChatOptions

logger: logging.Logger = logging.getLogger("agent_framework.foundry")

FoundryAgentOptionsT = TypeVar(
    "FoundryAgentOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="OpenAIChatOptions",
    covariant=True,
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
        context_providers: Sequence[BaseContextProvider] | None = None,
        client_type: type[RawFoundryAgentChatClient] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
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
            client_type: Custom client class to use (must be a subclass of ``RawFoundryAgentChatClient``).
                Defaults to ``_FoundryAgentChatClient`` (full client middleware).
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            kwargs: Additional keyword arguments passed to the Agent base class.
        """
        # Create the client
        actual_client_type = client_type or _FoundryAgentChatClient
        if not issubclass(actual_client_type, RawFoundryAgentChatClient):
            raise TypeError(
                f"client_type must be a subclass of RawFoundryAgentChatClient, got {actual_client_type.__name__}"
            )

        client = actual_client_type(
            project_endpoint=project_endpoint,
            agent_name=agent_name,
            agent_version=agent_version,
            credential=credential,
            project_client=project_client,
            allow_preview=allow_preview,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        super().__init__(
            client=client,  # type: ignore[arg-type]
            tools=tools,  # type: ignore[arg-type]
            context_providers=context_providers,
            **kwargs,
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

        from ._foundry_agent_client import RawFoundryAgentChatClient

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
        context_providers: Sequence[BaseContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        client_type: type[RawFoundryAgentChatClient] | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
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
            kwargs: Additional keyword arguments.
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
            **kwargs,
        )
