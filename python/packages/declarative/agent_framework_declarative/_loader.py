# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from agent_framework import (
    Agent,
    SupportsChatGetResponse,
)
from agent_framework import (
    FunctionTool as AFFunctionTool,
)
from agent_framework._tools import _create_model_from_json_schema  # type: ignore
from agent_framework.exceptions import AgentException
from dotenv import load_dotenv

from ._models import (
    AnonymousConnection,
    ApiKeyConnection,
    CodeInterpreterTool,
    FileSearchTool,
    FunctionTool,
    McpServerToolSpecifyApprovalMode,
    McpTool,
    Model,
    ModelOptions,
    PromptAgent,
    ReferenceConnection,
    RemoteConnection,
    Tool,
    WebSearchTool,
    _safe_mode_context,
    agent_schema_dispatch,
)

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


class ProviderTypeMapping(TypedDict, total=True):
    package: str
    name: str
    model_id_field: str


PROVIDER_TYPE_OBJECT_MAPPING: dict[str, ProviderTypeMapping] = {
    "AzureOpenAI.Chat": {
        "package": "agent_framework.azure",
        "name": "AzureOpenAIChatClient",
        "model_id_field": "deployment_name",
    },
    "AzureOpenAI.Assistants": {
        "package": "agent_framework.azure",
        "name": "AzureOpenAIAssistantsClient",
        "model_id_field": "deployment_name",
    },
    "AzureOpenAI.Responses": {
        "package": "agent_framework.azure",
        "name": "AzureOpenAIResponsesClient",
        "model_id_field": "deployment_name",
    },
    "OpenAI.Chat": {
        "package": "agent_framework.openai",
        "name": "OpenAIChatClient",
        "model_id_field": "model_id",
    },
    "OpenAI.Assistants": {
        "package": "agent_framework.openai",
        "name": "OpenAIAssistantsClient",
        "model_id_field": "model_id",
    },
    "OpenAI.Responses": {
        "package": "agent_framework.openai",
        "name": "OpenAIResponsesClient",
        "model_id_field": "model_id",
    },
    "AzureAIAgentClient": {
        "package": "agent_framework.azure",
        "name": "AzureAIAgentClient",
        "model_id_field": "model_deployment_name",
    },
    "AzureAIClient": {
        "package": "agent_framework.azure",
        "name": "AzureAIClient",
        "model_id_field": "model_deployment_name",
    },
    "AzureAI.ProjectProvider": {
        "package": "agent_framework.azure",
        "name": "AzureAIProjectAgentProvider",
        "model_id_field": "model",
    },
    "Anthropic.Chat": {
        "package": "agent_framework.anthropic",
        "name": "AnthropicChatClient",
        "model_id_field": "model_id",
    },
}


class DeclarativeLoaderError(AgentException):
    """Exception raised for errors in the declarative loader."""

    pass


class ProviderLookupError(DeclarativeLoaderError):
    """Exception raised for errors in provider type lookup."""

    pass


