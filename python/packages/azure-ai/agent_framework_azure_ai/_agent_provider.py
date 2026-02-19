# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Any, Generic, cast

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    Agent,
    BaseContextProvider,
    FunctionTool,
    MiddlewareTypes,
    normalize_tools,
)
from agent_framework._mcp import MCPTool
from agent_framework._settings import load_settings
from agent_framework._tools import ToolTypes
from agent_framework.azure._entra_id_authentication import AzureCredentialTypes
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import Agent as AzureAgent
from azure.ai.agents.models import ResponseFormatJsonSchema, ResponseFormatJsonSchemaType
from pydantic import BaseModel

from ._chat_client import AzureAIAgentClient, AzureAIAgentOptions
from ._shared import AzureAISettings, to_azure_ai_agent_tools

if sys.version_info >= (3, 13):
    from typing import Self, TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import Self, TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


# Type variable for options - allows typed Agent[TOptions] returns
# Default matches AzureAIAgentClient's default options type
OptionsCoT = TypeVar(
    "OptionsCoT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AzureAIAgentOptions",
    covariant=True,
)


class AzureAIAgentsProvider(Generic[OptionsCoT]):
    """Provider for Azure AI Agent Service V1 (Persistent Agents API).

    This provider enables creating, retrieving, and wrapping Azure AI agents as Agent
    instances. It manages the underlying AgentsClient lifecycle and provides a high-level
    interface for agent operations.

    The provider can be initialized with either:
    - An existing AgentsClient instance
    - Azure credentials and endpoint for automatic client creation

    Examples:
        Using credentials (auto-creates client):

        .. code-block:: python

            from agent_framework.azure import AzureAIAgentsProvider
            from azure.identity.aio import AzureCliCredential

            async with (
                AzureCliCredential() as credential,
                AzureAIAgentsProvider(credential=credential) as provider,
            ):
                agent = await provider.create_agent(
                    name="MyAgent",
                    instructions="You are a helpful assistant.",
                )
                result = await agent.run("Hello!")

        Using existing AgentsClient:

        .. code-block:: python

            from agent_framework.azure import AzureAIAgentsProvider
            from azure.ai.agents.aio import AgentsClient

            async with AgentsClient(endpoint=endpoint, credential=credential) as client:
                provider = AzureAIAgentsProvider(agents_client=client)
                agent = await provider.create_agent(name="MyAgent", instructions="...")
    """

    def __init__(
        self,
        agents_client: AgentsClient | None = None,
        *,
        project_endpoint: str | None = None,
        credential: AzureCredentialTypes | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the Azure AI Agents Provider.

        Args:
            agents_client: An existing AgentsClient to use. If provided, the provider
                will not manage its lifecycle.

        Keyword Args:
            project_endpoint: The Azure AI Project endpoint URL.
                Can also be set via AZURE_AI_PROJECT_ENDPOINT environment variable.
            credential: Azure credential for authentication. Accepts a TokenCredential,
                AsyncTokenCredential, or a callable token provider.
                Required if agents_client is not provided.
            env_file_path: Path to .env file for loading settings.
            env_file_encoding: Encoding of the .env file.

        Raises:
            ValueError: If required parameters are missing or invalid.
        """
        self._settings = load_settings(
            AzureAISettings,
            env_prefix="AZURE_AI_",
            project_endpoint=project_endpoint,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        self._should_close_client = False

        if agents_client is not None:
            self._agents_client = agents_client
        else:
            resolved_endpoint = self._settings.get("project_endpoint")
            if not resolved_endpoint:
                raise ValueError(
                    "Azure AI project endpoint is required. Provide 'project_endpoint' parameter "
                    "or set 'AZURE_AI_PROJECT_ENDPOINT' environment variable."
                )
            if not credential:
                raise ValueError("Azure credential is required when agents_client is not provided.")
            self._agents_client = AgentsClient(
                endpoint=resolved_endpoint,
                credential=credential,  # type: ignore[arg-type]
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )
            self._should_close_client = True

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the provider and release resources.

        Only closes the AgentsClient if it was created by this provider.
        """
        if self._should_close_client:
            await self._agents_client.close()

    async def create_agent(
        self,
        name: str,
        *,
        model: str | None = None,
        instructions: str | None = None,
        description: str | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsCoT | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
    ) -> Agent[OptionsCoT]:
        """Create a new agent on the Azure AI service and return a Agent.

        This method creates a persistent agent on the Azure AI service with the specified
        configuration and returns a local Agent instance for interaction.

        Args:
            name: The name for the agent.

        Keyword Args:
            model: The model deployment name to use. Falls back to
                AZURE_AI_MODEL_DEPLOYMENT_NAME environment variable if not provided.
            instructions: Instructions for the agent's behavior.
            description: A description of the agent's purpose.
            tools: Tools to make available to the agent.
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_providers: Context providers to include during agent invocation.

        Returns:
            Agent: A Agent instance configured with the created agent.

        Raises:
            ValueError: If model deployment name is not available.

        Examples:
            .. code-block:: python

                agent = await provider.create_agent(
                    name="WeatherAgent",
                    instructions="You are a helpful weather assistant.",
                    tools=get_weather,
                )
        """
        resolved_model = model or self._settings.get("model_deployment_name")
        if not resolved_model:
            raise ValueError(
                "Model deployment name is required. Provide 'model' parameter "
                "or set 'AZURE_AI_MODEL_DEPLOYMENT_NAME' environment variable."
            )

        # Extract response_format from default_options if present
        opts = dict(default_options) if default_options else {}
        response_format = opts.get("response_format")

        args: dict[str, Any] = {
            "model": resolved_model,
            "name": name,
        }

        if description:
            args["description"] = description
        if instructions:
            args["instructions"] = instructions

        # Handle response format
        if response_format and isinstance(response_format, type) and issubclass(response_format, BaseModel):
            args["response_format"] = self._create_response_format_config(response_format)

        # Normalize and convert tools
        # Local MCP tools (MCPTool) are handled by Agent at runtime, not stored on the Azure agent
        normalized_tools = normalize_tools(tools)
        if normalized_tools:
            # Collect all non-MCP tools for Azure AI agent creation.
            # to_azure_ai_agent_tools handles FunctionTool, SDK Tool types (FileSearchTool, etc.), and dicts.
            non_mcp_tools: list[Any] = [t for t in normalized_tools if not isinstance(t, MCPTool)]
            if non_mcp_tools:
                # Pass run_options to capture tool_resources (e.g., for file search vector stores)
                run_options: dict[str, Any] = {}
                args["tools"] = to_azure_ai_agent_tools(non_mcp_tools, run_options)
                if "tool_resources" in run_options:
                    args["tool_resources"] = run_options["tool_resources"]

        # Create the agent on the service
        created_agent = await self._agents_client.create_agent(**args)

        # Create Agent wrapper
        return self._to_chat_agent_from_agent(
            created_agent,
            normalized_tools,
            default_options=default_options,
            middleware=middleware,
            context_providers=context_providers,
        )

    async def get_agent(
        self,
        id: str,
        *,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsCoT | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
    ) -> Agent[OptionsCoT]:
        """Retrieve an existing agent from the service and return a Agent.

        This method fetches an agent by ID from the Azure AI service
        and returns a local Agent instance for interaction.

        Args:
            id: The ID of the agent to retrieve from the service.

        Keyword Args:
            tools: Tools to make available to the agent. Required if the agent
                has function tools that need implementations.
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_providers: Context providers to include during agent invocation.

        Returns:
            Agent: A Agent instance configured with the retrieved agent.

        Raises:
            ValueError: If required function tools are not provided.

        Examples:
            .. code-block:: python

                agent = await provider.get_agent("agent-123")

                # With function tools
                agent = await provider.get_agent("agent-123", tools=my_function)
        """
        agent = await self._agents_client.get_agent(id)

        # Validate function tools
        normalized_tools = normalize_tools(tools)
        self._validate_function_tools(agent.tools, normalized_tools)

        return self._to_chat_agent_from_agent(
            agent,
            normalized_tools,
            default_options=default_options,
            middleware=middleware,
            context_providers=context_providers,
        )

    def as_agent(
        self,
        agent: AzureAgent,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: OptionsCoT | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
    ) -> Agent[OptionsCoT]:
        """Wrap an existing Agent SDK object as a Agent without making HTTP calls.

        Use this method when you already have an Agent object from a previous
        SDK operation and want to use it with the Agent Framework.

        Args:
            agent: The Agent object to wrap.
            tools: Tools to make available to the agent. Required if the agent
                has function tools that need implementations.
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_providers: Context providers to include during agent invocation.

        Returns:
            Agent: A Agent instance configured with the agent.

        Raises:
            ValueError: If required function tools are not provided.

        Examples:
            .. code-block:: python

                # Create agent directly with SDK
                sdk_agent = await agents_client.create_agent(
                    model="gpt-4",
                    name="MyAgent",
                    instructions="...",
                )

                # Wrap as Agent
                chat_agent = provider.as_agent(sdk_agent)
        """
        # Validate function tools
        normalized_tools = normalize_tools(tools)
        self._validate_function_tools(agent.tools, normalized_tools)

        return self._to_chat_agent_from_agent(
            agent,
            normalized_tools,
            default_options=default_options,
            middleware=middleware,
            context_providers=context_providers,
        )

    def _to_chat_agent_from_agent(
        self,
        agent: AzureAgent,
        provided_tools: Sequence[ToolTypes] | None = None,
        default_options: OptionsCoT | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
    ) -> Agent[OptionsCoT]:
        """Create a Agent from an Agent SDK object.

        Args:
            agent: The Agent SDK object.
            provided_tools: User-provided tools (including function implementations).
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_providers: Context providers to include during agent invocation.
        """
        # Create the underlying client
        client = AzureAIAgentClient(
            agents_client=self._agents_client,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_description=agent.description,
            should_cleanup_agent=False,  # Provider manages agent lifecycle
        )

        # Merge tools: convert agent's hosted tools + user-provided function tools
        merged_tools = self._merge_tools(agent.tools, provided_tools)

        return Agent(  # type: ignore[return-value]
            client=client,
            id=agent.id,
            name=agent.name,
            description=agent.description,
            instructions=agent.instructions,
            model_id=agent.model,
            tools=merged_tools,
            default_options=default_options,  # type: ignore[arg-type]
            middleware=middleware,
            context_providers=context_providers,
        )

    def _merge_tools(
        self,
        agent_tools: Sequence[Any] | None,
        provided_tools: Sequence[ToolTypes] | None,
    ) -> list[ToolTypes]:
        """Merge hosted tools from agent with user-provided function tools.

        Args:
            agent_tools: Tools from the agent definition (Azure AI format).
            provided_tools: User-provided tools (Agent Framework format).

        Returns:
            Combined list of tools for the Agent.
        """
        merged: list[ToolTypes] = []

        # Hosted tools (file_search, code_interpreter, bing_grounding, openapi, etc.)
        # are already defined on the server agent and will be read back by the client
        # at run time via agent_definition.tools. We skip them here to avoid sending
        # them again at request time (which causes API errors like unknown vector_store_ids).

        # Add user-provided function tools and MCP tools
        if provided_tools:
            for provided_tool in provided_tools:
                # FunctionTool - has implementation for function calling
                # MCPTool - Agent handles MCP connection and tool discovery at runtime
                if isinstance(provided_tool, (FunctionTool, MCPTool)):
                    merged.append(provided_tool)  # type: ignore[reportUnknownArgumentType]

        return merged

    def _validate_function_tools(
        self,
        agent_tools: Sequence[Any] | None,
        provided_tools: Sequence[ToolTypes] | None,
    ) -> None:
        """Validate that required function tools are provided.

        Raises:
            ValueError: If agent has function tools but user
                didn't provide implementations.
        """
        if not agent_tools:
            return

        # Get function tool names from agent definition
        function_tool_names: set[str] = set()
        for tool in agent_tools:
            if isinstance(tool, dict):
                tool_dict = cast(dict[str, Any], tool)
                if tool_dict.get("type") == "function":
                    func_def = cast(dict[str, Any], tool_dict.get("function", {}))
                    name = func_def.get("name")
                    if isinstance(name, str):
                        function_tool_names.add(name)
            elif hasattr(tool, "type") and tool.type == "function":
                func_attr = getattr(tool, "function", None)
                if func_attr and hasattr(func_attr, "name"):
                    function_tool_names.add(str(func_attr.name))

        if not function_tool_names:
            return

        # Get provided function names
        provided_names: set[str] = set()
        if provided_tools:
            for tool in provided_tools:
                if isinstance(tool, FunctionTool):
                    provided_names.add(tool.name)

        # Check for missing implementations
        missing = function_tool_names - provided_names
        if missing:
            raise ValueError(
                f"Agent has function tools that require implementations: {missing}. "
                "Provide these functions via the 'tools' parameter."
            )

    def _create_response_format_config(
        self,
        response_format: type[BaseModel],
    ) -> ResponseFormatJsonSchemaType:
        """Create response format configuration for Azure AI.

        Args:
            response_format: Pydantic model for structured output.

        Returns:
            Azure AI response format configuration.
        """
        return ResponseFormatJsonSchemaType(
            json_schema=ResponseFormatJsonSchema(
                name=response_format.__name__,
                schema=response_format.model_json_schema(),
            )
        )
