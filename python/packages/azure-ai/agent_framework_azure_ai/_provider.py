# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import Callable, MutableMapping, Sequence
from typing import Any

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AIFunction,
    ChatAgent,
    ChatOptions,
    ToolProtocol,
    get_logger,
)
from agent_framework.exceptions import ServiceInitializationError
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    AgentDetails,
    AgentReference,
    AgentVersionDetails,
    FunctionTool,
    PromptAgentDefinition,
    PromptAgentDefinitionText,
)
from azure.core.credentials_async import AsyncTokenCredential
from pydantic import BaseModel, ValidationError

from ._client import AzureAIClient
from ._shared import AzureAISettings, create_text_format_config, from_azure_ai_tools, to_azure_ai_tools

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = get_logger("agent_framework.azure")


class AzureAIProjectAgentProvider:
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
        self._credential = credential

    async def create_agent(
        self,
        name: str,
        model: str | None = None,
        instructions: str | None = None,
        description: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        response_format: type[BaseModel] | MutableMapping[str, Any] | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
    ) -> ChatAgent:
        """Create a new agent on the Azure AI service and return a local ChatAgent wrapper.

        Args:
            name: The name of the agent to create.
            model: The model deployment name to use. Falls back to AZURE_AI_MODEL_DEPLOYMENT_NAME
                environment variable if not provided.
            instructions: Instructions for the agent.
            description: A description of the agent.
            temperature: The sampling temperature to use.
            top_p: The nucleus sampling probability to use.
            response_format: The format of the response. Can be a Pydantic model for structured
                output, or a dict with JSON schema configuration.
            tools: Tools to make available to the agent.

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

        args: dict[str, Any] = {"model": resolved_model}

        if instructions:
            args["instructions"] = instructions
        if temperature is not None:
            args["temperature"] = temperature
        if top_p is not None:
            args["top_p"] = top_p
        if response_format:
            args["text"] = PromptAgentDefinitionText(format=create_text_format_config(response_format))
        if tools:
            normalized_tools = ChatOptions(tools=tools).tools or []
            args["tools"] = to_azure_ai_tools(normalized_tools)

        created_agent = await self._project_client.agents.create_version(
            agent_name=name,
            definition=PromptAgentDefinition(**args),
            description=description,
        )

        # Pass the user-provided tools for function invocation
        chat_agent_tools = ChatOptions(tools=tools).tools if tools else None

        # Only pass Pydantic models to ChatAgent for response parsing
        # Dict schemas are used by Azure AI for formatting, but can't be used for local parsing
        pydantic_response_format = (
            response_format if isinstance(response_format, type) and issubclass(response_format, BaseModel) else None
        )

        return self._create_chat_agent_from_details(
            created_agent, chat_agent_tools, response_format=pydantic_response_format
        )

    async def get_agent(
        self,
        *,
        name: str | None = None,
        reference: AgentReference | None = None,
        details: AgentDetails | None = None,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
    ) -> ChatAgent:
        """Retrieve an existing agent from the Azure AI service and return a local ChatAgent wrapper.

        You must provide one of: name, reference, or details.

        Args:
            name: The name of the agent to retrieve (fetches latest version).
            reference: Reference containing the agent's name and optionally a specific version.
            details: A pre-fetched AgentDetails object (uses latest version from it).
            tools: Tools to make available to the agent. Required if the agent has function tools.

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
        else:
            # Get agent details if not provided
            if agent_name := (reference.name if reference else name):
                details = await self._project_client.agents.get(agent_name=agent_name)

            if not details:
                raise ValueError("Either name, reference, or details must be provided to get an agent.")

            existing_agent = details.versions.latest

        if not isinstance(existing_agent.definition, PromptAgentDefinition):
            raise ValueError("Agent definition must be PromptAgentDefinition to get a ChatAgent.")

        # Validate that required function tools are provided
        self._validate_function_tools(existing_agent.definition.tools, tools)

        # Pass user-provided tools for function invocation
        normalized_tools = ChatOptions(tools=tools).tools if tools else None
        return self._create_chat_agent_from_details(existing_agent, normalized_tools)

    def as_agent(
        self,
        details: AgentVersionDetails,
        tools: ToolProtocol
        | Callable[..., Any]
        | MutableMapping[str, Any]
        | Sequence[ToolProtocol | Callable[..., Any] | MutableMapping[str, Any]]
        | None = None,
    ) -> ChatAgent:
        """Wrap an SDK agent version object into a ChatAgent without making HTTP calls.

        Use this when you already have an AgentVersionDetails from a previous API call.

        Args:
            details: The AgentVersionDetails to wrap.
            tools: Tools to make available to the agent. Required if the agent has function tools.

        Returns:
            ChatAgent: A ChatAgent instance configured with the agent version.

        Raises:
            ValueError: If the agent definition is not a PromptAgentDefinition or required tools are missing.
        """
        if not isinstance(details.definition, PromptAgentDefinition):
            raise ValueError("Agent definition must be PromptAgentDefinition to create a ChatAgent.")

        # Validate that required function tools are provided
        self._validate_function_tools(details.definition.tools, tools)

        # Pass user-provided tools for function invocation
        normalized_tools = ChatOptions(tools=tools).tools if tools else None
        return self._create_chat_agent_from_details(details, normalized_tools)

    def _create_chat_agent_from_details(
        self,
        details: AgentVersionDetails,
        provided_tools: Sequence[ToolProtocol | MutableMapping[str, Any]] | None = None,
        response_format: type[BaseModel] | None = None,
    ) -> ChatAgent:
        """Create a ChatAgent from an AgentVersionDetails.

        Args:
            details: The AgentVersionDetails containing the agent definition.
            provided_tools: User-provided tools (including function implementations).
                These are merged with hosted tools from the definition.
            response_format: The Pydantic model type for structured output parsing.
        """
        if not isinstance(details.definition, PromptAgentDefinition):
            raise ValueError("Agent definition must be PromptAgentDefinition to get a ChatAgent.")

        client = AzureAIClient(
            project_client=self._project_client,
            agent_name=details.name,
            agent_version=details.version,
            agent_description=details.description,
        )

        # Merge tools: hosted tools from definition + user-provided function tools
        # from_azure_ai_tools converts hosted tools (MCP, code interpreter, file search, web search)
        # but function tools need the actual implementations from provided_tools
        merged_tools = self._merge_tools(details.definition.tools, provided_tools)

        return ChatAgent(
            chat_client=client,
            id=details.id,
            name=details.name,
            description=details.description,
            instructions=details.definition.instructions,
            model_id=details.definition.model,
            temperature=details.definition.temperature,
            top_p=details.definition.top_p,
            tools=merged_tools,
            response_format=response_format,
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

        # Add user-provided function tools (these have the actual implementations)
        if provided_tools:
            for provided_tool in provided_tools:
                if isinstance(provided_tool, AIFunction):
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
        normalized_tools = ChatOptions(tools=provided_tools).tools or []
        tool_names = {tool.name for tool in normalized_tools if isinstance(tool, AIFunction)}

        # If function tools exist in agent definition but were not provided,
        # we need to raise an error, as it won't be possible to invoke the function.
        missing_tools = [
            tool.name for tool in (agent_tools or []) if isinstance(tool, FunctionTool) and tool.name not in tool_names
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
