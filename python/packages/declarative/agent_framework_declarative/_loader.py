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
    Model,
    ModelOptions,
    PromptAgent,
    ReferenceConnection,
    RemoteConnection,
    Tool,
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
    "AzureAIClient": {
        "package": "agent_framework.azure",
        "name": "AzureAIClient",
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
        *,
        chat_client: ChatClientProtocol | None = None,
        bindings: Mapping[str, Any] | None = None,
        connections: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        additional_mappings: Mapping[str, ProviderTypeMapping] | None = None,
        default_provider: str = "AzureAIClient",
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
                Package refers to which model needs to be imported, Name is the class name of the ChatClientProtocol
                implementation, and model_id_field is the name of the field in the constructor
                that accepts the model.id value.
            default_provider: The default provider used when model.provider is not specified,
                default is "AzureAIClient".
            env_file: An optional path to a .env file to load environment variables from.
        """
        self.chat_client = chat_client
        self.bindings = bindings
        self.connections = connections
        self.client_kwargs = client_kwargs or {}
        self.additional_mappings = additional_mappings or {}
        self.default_provider: str = default_provider
        load_dotenv(dotenv_path=env_file)

    def create_agent_from_yaml_path(self, yaml_path: str | Path) -> ChatAgent:
        """Create a ChatAgent from a YAML file path.

        This method does the following things:
        1. Loads the YAML file into a AgentSchema object using open and agent_schema_dispatch.
        2. Validates that the loaded object is a PromptAgent.
        3. Creates the appropriate ChatClient based on the model provider and apiType.
        4. Parses the tools, options, and response format from the PromptAgent.
        5. Creates and returns a ChatAgent instance with the configured properties.

        Args:
            yaml_path: Path to the YAML file representation of a AgentSchema object

        Returns:
            The ``ChatAgent`` instance created from the YAML file.

        Raises:
            DeclarativeLoaderError: If the YAML does not represent a PromptAgent.
            ProviderLookupError: If the provider type is unknown or unsupported.
            ValueError: If a ReferenceConnection cannot be resolved.
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
        """Create a ChatAgent from a YAML string.

        This method does the following things:
        1. Loads the YAML string into a AgentSchema object using agent_schema_dispatch.
        2. Validates that the loaded object is a PromptAgent.
        3. Creates the appropriate ChatClient based on the model provider and apiType.
        4. Parses the tools, options, and response format from the PromptAgent.
        5. Creates and returns a ChatAgent instance with the configured properties.

        Args:
            yaml_str: YAML string representation of a AgentSchema object

        Returns:
            The ``ChatAgent`` instance created from the YAML string.

        Raises:
            DeclarativeLoaderError: If the YAML does not represent a PromptAgent.
            ProviderLookupError: If the provider type is unknown or unsupported.
            ValueError: If a ReferenceConnection cannot be resolved.
            ModuleNotFoundError: If the required module for the provider type cannot be imported.
            AttributeError: If the required class for the provider type cannot be found in the module.
        """
        prompt_agent = agent_schema_dispatch(yaml.safe_load(yaml_str))
        if not isinstance(prompt_agent, PromptAgent):
            raise DeclarativeLoaderError("Only yaml definitions for a PromptAgent are supported for agent creation.")

        # Step 1: Create the ChatClient
        client = self._get_client(prompt_agent)
        # Step 2: Get the chat options
        chat_options = self._parse_chat_options(prompt_agent.model)
        if tools := self._parse_tools(prompt_agent.tools):
            chat_options["tools"] = tools
        if output_schema := prompt_agent.outputSchema:
            chat_options["response_format"] = _create_model_from_json_schema("agent", output_schema.to_json_schema())
        # Step 3: Create the agent instance
        return ChatAgent(
            chat_client=client,
            name=prompt_agent.name,
            description=prompt_agent.description,
            instructions=prompt_agent.instructions,
            **chat_options,
        )

    def _get_client(self, prompt_agent: PromptAgent) -> ChatClientProtocol:
        """Create the ChatClientProtocol instance based on the PromptAgent model."""
        if not prompt_agent.model:
            # if no model is defined, use the supplied chat_client
            if self.chat_client:
                return self.chat_client
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
            # if prompt_agent.model is defined, but no id, use the supplied chat_client
            if self.chat_client:
                return self.chat_client
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

    def _parse_tools(self, tools: list[Tool] | None) -> list[ToolProtocol] | None:
        """Parse tool resources into ToolProtocol instances."""
        if not tools:
            return None
        return [self._parse_tool(tool_resource) for tool_resource in tools]

    def _parse_tool(self, tool_resource: Tool) -> ToolProtocol:
        """Parse a single tool resource into a ToolProtocol instance."""
        match tool_resource:
            case FunctionTool():
                func: Callable[..., Any] | None = None
                if self.bindings and tool_resource.bindings:
                    for binding in tool_resource.bindings:
                        if binding.name and (func := self.bindings.get(binding.name)):
                            break
                return AIFunction(  # type: ignore
                    name=tool_resource.name,  # type: ignore
                    description=tool_resource.description,  # type: ignore
                    input_model=tool_resource.parameters.to_json_schema() if tool_resource.parameters else None,
                    func=func,
                )
            case WebSearchTool():
                return HostedWebSearchTool(
                    description=tool_resource.description, additional_properties=tool_resource.options
                )
            case FileSearchTool():
                add_props: dict[str, Any] = {}
                if tool_resource.ranker is not None:
                    add_props["ranker"] = tool_resource.ranker
                if tool_resource.scoreThreshold is not None:
                    add_props["score_threshold"] = tool_resource.scoreThreshold
                if tool_resource.filters:
                    add_props["filters"] = tool_resource.filters
                return HostedFileSearchTool(
                    inputs=[HostedVectorStoreContent(id) for id in tool_resource.vectorStoreIds or []],
                    description=tool_resource.description,
                    max_results=tool_resource.maximumResultCount,
                    additional_properties=add_props,
                )
            case CodeInterpreterTool():
                return HostedCodeInterpreterTool(
                    inputs=[HostedFileContent(file_id=file) for file in tool_resource.fileIds or []],
                    description=tool_resource.description,
                )
            case McpTool():
                approval_mode: HostedMCPSpecificApproval | Literal["always_require", "never_require"] | None = None
                if tool_resource.approvalMode is not None:
                    if tool_resource.approvalMode.kind == "always":
                        approval_mode = "always_require"
                    elif tool_resource.approvalMode.kind == "never":
                        approval_mode = "never_require"
                    elif isinstance(tool_resource.approvalMode, McpServerToolSpecifyApprovalMode):
                        approval_mode = {}
                        if tool_resource.approvalMode.alwaysRequireApprovalTools:
                            approval_mode["always_require_approval"] = (
                                tool_resource.approvalMode.alwaysRequireApprovalTools
                            )
                        if tool_resource.approvalMode.neverRequireApprovalTools:
                            approval_mode["never_require_approval"] = (
                                tool_resource.approvalMode.neverRequireApprovalTools
                            )
                        if not approval_mode:
                            approval_mode = None
                return HostedMCPTool(
                    name=tool_resource.name,  # type: ignore
                    description=tool_resource.description,
                    url=tool_resource.url,  # type: ignore
                    allowed_tools=tool_resource.allowedTools,
                    approval_mode=approval_mode,
                )
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
