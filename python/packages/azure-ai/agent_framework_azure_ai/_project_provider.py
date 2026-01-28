# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import Callable, MutableMapping, Sequence
from typing import Any, Generic

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    ChatAgent,
    ContextProvider,
    FunctionTool,
    Middleware,
    ToolProtocol,
    get_logger,
    normalize_tools,
)
from agent_framework._mcp import MCPTool
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    AgentReference,
    AgentVersionDetails,
    PromptAgentDefinition,
    PromptAgentDefinitionText,
)
from azure.ai.projects.models import (
    FunctionTool as AzureFunctionTool,
)
from azure.core.credentials_async import AsyncTokenCredential
from pydantic import ValidationError

from ._client import AzureAIClient, AzureAIProjectAgentOptions
from ._shared import AzureAISettings, create_text_format_config, from_azure_ai_tools, to_azure_ai_tools

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self, TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import Self, TypedDict  # type: ignore # pragma: no cover


logger = get_logger("agent_framework.azure")


# Type variable for options - allows typed ChatAgent[TOptions] returns
# Default matches AzureAIClient's default options type
TOptions_co = TypeVar(
    "TOptions_co",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AzureAIProjectAgentOptions",
    covariant=True,
)


class AzureAIProjectAgentProvider(Generic[TOptions_co]):
    """Provider for Azure AI Agent Service (Responses API).

    This provider allows you to create, retrieve, and manage Azure AI agents
    using the AIProjectClient from the Azure AI Projects SDK.

    Examples:
        Using with explicit AIProjectClient:

        .. code-block:: python

            from agent_framework.azure import AzureAIProjectAgentProvider
            from azure.ai.projects.aio import AIProjectClient
            from azure.identity.aio import DefaultAzureCredential

            async with AIProjectClient(endpoint, credential) as client:
                provider = AzureAIProjectAgentProvider(client)
                agent = await provider.create_agent(
                    name="MyAgent",
                    model="gpt-4",
                    instructions="You are a helpful assistant.",
                )
                response = await agent.run("Hello!")

        Using with credential and endpoint (auto-creates client):

        .. code-block:: python

            from agent_framework.azure import AzureAIProjectAgentProvider
            from azure.identity.aio import DefaultAzureCredential

            async with AzureAIProjectAgentProvider(credential=credential) as provider:
                agent = await provider.create_agent(
                    name="MyAgent",
                    model="gpt-4",
                    instructions="You are a helpful assistant.",
                )
                response = await agent.run("Hello!")
    """

    def __init__(
        self,
        project_client: AIProjectClient | None = None,
        *,
        project_endpoint: str | None = None,
        model: str | None = None,
        credential: AsyncTokenCredential | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an Azure AI Project Agent Provider.

        Args:
            project_client: An existing AIProjectClient to use. If not provided, one will be created.
            project_endpoint: The Azure AI Project endpoint URL.
                Can also be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
                Ignored when a project_client is passed.
            model: The default model deployment name to use for agent creation.
                Can also be set via environment variable AZURE_AI_MODEL_DEPLOYMENT_NAME.
            credential: Azure async credential to use for authentication.
                Required when project_client is not provided.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.

        Raises:
            ServiceInitializationError: If required parameters are missing or invalid.
        """
        try:
            self._settings = AzureAISettings(
                project_endpoint=project_endpoint,
                model_deployment_name=model,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Azure AI settings.", ex) from ex

        # Track whether we should close client connection
        self._should_close_client = False

        if project_client is None:
            if not self._settings.project_endpoint:
                raise ServiceInitializationError(
                    "Azure AI project endpoint is required. Set via 'project_endpoint' parameter "
                    "or 'AZURE_AI_PROJECT_ENDPOINT' environment variable."
                )

            if not credential:
                raise ServiceInitializationError("Azure credential is required when project_client is not provided.")

            project_client = AIProjectClient(
                endpoint=self._settings.project_endpoint,
                credential=credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )
            self._should_close_client = True

        self._project_client = project_client

    async def create_agent(
        self,
        name: str,
        model: str | None = None,
        instructions: str | None = None,
        description: str | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        default_options: TOptions_co | None = None,
        middleware: Sequence[Middleware] | None = None,
        context_provider: ContextProvider | None = None,
    ) -> "ChatAgent[TOptions_co]":
        """Create a new agent on the Azure AI service and return a local ChatAgent wrapper.

        Args:
            name: The name of the agent to create.
            model: The model deployment name to use. Falls back to AZURE_AI_MODEL_DEPLOYMENT_NAME
                environment variable if not provided.
            instructions: Instructions for the agent.
            description: A description of the agent.
            tools: Tools to make available to the agent.
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_provider: Context provider to include during agent invocation.

        Returns:
            ChatAgent: A ChatAgent instance configured with the created agent.

        Raises:
            ServiceInitializationError: If required parameters are missing.
        """
        # Resolve model from parameter or environment variable
        resolved_model = model or self._settings.model_deployment_name
        if not resolved_model:
            raise ServiceInitializationError(
                "Model deployment name is required. Provide 'model' parameter "
                "or set 'AZURE_AI_MODEL_DEPLOYMENT_NAME' environment variable."
            )

        # Extract options from default_options if present
        opts = dict(default_options) if default_options else {}
        response_format = opts.get("response_format")
        rai_config = opts.get("rai_config")
        reasoning = opts.get("reasoning")

        args: dict[str, Any] = {"model": resolved_model}

        if instructions:
            args["instructions"] = instructions
        if response_format and isinstance(response_format, (type, dict)):
            args["text"] = PromptAgentDefinitionText(
                format=create_text_format_config(response_format)  # type: ignore[arg-type]
            )
        if rai_config:
            args["rai_config"] = rai_config
        if reasoning:
            args["reasoning"] = reasoning

        # Normalize tools and separate MCP tools from other tools
        normalized_tools = normalize_tools(tools)
        mcp_tools: list[MCPTool] = []
        non_mcp_tools: list[ToolProtocol | MutableMapping[str, Any]] = []

        if normalized_tools:
            for tool in normalized_tools:
                if isinstance(tool, MCPTool):
                    mcp_tools.append(tool)
                else:
                    non_mcp_tools.append(tool)

        # Connect MCP tools and discover their functions BEFORE creating the agent
        # This is required because Azure AI Responses API doesn't accept tools at request time
        mcp_discovered_functions: list[FunctionTool] = []
        for mcp_tool in mcp_tools:
            if not mcp_tool.is_connected:
                await mcp_tool.connect()
            mcp_discovered_functions.extend(mcp_tool.functions)

        # Combine non-MCP tools with discovered MCP functions for Azure AI
        all_tools_for_azure: list[ToolProtocol | MutableMapping[str, Any]] = list(non_mcp_tools)
        all_tools_for_azure.extend(mcp_discovered_functions)

        if all_tools_for_azure:
            args["tools"] = to_azure_ai_tools(all_tools_for_azure)

        created_agent = await self._project_client.agents.create_version(
            agent_name=name,
            definition=PromptAgentDefinition(**args),
            description=description,
        )

        return self._to_chat_agent_from_details(
            created_agent,
            normalized_tools,
            default_options=default_options,
            middleware=middleware,
            context_provider=context_provider,
        )

    async def get_agent(
        self,
        *,
        name: str | None = None,
        reference: AgentReference | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        default_options: TOptions_co | None = None,
        middleware: Sequence[Middleware] | None = None,
        context_provider: ContextProvider | None = None,
    ) -> "ChatAgent[TOptions_co]":
        """Retrieve an existing agent from the Azure AI service and return a local ChatAgent wrapper.

        You must provide either name or reference. Use `as_agent()` if you already have
        AgentVersionDetails and want to avoid an async call.

        Args:
            name: The name of the agent to retrieve (fetches latest version).
            reference: Reference containing the agent's name and optionally a specific version.
            tools: Tools to make available to the agent. Required if the agent has function tools.
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_provider: Context provider to include during agent invocation.

        Returns:
            ChatAgent: A ChatAgent instance configured with the retrieved agent.

        Raises:
            ValueError: If no identifier is provided or required tools are missing.
        """
        existing_agent: AgentVersionDetails

        if reference and reference.version:
            # Fetch specific version
            existing_agent = await self._project_client.agents.get_version(
                agent_name=reference.name, agent_version=reference.version
            )
        elif agent_name := (reference.name if reference else name):
            # Fetch latest version
            details = await self._project_client.agents.get(agent_name=agent_name)
            existing_agent = details.versions.latest
        else:
            raise ValueError("Either name or reference must be provided to get an agent.")

        if not isinstance(existing_agent.definition, PromptAgentDefinition):
            raise ValueError("Agent definition must be PromptAgentDefinition to get a ChatAgent.")

        # Validate that required function tools are provided
        self._validate_function_tools(existing_agent.definition.tools, tools)

        return self._to_chat_agent_from_details(
            existing_agent,
            normalize_tools(tools),
            default_options=default_options,
            middleware=middleware,
            context_provider=context_provider,
        )

    def as_agent(
        self,
        details: AgentVersionDetails,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
        default_options: TOptions_co | None = None,
        middleware: Sequence[Middleware] | None = None,
        context_provider: ContextProvider | None = None,
    ) -> "ChatAgent[TOptions_co]":
        """Wrap an SDK agent version object into a ChatAgent without making HTTP calls.

        Use this when you already have an AgentVersionDetails from a previous API call.

        Args:
            details: The AgentVersionDetails to wrap.
            tools: Tools to make available to the agent. Required if the agent has function tools.
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_provider: Context provider to include during agent invocation.

        Returns:
            ChatAgent: A ChatAgent instance configured with the agent version.

        Raises:
            ValueError: If the agent definition is not a PromptAgentDefinition or required tools are missing.
        """
        if not isinstance(details.definition, PromptAgentDefinition):
            raise ValueError("Agent definition must be PromptAgentDefinition to create a ChatAgent.")

        # Validate that required function tools are provided
        self._validate_function_tools(details.definition.tools, tools)

        return self._to_chat_agent_from_details(
            details,
            normalize_tools(tools),
            default_options=default_options,
            middleware=middleware,
            context_provider=context_provider,
        )

    def _to_chat_agent_from_details(
        self,
        details: AgentVersionDetails,
        provided_tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None = None,
        default_options: TOptions_co | None = None,
        middleware: Sequence[Middleware] | None = None,
        context_provider: ContextProvider | None = None,
    ) -> "ChatAgent[TOptions_co]":
        """Create a ChatAgent from an AgentVersionDetails.

        Args:
            details: The AgentVersionDetails containing the agent definition.
            provided_tools: User-provided tools (including function implementations).
                These are merged with hosted tools from the definition.
            default_options: A TypedDict containing default chat options for the agent.
                These options are applied to every run unless overridden.
            middleware: List of middleware to intercept agent and function invocations.
            context_provider: Context provider to include during agent invocation.
        """
        if not isinstance(details.definition, PromptAgentDefinition):
            raise ValueError("Agent definition must be PromptAgentDefinition to get a ChatAgent.")

        client = AzureAIClient(
            project_client=self._project_client,
            agent_name=details.name,
            agent_version=details.version,
            agent_description=details.description,
            model_deployment_name=details.definition.model,
        )

        # Merge tools: hosted tools from definition + user-provided function tools
        # from_azure_ai_tools converts hosted tools (MCP, code interpreter, file search, web search)
        # but function tools need the actual implementations from provided_tools
        merged_tools = self._merge_tools(details.definition.tools, provided_tools)

        return ChatAgent(  # type: ignore[return-value]
            chat_client=client,
            id=details.id,
            name=details.name,
            description=details.description,
            instructions=details.definition.instructions,
            model_id=details.definition.model,
            tools=merged_tools,
            default_options=default_options,  # type: ignore[arg-type]
            middleware=middleware,
            context_provider=context_provider,
        )

    def _merge_tools(
        self,
        definition_tools: Sequence[Any] | None,
        provided_tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None,
    ) -> list[ToolProtocol | dict[str, Any]]:
        """Merge hosted tools from definition with user-provided function tools.

        Args:
            definition_tools: Tools from the agent definition (Azure AI format).
            provided_tools: User-provided tools (Agent Framework format), including function implementations.

        Returns:
            Combined list of tools for the ChatAgent.
        """
        merged: list[ToolProtocol | dict[str, Any]] = []

        # Convert hosted tools from definition (MCP, code interpreter, file search, web search)
        # Function tools from the definition are skipped - we use user-provided implementations instead
        hosted_tools = from_azure_ai_tools(definition_tools)
        for hosted_tool in hosted_tools:
            # Skip function tool dicts - they don't have implementations
            if isinstance(hosted_tool, dict) and hosted_tool.get("type") == "function":
                continue
            merged.append(hosted_tool)

        # Add user-provided function tools and MCP tools
        if provided_tools:
            for provided_tool in provided_tools:
                # FunctionTool - has implementation for function calling
                # MCPTool - ChatAgent handles MCP connection and tool discovery at runtime
                if isinstance(provided_tool, (FunctionTool, MCPTool)):
                    merged.append(provided_tool)  # type: ignore[reportUnknownArgumentType]

        return merged

    def _validate_function_tools(
        self,
        agent_tools: Sequence[Any] | None,
        provided_tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None,
    ) -> None:
        """Validate that required function tools are provided."""
        # Normalize and validate function tools
        normalized_tools = normalize_tools(provided_tools)
        tool_names = {tool.name for tool in normalized_tools if isinstance(tool, FunctionTool)}

        # If function tools exist in agent definition but were not provided,
        # we need to raise an error, as it won't be possible to invoke the function.
        missing_tools = [
            tool.name
            for tool in (agent_tools or [])
            if isinstance(tool, AzureFunctionTool) and tool.name not in tool_names
        ]

        if missing_tools:
            raise ValueError(
                f"The following prompt agent definition required tools were not provided: {', '.join(missing_tools)}"
            )

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the provider and release resources.

        Only closes the underlying AIProjectClient if it was created by this provider.
        """
        if self._should_close_client:
            await self._project_client.close()
