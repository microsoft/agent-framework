# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, TypedDict

import yaml
from agent_framework import (
    AIFunction,
    ChatAgent,
    ChatClientProtocol,
    HostedCodeInterpreterTool,
    HostedFileContent,
    HostedFileSearchTool,
    HostedMCPSpecificApproval,
    HostedMCPTool,
    HostedVectorStoreContent,
    HostedWebSearchTool,
    ToolProtocol,
)
from agent_framework._tools import _create_model_from_json_schema  # type: ignore
from agent_framework.exceptions import AgentFrameworkException
from dotenv import load_dotenv

from ._models import (
    AnonymousConnection,
    ApiKeyConnection,
    CodeInterpreterTool,
    FileSearchTool,
    FunctionTool,
    McpServerToolSpecifyApprovalMode,
    McpTool,
    ModelOptions,
    PromptAgent,
    ReferenceConnection,
    RemoteConnection,
    WebSearchTool,
    agent_schema_dispatch,
)


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
    "Anthropic.Chat": {
        "package": "agent_framework.anthropic",
        "name": "AnthropicChatClient",
        "model_id_field": "model_id",
    },
}


class DeclarativeLoaderError(AgentFrameworkException):
    """Exception raised for errors in the declarative loader."""

    pass


class ProviderLookupError(DeclarativeLoaderError):
    """Exception raised for errors in provider type lookup."""

    pass


