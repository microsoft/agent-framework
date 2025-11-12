# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import MutableSequence
from typing import Any, ClassVar, TypeVar

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    ChatMessage,
    ChatOptions,
    HostedMCPTool,
    TextContent,
    get_logger,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_observability
from agent_framework.openai._responses_client import OpenAIBaseResponsesClient
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    MCPTool,
    PromptAgentDefinition,
    PromptAgentDefinitionText,
    ResponseTextFormatConfigurationJsonSchema,
)
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from openai.types.responses.parsed_response import (
    ParsedResponse,
)
from openai.types.responses.response import Response as OpenAIResponse
from pydantic import BaseModel, ValidationError

from ._shared import AzureAISettings

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = get_logger("agent_framework.azure")


TAzureAIClient = TypeVar("TAzureAIClient", bound="AzureAIClient")


@use_function_invocation
@use_observability
@use_chat_middleware
class AzureAIClient(OpenAIBaseResponsesClient):
    """Azure AI Agent client."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        project_client: AIProjectClient | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        conversation_id: str | None = None,
        project_endpoint: str | None = None,
        model_deployment_name: str | None = None,
        async_credential: AsyncTokenCredential | None = None,
        use_latest_version: bool | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure AI Agent client.

        Keyword Args:
            project_client: An existing AIProjectClient to use. If not provided, one will be created.
            agent_name: The name to use when creating new agents.
            agent_version: The version of the agent to use.
            conversation_id: Default conversation ID to use for conversations. Can be overridden by
                conversation_id property when making a request.
            project_endpoint: The Azure AI Project endpoint URL.
                Can also be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
                Ignored when a project_client is passed.
            model_deployment_name: The model deployment name to use for agent creation.
                Can also be set via environment variable AZURE_AI_MODEL_DEPLOYMENT_NAME.
            async_credential: Azure async credential to use for authentication.
            use_latest_version: Boolean flag that indicates whether to use latest agent version
                if it exists in the service.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureAIClient
                from azure.identity.aio import DefaultAzureCredential

                # Using environment variables
                # Set AZURE_AI_PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com
                # Set AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4
                credential = DefaultAzureCredential()
                client = AzureAIClient(async_credential=credential)

                # Or passing parameters directly
                client = AzureAIClient(
                    project_endpoint="https://your-project.cognitiveservices.azure.com",
                    model_deployment_name="gpt-4",
                    async_credential=credential,
                )

                # Or loading from a .env file
                client = AzureAIClient(async_credential=credential, env_file_path="path/to/.env")
        """
        try:
            azure_ai_settings = AzureAISettings(
                project_endpoint=project_endpoint,
                model_deployment_name=model_deployment_name,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Azure AI settings.", ex) from ex

        # If no project_client is provided, create one
        should_close_client = False
        if project_client is None:
            if not azure_ai_settings.project_endpoint:
                raise ServiceInitializationError(
                    "Azure AI project endpoint is required. Set via 'project_endpoint' parameter "
                    "or 'AZURE_AI_PROJECT_ENDPOINT' environment variable."
                )

            # Use provided credential
            if not async_credential:
                raise ServiceInitializationError("Azure credential is required when project_client is not provided.")
            project_client = AIProjectClient(
                endpoint=azure_ai_settings.project_endpoint,
                credential=async_credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )
            should_close_client = True

        # Initialize parent
        super().__init__(
            **kwargs,
        )

        # Initialize instance variables
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.use_latest_version = use_latest_version
        self.project_client = project_client
        self.credential = async_credential
        self.model_id = azure_ai_settings.model_deployment_name
        self.conversation_id = conversation_id
        self._should_close_client = should_close_client  # Track whether we should close client connection

    async def setup_azure_ai_observability(self, enable_sensitive_data: bool | None = None) -> None:
        """Use this method to setup tracing in your Azure AI Project.

        This will take the connection string from the project project_client.
        It will override any connection string that is set in the environment variables.
        It will disable any OTLP endpoint that might have been set.
        """
        try:
            conn_string = await self.project_client.telemetry.get_application_insights_connection_string()
        except ResourceNotFoundError:
            logger.warning(
                "No Application Insights connection string found for the Azure AI Project, "
                "please call setup_observability() manually."
            )
            return
        from agent_framework.observability import setup_observability

        setup_observability(
            applicationinsights_connection_string=conn_string, enable_sensitive_data=enable_sensitive_data
        )

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the project_client."""
        await self._close_client_if_needed()

    async def _get_agent_reference_or_create(
        self, run_options: dict[str, Any], messages_instructions: str | None
    ) -> dict[str, str]:
        """Determine which agent to use and create if needed.

        Returns:
            str: The agent_name to use
        """
        agent_name = self.agent_name or "UnnamedAgent"

        # If no agent_version is provided, either use latest version or create a new agent:
        if self.agent_version is None:
            # Try to use latest version if requested and agent exists
            if self.use_latest_version:
                try:
                    existing_agent = await self.project_client.agents.get(agent_name)
                    self.agent_name = existing_agent.name
                    self.agent_version = existing_agent.versions.latest.version
                    return {"name": self.agent_name, "version": self.agent_version, "type": "agent_reference"}
                except ResourceNotFoundError:
                    # Agent doesn't exist, fall through to creation logic
                    pass

            if "model" not in run_options or not run_options["model"]:
                raise ServiceInitializationError(
                    "Model deployment name is required for agent creation, "
                    "can also be passed to the get_response methods."
                )

            args: dict[str, Any] = {"model": run_options["model"]}

            if "tools" in run_options:
                args["tools"] = run_options["tools"]

            if "response_format" in run_options:
                response_format = run_options["response_format"]
                args["text"] = PromptAgentDefinitionText(
                    format=ResponseTextFormatConfigurationJsonSchema(
                        name=response_format.__name__,
                        schema=response_format.model_json_schema(),
                    )
                )

            # Combine instructions from messages and options
            combined_instructions = [
                instructions
                for instructions in [messages_instructions, run_options.get("instructions")]
                if instructions
            ]
            if combined_instructions:
                args["instructions"] = "".join(combined_instructions)

            created_agent = await self.project_client.agents.create_version(
                agent_name=agent_name, definition=PromptAgentDefinition(**args)
            )

            self.agent_name = created_agent.name
            self.agent_version = created_agent.version

        return {"name": agent_name, "version": self.agent_version, "type": "agent_reference"}

    async def _close_client_if_needed(self) -> None:
        """Close project_client session if we created it."""
        if self._should_close_client:
            await self.project_client.close()

    def _prepare_input(self, messages: MutableSequence[ChatMessage]) -> tuple[list[ChatMessage], str | None]:
        """Prepare input from messages and convert system/developer messages to instructions."""
        result: list[ChatMessage] = []
        instructions_list: list[str] = []
        instructions: str | None = None

        # System/developer messages are turned into instructions, since there is no such message roles in Azure AI.
        for message in messages:
            if message.role.value in ["system", "developer"]:
                for text_content in [content for content in message.contents if isinstance(content, TextContent)]:
                    instructions_list.append(text_content.text)
            else:
                result.append(message)

        if len(instructions_list) > 0:
            instructions = "".join(instructions_list)

        return result, instructions

    async def prepare_options(
        self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions
    ) -> dict[str, Any]:
        chat_options.store = bool(chat_options.store or chat_options.store is None)
        prepared_messages, instructions = self._prepare_input(messages)
        run_options = await super().prepare_options(prepared_messages, chat_options)
        agent_reference = await self._get_agent_reference_or_create(run_options, instructions)

        run_options["extra_body"] = {"agent": agent_reference}

        conversation_id = chat_options.conversation_id or self.conversation_id

        # Handle different conversation ID formats
        if conversation_id:
            if conversation_id.startswith("resp_"):
                # For response IDs, set previous_response_id and remove conversation property
                run_options.pop("conversation", None)
                run_options["previous_response_id"] = conversation_id
            elif conversation_id.startswith("conv_"):
                # For conversation IDs, set conversation and remove previous_response_id property
                run_options.pop("previous_response_id", None)
                run_options["conversation"] = conversation_id

        # Remove properties that are not supported on request level
        # but were configured on agent level
        exclude = ["model", "tools", "response_format"]

        for property in exclude:
            run_options.pop(property, None)

        return run_options

    async def initialize_client(self) -> None:
        """Initialize OpenAI client asynchronously."""
        self.client = await self.project_client.get_openai_client()  # type: ignore

    def _update_agent_name(self, agent_name: str | None) -> None:
        """Update the agent name in the chat client.

        Args:
            agent_name: The new name for the agent.
        """
        # This is a no-op in the base class, but can be overridden by subclasses
        # to update the agent name in the client.
        if agent_name and not self.agent_name:
            self.agent_name = agent_name

    def get_mcp_tool(self, tool: HostedMCPTool) -> Any:
        """Get MCP tool from HostedMCPTool."""
        mcp = MCPTool(server_label=tool.name.replace(" ", "_"), server_url=str(tool.url))

        if tool.allowed_tools:
            mcp["allowed_tools"] = list(tool.allowed_tools)

        if tool.approval_mode:
            match tool.approval_mode:
                case str():
                    mcp["require_approval"] = "always" if tool.approval_mode == "always_require" else "never"
                case _:
                    if always_require_approvals := tool.approval_mode.get("always_require_approval"):
                        mcp["require_approval"] = {"always": {"tool_names": list(always_require_approvals)}}
                    if never_require_approvals := tool.approval_mode.get("never_require_approval"):
                        mcp["require_approval"] = {"never": {"tool_names": list(never_require_approvals)}}

        return mcp

    def get_conversation_id(
        self, response: OpenAIResponse | ParsedResponse[BaseModel], store: bool | None
    ) -> str | None:
        """Get the conversation ID from the response if store is True."""
        if store:
            # If conversation ID exists, it means that we operate with conversation
            # so we use conversation ID as input and output.
            if response.conversation and response.conversation.id:
                return response.conversation.id
            # If conversation ID doesn't exist, we operate with responses
            # so we use response ID as input and output.
            return response.id
        return None