class AgentFactory:
    """Factory for creating Agent instances from declarative YAML definitions.

    AgentFactory parses YAML agent definitions (PromptAgent kind) and creates
    configured Agent instances with the appropriate chat client, tools,
    and response format.

    Examples:
        .. code-block:: python

            from agent_framework_declarative import AgentFactory

            # Create agent from YAML file
            factory = AgentFactory()
            agent = factory.create_agent_from_yaml_path("agent.yaml")

            # Run the agent
            async for event in agent.run("Hello!", stream=True):
                print(event)

        .. code-block:: python

            from agent_framework.azure import AzureOpenAIChatClient
            from agent_framework_declarative import AgentFactory

            # With pre-configured chat client
            client = AzureOpenAIChatClient()
            factory = AgentFactory(client=client)
            agent = factory.create_agent_from_yaml_path("agent.yaml")

        .. code-block:: python

            from agent_framework_declarative import AgentFactory

            # From inline YAML string
            yaml_content = '''
            kind: Prompt
            name: GreetingAgent
            instructions: You are a friendly assistant.
            model:
              id: gpt-4o
              provider: AzureOpenAI
            '''

            factory = AgentFactory()
            agent = factory.create_agent_from_yaml(yaml_content)
    """

    def __init__(
        self,
        *,
        client: SupportsChatGetResponse | None = None,
        bindings: Mapping[str, Any] | None = None,
        connections: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        additional_mappings: Mapping[str, ProviderTypeMapping] | None = None,
        default_provider: str = "AzureAIClient",
        safe_mode: bool = True,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Create the agent factory.

        Args:
            client: An optional SupportsChatGetResponse instance to use as a dependency.
                This will be passed to the Agent that gets created.
                If you need to create multiple agents with different chat clients,
                do not pass this and instead provide the chat client in the YAML definition.
            bindings: An optional dictionary of bindings to use when creating agents.
            connections: An optional dictionary of connections to resolve ReferenceConnections.
            client_kwargs: An optional dictionary of keyword arguments to pass to chat client constructor.
            additional_mappings: An optional dictionary to extend the provider type to object mapping.
                Should have the structure:

                    ..code-block:: python

                        additional_mappings = {
                            "Provider.ApiType": {
                                "package": "package.name",
                                "name": "ClassName",
                                "model_id_field": "field_name_in_constructor",
                            },
                            ...
                        }

                    Here, "Provider.ApiType" is the lookup key used when both provider and apiType are specified in the
                    model, "Provider" is also allowed.
                    Package refers to which model needs to be imported, Name is the class name of the
                    SupportsChatGetResponse implementation, and model_id_field is the name of the field in the
                    constructor that accepts the model.id value.
            default_provider: The default provider used when model.provider is not specified,
                default is "AzureAIClient".
            safe_mode: Whether to run in safe mode, default is True.
                When safe_mode is True, environment variables are not accessible in the powerfx expressions.
                You can still use environment variables, but through the constructors of the classes.
                Which means you must make sure you are using the standard env variable names of the classes
                you are using and not custom ones and remove the powerfx statements that start with `=Env.`.
                Only when you trust the source of your yaml files, you can set safe_mode to False
                via the AgentFactory constructor.
            env_file_path: The path to the .env file to load environment variables from.
            env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

        Examples:
            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                # Minimal initialization
                factory = AgentFactory()

            .. code-block:: python

                from agent_framework.azure import AzureOpenAIChatClient
                from agent_framework_declarative import AgentFactory

                # With shared chat client
                client = AzureOpenAIChatClient()
                factory = AgentFactory(
                    client=client,
                    env_file_path=".env",
                )

            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                # With custom provider mappings
                factory = AgentFactory(
                    additional_mappings={
                        "CustomProvider.Chat": {
                            "package": "my_package.clients",
                            "name": "CustomChatClient",
                            "model_id_field": "model_name",
                        },
                    },
                )
        """
        self.client = client
        self.bindings = bindings
        self.connections = connections
        self.client_kwargs = client_kwargs or {}
        self.additional_mappings = additional_mappings or {}
        self.default_provider: str = default_provider
        self.safe_mode = safe_mode
        load_dotenv(dotenv_path=env_file_path, encoding=env_file_encoding)

    def create_agent_from_yaml_path(self, yaml_path: str | Path) -> Agent:
        """Create a Agent from a YAML file path.

        This method does the following things:

        1. Loads the YAML file into an AgentSchema object.
        2. Validates that the loaded object is a PromptAgent.
        3. Creates the appropriate ChatClient based on the model provider and apiType.
        4. Parses the tools, options, and response format from the PromptAgent.
        5. Creates and returns a Agent instance with the configured properties.

        Args:
            yaml_path: Path to the YAML file representation of a PromptAgent.

        Returns:
            The ``Agent`` instance created from the YAML file.

        Raises:
            DeclarativeLoaderError: If the YAML does not represent a PromptAgent.
            ProviderLookupError: If the provider type is unknown or unsupported.
            ValueError: If a ReferenceConnection cannot be resolved.
            ModuleNotFoundError: If the required module for the provider type cannot be imported.
            AttributeError: If the required class for the provider type cannot be found in the module.

        Examples:
            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                factory = AgentFactory()
                agent = factory.create_agent_from_yaml_path("agents/support_agent.yaml")

                # Execute the agent
                async for event in agent.run("Help me with my order", stream=True):
                    print(event)

            .. code-block:: python

                from pathlib import Path
                from agent_framework_declarative import AgentFactory

                # Using Path object for cross-platform compatibility
                agent_path = Path(__file__).parent / "agents" / "writer.yaml"
                factory = AgentFactory()
                agent = factory.create_agent_from_yaml_path(agent_path)
        """
        if not isinstance(yaml_path, Path):
            yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise DeclarativeLoaderError(f"YAML file not found at path: {yaml_path}")
        with open(yaml_path) as f:
            yaml_str = f.read()
        return self.create_agent_from_yaml(yaml_str)

    def create_agent_from_yaml(self, yaml_str: str) -> Agent:
        """Create a Agent from a YAML string.

        This method does the following things:

        1. Loads the YAML string into an AgentSchema object.
        2. Validates that the loaded object is a PromptAgent.
        3. Creates the appropriate ChatClient based on the model provider and apiType.
        4. Parses the tools, options, and response format from the PromptAgent.
        5. Creates and returns a Agent instance with the configured properties.

        Args:
            yaml_str: YAML string representation of a PromptAgent.

        Returns:
            The ``Agent`` instance created from the YAML string.

        Raises:
            DeclarativeLoaderError: If the YAML does not represent a PromptAgent.
            ProviderLookupError: If the provider type is unknown or unsupported.
            ValueError: If a ReferenceConnection cannot be resolved.
            ModuleNotFoundError: If the required module for the provider type cannot be imported.
            AttributeError: If the required class for the provider type cannot be found in the module.

        Examples:
            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                yaml_content = '''
                kind: Prompt
                name: TranslationAgent
                description: Translates text between languages
                instructions: |
                    You are a translation assistant.
                    Translate user input to the requested language.
                model:
                    id: gpt-4o
                    provider: AzureOpenAI
                    options:
                        temperature: 0.3
                '''

                factory = AgentFactory()
                agent = factory.create_agent_from_yaml(yaml_content)

            .. code-block:: python

                from agent_framework_declarative import AgentFactory
                from pydantic import BaseModel

                # Agent with structured output
                yaml_content = '''
                kind: Prompt
                name: SentimentAnalyzer
                instructions: Analyze the sentiment of the input text.
                model:
                    id: gpt-4o
                outputSchema:
                    type: object
                    properties:
                        sentiment:
                            type: string
                            enum: [positive, negative, neutral]
                        confidence:
                            type: number
                '''

                factory = AgentFactory()
                agent = factory.create_agent_from_yaml(yaml_content)
        """
        return self.create_agent_from_dict(yaml.safe_load(yaml_str))

    def create_agent_from_dict(self, agent_def: dict[str, Any]) -> Agent:
        """Create a Agent from a dictionary definition.

        This method does the following things:

        1. Converts the dictionary into an AgentSchema object.
        2. Validates that the loaded object is a PromptAgent.
        3. Creates the appropriate ChatClient based on the model provider and apiType.
        4. Parses the tools, options, and response format from the PromptAgent.
        5. Creates and returns a Agent instance with the configured properties.

        Args:
            agent_def: Dictionary representation of a PromptAgent.

        Returns:
            The `Agent` instance created from the dictionary.

        Raises:
            DeclarativeLoaderError: If the dictionary does not represent a PromptAgent.
            ProviderLookupError: If the provider type is unknown or unsupported.
            ValueError: If a ReferenceConnection cannot be resolved.
            ModuleNotFoundError: If the required module for the provider type cannot be imported.
            AttributeError: If the required class for the provider type cannot be found in the module.

        Examples:
            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                agent_def = {
                    "kind": "Prompt",
                    "name": "TranslationAgent",
                    "description": "Translates text between languages",
                    "instructions": "You are a translation assistant.",
                    "model": {
                        "id": "gpt-4o",
                        "provider": "AzureOpenAI",
                    },
                }

                factory = AgentFactory()
                agent = factory.create_agent_from_dict(agent_def)
        """
        # Set safe_mode context before parsing YAML to control PowerFx environment variable access
        _safe_mode_context.set(self.safe_mode)
        prompt_agent = agent_schema_dispatch(agent_def)
        if not isinstance(prompt_agent, PromptAgent):
            raise DeclarativeLoaderError("Only definitions for a PromptAgent are supported for agent creation.")

        # Step 1: Create the ChatClient
        client = self._get_client(prompt_agent)
        # Step 2: Get the chat options
        chat_options = self._parse_chat_options(prompt_agent.model)
        if tools := self._parse_tools(prompt_agent.tools):
            chat_options["tools"] = tools
        if output_schema := prompt_agent.outputSchema:
            chat_options["response_format"] = _create_model_from_json_schema("agent", output_schema.to_json_schema())
        # Step 3: Create the agent instance
        return Agent(
            client=client,
            name=prompt_agent.name,
            description=prompt_agent.description,
            instructions=prompt_agent.instructions,
            default_options=chat_options,  # type: ignore[arg-type]
        )

    async def create_agent_from_yaml_path_async(self, yaml_path: str | Path) -> Agent:
        """Async version: Create a Agent from a YAML file path.

        Use this method when the provider requires async initialization, such as
        AzureAI.ProjectProvider which creates agents on the Azure AI Agent Service.

        Args:
            yaml_path: Path to the YAML file representation of a PromptAgent.

        Returns:
            The ``Agent`` instance created from the YAML file.

        Examples:
            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                factory = AgentFactory(
                    client_kwargs={"credential": credential},
                    default_provider="AzureAI.ProjectProvider",
                )
                agent = await factory.create_agent_from_yaml_path_async("agent.yaml")
        """
        if not isinstance(yaml_path, Path):
            yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise DeclarativeLoaderError(f"YAML file not found at path: {yaml_path}")
        yaml_str = yaml_path.read_text()
        return await self.create_agent_from_yaml_async(yaml_str)

    async def create_agent_from_yaml_async(self, yaml_str: str) -> Agent:
        """Async version: Create a Agent from a YAML string.

        Use this method when the provider requires async initialization, such as
        AzureAI.ProjectProvider which creates agents on the Azure AI Agent Service.

        Args:
            yaml_str: YAML string representation of a PromptAgent.

        Returns:
            The ``Agent`` instance created from the YAML string.

        Examples:
            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                yaml_content = '''
                kind: Prompt
                name: MyAgent
                instructions: You are a helpful assistant.
                model:
                    id: gpt-4o
                    provider: AzureAI.ProjectProvider
                '''

                factory = AgentFactory(client_kwargs={"credential": credential})
                agent = await factory.create_agent_from_yaml_async(yaml_content)
        """
        return await self.create_agent_from_dict_async(yaml.safe_load(yaml_str))

    async def create_agent_from_dict_async(self, agent_def: dict[str, Any]) -> Agent:
        """Async version: Create a Agent from a dictionary definition.

        Use this method when the provider requires async initialization, such as
        AzureAI.ProjectProvider which creates agents on the Azure AI Agent Service.

        Args:
            agent_def: Dictionary representation of a PromptAgent.

        Returns:
            The ``Agent`` instance created from the dictionary.

        Examples:
            .. code-block:: python

                from agent_framework_declarative import AgentFactory

                agent_def = {
                    "kind": "Prompt",
                    "name": "MyAgent",
                    "instructions": "You are a helpful assistant.",
                    "model": {
                        "id": "gpt-4o",
                        "provider": "AzureAI.ProjectProvider",
                    },
                }

                factory = AgentFactory(client_kwargs={"credential": credential})
                agent = await factory.create_agent_from_dict_async(agent_def)
        """
        # Set safe_mode context before parsing YAML to control PowerFx environment variable access
        _safe_mode_context.set(self.safe_mode)
        prompt_agent = agent_schema_dispatch(agent_def)
        if not isinstance(prompt_agent, PromptAgent):
            raise DeclarativeLoaderError("Only definitions for a PromptAgent are supported for agent creation.")

        # Check if we're using a provider-based approach (like AzureAIProjectAgentProvider)
        mapping = self._retrieve_provider_configuration(prompt_agent.model) if prompt_agent.model else None
        if mapping and mapping["name"] == "AzureAIProjectAgentProvider":
            return await self._create_agent_with_provider(prompt_agent, mapping)

        # Fall back to standard ChatClient approach
        client = self._get_client(prompt_agent)
        chat_options = self._parse_chat_options(prompt_agent.model)
        if tools := self._parse_tools(prompt_agent.tools):
            chat_options["tools"] = tools
        if output_schema := prompt_agent.outputSchema:
            chat_options["response_format"] = _create_model_from_json_schema("agent", output_schema.to_json_schema())
        return Agent(
            client=client,
            name=prompt_agent.name,
            description=prompt_agent.description,
            instructions=prompt_agent.instructions,
            default_options=chat_options,  # type: ignore[arg-type]
        )

    async def _create_agent_with_provider(self, prompt_agent: PromptAgent, mapping: ProviderTypeMapping) -> Agent:
        """Create a Agent using AzureAIProjectAgentProvider.

        This method handles the special case where we use a provider that creates
        agents on a remote service (like Azure AI Agent Service) and returns
        Agent instances directly.
        """
        # Import the provider class
        module_name = mapping["package"]
        class_name = mapping["name"]
        module = __import__(module_name, fromlist=[class_name])
        provider_class = getattr(module, class_name)

        # Build provider kwargs from client_kwargs and connection info
        provider_kwargs: dict[str, Any] = {}
        provider_kwargs.update(self.client_kwargs)

        # Handle connection settings for the model
        if prompt_agent.model and prompt_agent.model.connection:
            match prompt_agent.model.connection:
                case RemoteConnection() | AnonymousConnection():
                    if prompt_agent.model.connection.endpoint:
                        provider_kwargs["project_endpoint"] = prompt_agent.model.connection.endpoint
                case ApiKeyConnection():
                    if prompt_agent.model.connection.endpoint:
                        provider_kwargs["project_endpoint"] = prompt_agent.model.connection.endpoint

        # Create the provider and use it to create the agent
        provider = provider_class(**provider_kwargs)

        # Parse tools
        tools = self._parse_tools(prompt_agent.tools) if prompt_agent.tools else None

        # Parse response format into default_options
        default_options: dict[str, Any] | None = None
        if prompt_agent.outputSchema:
            response_format = _create_model_from_json_schema("agent", prompt_agent.outputSchema.to_json_schema())
            default_options = {"response_format": response_format}

        # Create the agent using the provider
        # The provider's create_agent returns a Agent directly
        return cast(
            Agent,
            await provider.create_agent(
                name=prompt_agent.name,
                model=prompt_agent.model.id if prompt_agent.model else None,
                instructions=prompt_agent.instructions,
                description=prompt_agent.description,
                tools=tools,
                default_options=default_options,
            ),
        )

    def _get_client(self, prompt_agent: PromptAgent) -> SupportsChatGetResponse:
        """Create the SupportsChatGetResponse instance based on the PromptAgent model."""
        if not prompt_agent.model:
            # if no model is defined, use the supplied client
            if self.client:
                return self.client
            raise DeclarativeLoaderError(
                "ChatClient must be provided to create agent from PromptAgent, "
                "alternatively define a model in the PromptAgent."
            )

        setup_dict: dict[str, Any] = {}
        setup_dict.update(self.client_kwargs)

        # parse connections
        if prompt_agent.model.connection:
            match prompt_agent.model.connection:
                case ApiKeyConnection():
                    setup_dict["api_key"] = prompt_agent.model.connection.apiKey
                    if prompt_agent.model.connection.endpoint:
                        setup_dict["endpoint"] = prompt_agent.model.connection.endpoint
                case RemoteConnection() | AnonymousConnection():
                    setup_dict["endpoint"] = prompt_agent.model.connection.endpoint
                case ReferenceConnection():
                    if not self.connections:
                        raise ValueError("Connections must be provided to resolve ReferenceConnection")
                    # find the referenced connection
                    if prompt_agent.model.connection.name and (
                        value := self.connections.get(prompt_agent.model.connection.name)
                    ):
                        setup_dict[prompt_agent.model.connection.name] = value
                    else:
                        raise ValueError(
                            f"ReferenceConnection with name {prompt_agent.model.connection.name} not found in provided "
                            "connections."
                        )

        # Any client we create, needs a model.id
        if not prompt_agent.model.id:
            # if prompt_agent.model is defined, but no id, use the supplied client
            if self.client:
                return self.client
            # or raise, since we cannot create a client without model id
            raise DeclarativeLoaderError(
                "ChatClient must be provided to create agent from PromptAgent, or define model.id in the PromptAgent."
            )
        # if provider is defined, use that, if possible with apiType, fallback to default_provider
        mapping = self._retrieve_provider_configuration(prompt_agent.model)
        module_name = mapping["package"]
        class_name = mapping["name"]
        module = __import__(module_name, fromlist=[class_name])
        agent_class = getattr(module, class_name)
        setup_dict[mapping["model_id_field"]] = prompt_agent.model.id
        return agent_class(**setup_dict)  # type: ignore[no-any-return]

    def _parse_chat_options(self, model: Model | None) -> dict[str, Any]:
        """Parse ModelOptions into chat options dictionary."""
        chat_options: dict[str, Any] = {}
        if not model or not model.options or not isinstance(model.options, ModelOptions):
            return chat_options
        options = model.options
        if options.frequencyPenalty is not None:
            chat_options["frequency_penalty"] = options.frequencyPenalty
        if options.presencePenalty is not None:
            chat_options["presence_penalty"] = options.presencePenalty
        if options.maxOutputTokens is not None:
            chat_options["max_tokens"] = options.maxOutputTokens
        if options.temperature is not None:
            chat_options["temperature"] = options.temperature
        if options.topP is not None:
            chat_options["top_p"] = options.topP
        if options.seed is not None:
            chat_options["seed"] = options.seed
        if options.stopSequences:
            chat_options["stop"] = options.stopSequences
        if options.allowMultipleToolCalls is not None:
            chat_options["allow_multiple_tool_calls"] = options.allowMultipleToolCalls
        if (chat_tool_mode := options.additionalProperties.pop("chatToolMode", None)) is not None:
            chat_options["tool_choice"] = chat_tool_mode
        if options.additionalProperties:
            chat_options["additional_chat_options"] = options.additionalProperties
        return chat_options

    def _parse_tools(self, tools: list[Tool] | None) -> list[AFFunctionTool | dict[str, Any]] | None:
        """Parse tool resources into AFFunctionTool instances or dict-based tools."""
        if not tools:
            return None
        return [self._parse_tool(tool_resource) for tool_resource in tools]

    def _parse_tool(self, tool_resource: Tool) -> AFFunctionTool | dict[str, Any]:
        """Parse a single tool resource into an AFFunctionTool instance."""
        match tool_resource:
            case FunctionTool():
                func: Callable[..., Any] | None = None
                if self.bindings and tool_resource.bindings:
                    for binding in tool_resource.bindings:
                        if binding.name and (func := self.bindings.get(binding.name)):
                            break
                return AFFunctionTool(  # type: ignore
                    name=tool_resource.name,  # type: ignore
                    description=tool_resource.description,  # type: ignore
                    input_model=tool_resource.parameters.to_json_schema() if tool_resource.parameters else None,
                    func=func,
                )
            case WebSearchTool():
                result: dict[str, Any] = {"type": "web_search_preview"}
                if tool_resource.description:
                    result["description"] = tool_resource.description
                if tool_resource.options:
                    result.update(tool_resource.options)
                return result
            case FileSearchTool():
                result = {
                    "type": "file_search",
                    "vector_store_ids": tool_resource.vectorStoreIds or [],
                }
                if tool_resource.maximumResultCount is not None:
                    result["max_num_results"] = tool_resource.maximumResultCount
                if tool_resource.description:
                    result["description"] = tool_resource.description
                if tool_resource.ranker is not None:
                    result["ranker"] = tool_resource.ranker
                if tool_resource.scoreThreshold is not None:
                    result["score_threshold"] = tool_resource.scoreThreshold
                if tool_resource.filters:
                    result["filters"] = tool_resource.filters
                return result
            case CodeInterpreterTool():
                result = {"type": "code_interpreter"}
                if tool_resource.fileIds:
                    result["file_ids"] = tool_resource.fileIds
                if tool_resource.description:
                    result["description"] = tool_resource.description
                return result
            case McpTool():
                result = {
                    "type": "mcp",
                    "server_label": tool_resource.name.replace(" ", "_") if tool_resource.name else "",
                    "server_url": str(tool_resource.url) if tool_resource.url else "",
                }
                if tool_resource.description:
                    result["server_description"] = tool_resource.description
                if tool_resource.allowedTools:
                    result["allowed_tools"] = list(tool_resource.allowedTools)

                # Handle approval mode
                if tool_resource.approvalMode is not None:
                    if tool_resource.approvalMode.kind == "always":
                        result["require_approval"] = "always"
                    elif tool_resource.approvalMode.kind == "never":
                        result["require_approval"] = "never"
                    elif isinstance(tool_resource.approvalMode, McpServerToolSpecifyApprovalMode):
                        approval_config: dict[str, Any] = {}
                        if tool_resource.approvalMode.alwaysRequireApprovalTools:
                            approval_config["always"] = {
                                "tool_names": list(tool_resource.approvalMode.alwaysRequireApprovalTools)
                            }
                        if tool_resource.approvalMode.neverRequireApprovalTools:
                            approval_config["never"] = {
                                "tool_names": list(tool_resource.approvalMode.neverRequireApprovalTools)
                            }
                        if approval_config:
                            result["require_approval"] = approval_config

                # Handle connection settings
                if tool_resource.connection is not None:
                    match tool_resource.connection:
                        case ApiKeyConnection():
                            if tool_resource.connection.apiKey:
                                result["headers"] = {"Authorization": f"Bearer {tool_resource.connection.apiKey}"}
                        case RemoteConnection():
                            result["project_connection_id"] = tool_resource.connection.name
                        case ReferenceConnection():
                            result["project_connection_id"] = tool_resource.connection.name
                        case AnonymousConnection():
                            pass
                        case _:
                            raise ValueError(f"Unsupported connection kind: {tool_resource.connection.kind}")

                return result
            case _:
                raise ValueError(f"Unsupported tool kind: {tool_resource.kind}")

    def _retrieve_provider_configuration(self, model: Model) -> ProviderTypeMapping:
        """Retrieve the provider configuration based on the model's provider and apiType.

        If only provider is specified, it will be used.
        If both provider and apiType are specified, both will be used.
        If neither is specified, the default_provider will be used.

        Args:
            model: The Model instance containing provider and apiType information.

        Returns:
            A dictionary containing the package, name, and model_id_field for the provider.

        Raises:
            ProviderLookupError: If the provider type is not supported or can't be found.
        """
        class_lookup = (
            f"{model.provider}.{model.apiType}"
            if model.apiType
            else f"{model.provider}"
            if model.provider
            else self.default_provider
        )
        if class_lookup in self.additional_mappings:
            return self.additional_mappings[class_lookup]
        if class_lookup not in PROVIDER_TYPE_OBJECT_MAPPING:
            raise ProviderLookupError(f"Unsupported provider type: {class_lookup}")
        return PROVIDER_TYPE_OBJECT_MAPPING[class_lookup]