class AgentFactory:
    def __init__(
        self,
        chat_client: ChatClientProtocol | None = None,
        bindings: Mapping[str, Any] | None = None,
        connections: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        additional_mappings: Mapping[str, ProviderTypeMapping] | None = None,
        env_file: str | None = None,
    ) -> None:
        """Create the agent factory, with bindings.

        Args:
            chat_client: An optional ChatClientProtocol instance to use as a dependency,
                this will be passed to the ChatAgent that get's created.
                If you need to create multiple agents with different chat clients,
                do not pass this and instead provide the chat client in the YAML definition.
            bindings: An optional dictionary of bindings to use when creating agents.
            connections: An optional dictionary of connections to resolve ReferenceConnections.
            client_kwargs: An optional dictionary of keyword arguments to pass to chat client constructors.
            env_file: An optional path to a .env file to load environment variables from.
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
        """
        self.chat_client = chat_client
        self.bindings = bindings
        self.connections = connections
        self.client_kwargs = client_kwargs or {}
        self.additional_mappings = additional_mappings or {}
        load_dotenv(dotenv_path=env_file)

    def create_agent_from_yaml_path(self, yaml_path: str | Path) -> ChatAgent:
        """Create a MAML object from a YAML file path asynchronously.

        This method wraps the synchronous load_yaml_spec function to provide
        asynchronous behavior.

        Args:
            yaml_path: Path to the YAML file representation of a MAML object
        Returns:
            The object instance created from the YAML file.

        Raises:
            DeclarativeLoaderError: If the YAML does not represent a PromptAgent.
            ProviderLookupError: If the provider type is unknown or unsupported.
            ModuleNotFoundError: If the required module for the provider type cannot be imported.
            AttributeError: If the required class for the provider type cannot be found in the module.
        """
        if not isinstance(yaml_path, Path):
            yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise DeclarativeLoaderError(f"YAML file not found at path: {yaml_path}")
        with open(yaml_path) as f:
            yaml_str = f.read()
        return self.create_agent_from_yaml(yaml_str)

    def create_agent_from_yaml(self, yaml_str: str) -> ChatAgent:
        """Create a MAML object from a YAML string asynchronously.

        This method wraps the synchronous load_yaml_spec function to provide
        asynchronous behavior.

        This method does the following things:
        1. Loads the YAML string into a MAML object using load_yaml_spec.
        2. Validates that the loaded object is a PromptAgent.
        3. Creates the appropriate ChatClient based on the model provider and apiType.
        4. Parses the tools, options, and response format from the PromptAgent.
        5. Creates and returns a ChatAgent instance with the configured properties.

        Args:
            yaml_str: YAML string representation of a MAML object

        Returns:
            The object instance created from the YAML string.

        Raises:
            DeclarativeLoaderError: If the YAML does not represent a PromptAgent.
            ProviderLookupError: If the provider type is unknown or unsupported.
            ModuleNotFoundError: If the required module for the provider type cannot be imported.
            AttributeError: If the required class for the provider type cannot be found in the module.
        """
        prompt_agent = agent_schema_dispatch(yaml.safe_load(yaml_str))
        if not isinstance(prompt_agent, PromptAgent):
            raise DeclarativeLoaderError("Only PromptAgent kind is supported for agent creation")

        # Step 1: Create the ChatClient
        setup_dict: dict[str, Any] = {}
        setup_dict.update(self.client_kwargs)
        # resolve connections:
        client: ChatClientProtocol | None = None
        if prompt_agent.model and prompt_agent.model.connection:
            match prompt_agent.model.connection:
                case ApiKeyConnection():
                    setup_dict["api_key"] = prompt_agent.model.connection.apiKey
                    if prompt_agent.model.connection.endpoint:
                        setup_dict["endpoint"] = prompt_agent.model.connection.endpoint
                case RemoteConnection():
                    setup_dict["endpoint"] = prompt_agent.model.connection.endpoint
                case ReferenceConnection():
                    # find the referenced connection
                    if not self.connections:
                        raise ValueError("Connections must be provided to resolve ReferenceConnection")
                    for name, value in self.connections.items():
                        if name == prompt_agent.model.connection.name:
                            setup_dict[name] = value
                            break
                case AnonymousConnection():
                    setup_dict["endpoint"] = prompt_agent.model.connection.endpoint
                case _:
                    raise ValueError(f"Referenced connection '{prompt_agent.model.connection.referenceName}' not found")
        # check if there is a model.provider and model.apiType defined
        if prompt_agent.model and prompt_agent.model.provider and prompt_agent.model.apiType:
            # lookup the provider type in the mapping
            class_lookup = f"{prompt_agent.model.provider}.{prompt_agent.model.apiType}"
            if class_lookup in PROVIDER_TYPE_OBJECT_MAPPING:
                mapping = self._retrieve_provider_configuration(class_lookup)
                module_name = mapping["package"]
                class_name = mapping["name"]
                module = __import__(module_name, fromlist=[class_name])
                agent_class = getattr(module, class_name)
                setup_dict[mapping["model_id_field"]] = prompt_agent.model.id
                client = agent_class(**setup_dict)
            else:
                raise ValueError("Unsupported model provider or apiType in PromptAgent")
        if not client and prompt_agent.model and prompt_agent.model.id:
            # assume AzureAIAgentClient
            mapping = self._retrieve_provider_configuration("AzureAIAgentClient")
            module_name = mapping["package"]
            class_name = mapping["name"]
            module = __import__(module_name, fromlist=[class_name])
            agent_class = getattr(module, class_name)
            setup_dict[mapping["model_id_field"]] = prompt_agent.model.id
            client = agent_class(**setup_dict)
        elif not client:
            # get a ChatClientProtocol supplied
            if not self.chat_client:
                raise ValueError("ChatClient must be provided to create agent from PromptAgent")
            client = self.chat_client
        # Step 2: Parse the other properties, including tools, options and response_format
        # Options
        chat_options: dict[str, Any] = {}
        if prompt_agent.model and (options := prompt_agent.model.options) and isinstance(options, ModelOptions):
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
        # Tools
        tools: list[ToolProtocol] = []
        if prompt_agent.tools:
            for tool_resource in prompt_agent.tools:
                match tool_resource:
                    case FunctionTool():
                        func: Callable[..., Any] | None = None
                        if self.bindings and tool_resource.bindings:
                            for binding in tool_resource.bindings:
                                if binding.name and binding.name in self.bindings:
                                    func = self.bindings[binding.name]
                                    break
                        tools.append(
                            AIFunction(  # type: ignore
                                name=tool_resource.name,  # type: ignore
                                description=tool_resource.description,  # type: ignore
                                input_model=tool_resource.parameters.to_json_schema()
                                if tool_resource.parameters
                                else None,
                                func=func,
                            )
                        )
                    case WebSearchTool():
                        tools.append(
                            HostedWebSearchTool(
                                description=tool_resource.description, additional_properties=tool_resource.options
                            )
                        )
                    case FileSearchTool():
                        add_props: dict[str, Any] = {}
                        if tool_resource.ranker is not None:
                            add_props["ranker"] = tool_resource.ranker
                        if tool_resource.scoreThreshold is not None:
                            add_props["score_threshold"] = tool_resource.scoreThreshold
                        if tool_resource.filters:
                            add_props["filters"] = tool_resource.filters
                        tools.append(
                            HostedFileSearchTool(
                                inputs=[HostedVectorStoreContent(id) for id in tool_resource.vectorStoreIds or []],
                                description=tool_resource.description,
                                max_results=tool_resource.maximumResultCount,
                                additional_properties=add_props,
                            )
                        )
                    case CodeInterpreterTool():
                        tools.append(
                            HostedCodeInterpreterTool(
                                inputs=[HostedFileContent(file_id=file) for file in tool_resource.fileIds or []],
                                description=tool_resource.description,
                            )
                        )
                    case McpTool():
                        approval_mode: HostedMCPSpecificApproval | Literal["always_require", "never_require"] | None = (
                            None
                        )
                        if tool_resource.approvalMode is not None:
                            if tool_resource.approvalMode.kind == "always":
                                approval_mode = "always_require"
                            elif tool_resource.approvalMode.kind == "never":
                                approval_mode = "never_require"
                            elif isinstance(tool_resource.approvalMode, McpServerToolSpecifyApprovalMode):
                                if tool_resource.approvalMode.alwaysRequireApprovalTools:
                                    approval_mode = {
                                        "always_require_approval": tool_resource.approvalMode.alwaysRequireApprovalTools
                                    }
                                else:
                                    approval_mode = {
                                        "never_require_approval": tool_resource.approvalMode.neverRequireApprovalTools
                                    }
                        tools.append(
                            HostedMCPTool(
                                name=tool_resource.name,  # type: ignore
                                description=tool_resource.description,
                                url=tool_resource.url,  # type: ignore
                                allowed_tools=tool_resource.allowedTools,
                                approval_mode=approval_mode,
                            )
                        )
                    case _:
                        raise ValueError(f"Unsupported tool kind: {tool_resource.kind}")

        # response format
        if prompt_agent.outputSchema:
            pydantic_model = _create_model_from_json_schema("agent", prompt_agent.outputSchema.to_json_schema())
            chat_options["response_format"] = pydantic_model

        # Step 3: Create the agent instance
        return ChatAgent(
            chat_client=client,
            name=prompt_agent.name,
            description=prompt_agent.description,
            instructions=prompt_agent.instructions,
            tools=tools,
            **chat_options,
        )

    def _retrieve_provider_configuration(self, class_lookup: str) -> ProviderTypeMapping:
        """Retrieve the provider configuration for a given class lookup.

        This method will first attempt to find the class lookup in the additional mappings
        provided to the AgentFactory. If not found there, it will look in the default
        PROVIDER_TYPE_OBJECT_MAPPING.

        Args:
            class_lookup: The class lookup string in the format 'Provider.ApiType'

        Returns:
            A dictionary containing the package, name, and model_id_field for the provider.

        Raises:
            ProviderLookupError: If the provider type is not supported.
        """
        if class_lookup in self.additional_mappings:
            return self.additional_mappings[class_lookup]
        if class_lookup not in PROVIDER_TYPE_OBJECT_MAPPING:
            raise ProviderLookupError(f"Unsupported provider type: {class_lookup}")
        return PROVIDER_TYPE_OBJECT_MAPPING[class_lookup]
