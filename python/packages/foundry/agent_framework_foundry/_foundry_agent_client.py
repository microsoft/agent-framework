# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Foundry Agent client for connecting to pre-configured agents in Foundry.

This module provides ``RawFoundryAgentClient`` and ``FoundryAgentClient`` for
communicating with PromptAgents and HostedAgents via the Responses API.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Generic, cast

from agent_framework._middleware import ChatMiddlewareLayer
from agent_framework._settings import load_settings
from agent_framework._telemetry import AGENT_FRAMEWORK_USER_AGENT
from agent_framework._tools import FunctionInvocationConfiguration, FunctionInvocationLayer, FunctionTool
from agent_framework._types import Message
from agent_framework.observability import ChatTelemetryLayer
from agent_framework_openai._chat_client import OpenAIChatOptions, RawOpenAIChatClient
from azure.ai.projects.aio import AIProjectClient

from ._entra_id_authentication import AzureCredentialTypes

logger: logging.Logger = logging.getLogger(__name__)

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
    from agent_framework import Agent, BaseContextProvider
    from agent_framework._middleware import (
        ChatMiddleware,
        ChatMiddlewareCallable,
        FunctionMiddleware,
        FunctionMiddlewareCallable,
        MiddlewareTypes,
    )
    from agent_framework._tools import ToolTypes


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
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
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
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            kwargs: Additional keyword arguments.
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

        super().__init__(async_client=async_client, **kwargs)

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
        context_providers: Sequence[BaseContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        **kwargs: Any,
    ) -> Agent[FoundryAgentOptionsT]:
        """Create a FoundryAgent that reuses this client's Foundry configuration."""
        from ._foundry_agent import FoundryAgent

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
                client_type=cast(type[RawFoundryAgentChatClient], self.__class__),
                id=id,
                name=self.agent_name if name is None else name,
                description=description,
                instructions=instructions,
                default_options=default_options,
                **kwargs,
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

        return run_options

    @override
    def _check_model_presence(self, options: dict[str, Any]) -> None:
        """Skip model check — model is configured on the Foundry agent."""
        pass

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
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        middleware: (
            Sequence[ChatMiddleware | ChatMiddlewareCallable | FunctionMiddleware | FunctionMiddlewareCallable] | None
        ) = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a Foundry Agent client with full middleware support.

        Keyword Args:
            project_endpoint: The Foundry project endpoint URL.
            agent_name: The name of the Foundry agent to connect to.
            agent_version: The version of the agent (for PromptAgents).
            credential: Azure credential for authentication.
            project_client: An existing AIProjectClient to use.
            allow_preview: Enables preview opt-in on internally-created AIProjectClient.
            env_file_path: Path to .env file for settings.
            env_file_encoding: Encoding for .env file.
            middleware: Optional sequence of middleware.
            function_invocation_configuration: Optional function invocation configuration.
            kwargs: Additional keyword arguments.
        """
        super().__init__(
            project_endpoint=project_endpoint,
            agent_name=agent_name,
            agent_version=agent_version,
            credential=credential,
            project_client=project_client,
            allow_preview=allow_preview,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            **kwargs,
        )
