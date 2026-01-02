# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import Mapping, MutableSequence
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
from agent_framework.exceptions import ServiceInitializationError, ServiceInvalidRequestError
from agent_framework.observability import use_instrumentation
from agent_framework.openai._responses_client import OpenAIBaseResponsesClient
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    MCPTool,
    PromptAgentDefinition,
    PromptAgentDefinitionText,
    ResponseTextFormatConfigurationJsonObject,
    ResponseTextFormatConfigurationJsonSchema,
    ResponseTextFormatConfigurationText,
)
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from pydantic import BaseModel, ValidationError

from ._shared import AzureAISettings

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover


logger = get_logger("agent_framework.azure")


TAzureAIClient = TypeVar("TAzureAIClient", bound="AzureAIClient")


@use_function_invocation
@use_instrumentation
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
        agent_description: str | None = None,
        conversation_id: str | None = None,
        project_endpoint: str | None = None,
        model_deployment_name: str | None = None,
        credential: AsyncTokenCredential | None = None,
        use_latest_version: bool | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure AI Agent client.

        Keyword Args:
            project_client: An existing AIProjectClient to use. If not provided, one will be created.
            agent_name: The name to use when creating new agents or using existing agents.
            agent_version: The version of the agent to use.
            agent_description: The description to use when creating new agents.
            conversation_id: Default conversation ID to use for conversations. Can be overridden by
                conversation_id property when making a request.
            project_endpoint: The Azure AI Project endpoint URL.
                Can also be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
                Ignored when a project_client is passed.
            model_deployment_name: The model deployment name to use for agent creation.
                Can also be set via environment variable AZURE_AI_MODEL_DEPLOYMENT_NAME.
            credential: Azure async credential to use for authentication.
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
                client = AzureAIClient(credential=credential)

                # Or passing parameters directly
                client = AzureAIClient(
                    project_endpoint="https://your-project.cognitiveservices.azure.com",
                    model_deployment_name="gpt-4",
                    credential=credential,
                )

                # Or loading from a .env file
                client = AzureAIClient(credential=credential, env_file_path="path/to/.env")
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
            if not credential:
                raise ServiceInitializationError("Azure credential is required when project_client is not provided.")
            project_client = AIProjectClient(
                endpoint=azure_ai_settings.project_endpoint,
                credential=credential,
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
        self.agent_description = agent_description
        self.use_latest_version = use_latest_version
        self.project_client = project_client
        self.credential = credential
        self.model_id = azure_ai_settings.model_deployment_name
        self.conversation_id = conversation_id

        # Track whether the application endpoint is used
        self._is_application_endpoint = "/applications/" in project_client._config.endpoint  # type: ignore
        # Track whether we should close client connection
        self._should_close_client = should_close_client

    async def configure_azure_monitor(
        self,
        enable_sensitive_data: bool = False,
        **kwargs: Any,
    ) -> None:
        """Setup observability with Azure Monitor (Azure AI Foundry integration).

        This method configures Azure Monitor for telemetry collection using the
        connection string from the Azure AI project client.

        Args:
            enable_sensitive_data: Enable sensitive data logging (prompts, responses).
                Should only be enabled in development/test environments. Default is False.
            **kwargs: Additional arguments passed to configure_azure_monitor().
                Common options include:
                - enable_live_metrics (bool): Enable Azure Monitor Live Metrics
                - credential (TokenCredential): Azure credential for Entra ID auth
                - resource (Resource): Custom OpenTelemetry resource
                See https://learn.microsoft.com/python/api/azure-monitor-opentelemetry/azure.monitor.opentelemetry.configure_azure_monitor
                for full list of options.

        Raises:
            ImportError: If azure-monitor-opentelemetry-exporter is not installed.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureAIClient
                from azure.ai.projects.aio import AIProjectClient
                from azure.identity.aio import DefaultAzureCredential

                async with (
                    DefaultAzureCredential() as credential,
                    AIProjectClient(
                        endpoint="https://your-project.api.azureml.ms", credential=credential
                    ) as project_client,
                    AzureAIClient(project_client=project_client) as client,
                ):
                    # Setup observability with defaults
                    await client.configure_azure_monitor()

                    # With live metrics enabled
                    await client.configure_azure_monitor(enable_live_metrics=True)

                    # With sensitive data logging (dev/test only)
                    await client.configure_azure_monitor(enable_sensitive_data=True)

        Note:
            This method retrieves the Application Insights connection string from the
            Azure AI project client automatically. You must have Application Insights
            configured in your Azure AI project for this to work.
        """
        # Get connection string from project client
        try:
            conn_string = await self.project_client.telemetry.get_application_insights_connection_string()
        except ResourceNotFoundError:
            logger.warning(
                "No Application Insights connection string found for the Azure AI Project. "
                "Please ensure Application Insights is configured in your Azure AI project, "
                "or call configure_otel_providers() manually with custom exporters."
            )
            return

        # Import Azure Monitor with proper error handling
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
        except ImportError as exc:
            raise ImportError(
                "azure-monitor-opentelemetry is required for Azure Monitor integration. "
                "Install it with: pip install azure-monitor-opentelemetry"
            ) from exc

        from agent_framework.observability import create_metric_views, create_resource, enable_instrumentation

        # Create resource if not provided in kwargs
        if "resource" not in kwargs:
            kwargs["resource"] = create_resource()

        # Configure Azure Monitor with connection string and kwargs
        configure_azure_monitor(
            connection_string=conn_string,
            views=create_metric_views(),
            **kwargs,
        )

        # Complete setup with core observability
        enable_instrumentation(enable_sensitive_data=enable_sensitive_data)

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the project_client."""
        await self._close_client_if_needed()

    def _create_text_format_config(
        self, response_format: Any
    ) -> (
        ResponseTextFormatConfigurationJsonSchema
        | ResponseTextFormatConfigurationJsonObject
        | ResponseTextFormatConfigurationText
    ):
        """Convert response_format into Azure text format configuration."""
        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            return ResponseTextFormatConfigurationJsonSchema(
                name=response_format.__name__,
                schema=response_format.model_json_schema(),
            )

        if isinstance(response_format, Mapping):
            format_config = self._convert_response_format(response_format)
            format_type = format_config.get("type")
            if format_type == "json_schema":
                config_kwargs: dict[str, Any] = {
                    "name": format_config.get("name") or "response",
                    "schema": format_config["schema"],
                }
                if "strict" in format_config:
                    config_kwargs["strict"] = format_config["strict"]
                if "description" in format_config:
                    config_kwargs["description"] = format_config["description"]
                return ResponseTextFormatConfigurationJsonSchema(**config_kwargs)
            if format_type == "json_object":
                return ResponseTextFormatConfigurationJsonObject()
            if format_type == "text":
                return ResponseTextFormatConfigurationText()

        raise ServiceInvalidRequestError("response_format must be a Pydantic model or mapping.")

    async def _get_agent_reference_or_create(
        self, run_options: dict[str, Any], messages_instructions: str | None
    ) -> dict[str, str]:
        """Determine which agent to use and create if needed.

        Returns:
            dict[str, str]: The agent reference to use.
        """
        # Agent name must be explicitly provided by the user.
        if self.agent_name is None:
            raise ServiceInitializationError(
                "Agent name is required. Provide 'agent_name' when initializing AzureAIClient "
                "or 'name' when initializing ChatAgent."
            )

        # If no agent_version is provided, either use latest version or create a new agent:
        if self.agent_version is None:
            # Try to use latest version if requested and agent exists
            if self.use_latest_version:
                try:
                    existing_agent = await self.project_client.agents.get(self.agent_name)
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
            if "temperature" in run_options:
                args["temperature"] = run_options["temperature"]
            if "top_p" in run_options:
                args["top_p"] = run_options["top_p"]

            if "response_format" in run_options:
                response_format = run_options["response_format"]
                args["text"] = PromptAgentDefinitionText(format=self._create_text_format_config(response_format))

            # Combine instructions from messages and options
            combined_instructions = [
                instructions
                for instructions in [messages_instructions, run_options.get("instructions")]
                if instructions
            ]
            if combined_instructions:
                args["instructions"] = "".join(combined_instructions)

            created_agent = await self.project_client.agents.create_version(
                agent_name=self.agent_name,
                definition=PromptAgentDefinition(**args),
                description=self.agent_description,
            )

            self.agent_version = created_agent.version

        return {"name": self.agent_name, "version": self.agent_version, "type": "agent_reference"}

    async def _close_client_if_needed(self) -> None:
        """Close project_client session if we created it."""
        if self._should_close_client:
            await self.project_client.close()

    @override
    async def _prepare_options(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Take ChatOptions and create the specific options for Azure AI."""
        prepared_messages, instructions = self._prepare_messages_for_azure_ai(messages)
        run_options = await super()._prepare_options(prepared_messages, chat_options, **kwargs)
        if not self._is_application_endpoint:
            # Application-scoped response APIs do not support "agent" property.
            agent_reference = await self._get_agent_reference_or_create(run_options, instructions)
            run_options["extra_body"] = {"agent": agent_reference}

        # Remove properties that are not supported on request level
        # but were configured on agent level
        exclude = ["model", "tools", "response_format", "temperature", "top_p"]

        for property in exclude:
            run_options.pop(property, None)

        return run_options

    @override
    def _get_current_conversation_id(self, chat_options: ChatOptions, **kwargs: Any) -> str | None:
        """Get the current conversation ID from chat options or kwargs."""
        return chat_options.conversation_id or kwargs.get("conversation_id") or self.conversation_id

    def _prepare_messages_for_azure_ai(
        self, messages: MutableSequence[ChatMessage]
    ) -> tuple[list[ChatMessage], str | None]:
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

    async def _initialize_client(self) -> None:
        """Initialize OpenAI client."""
        self.client = self.project_client.get_openai_client()  # type: ignore

    def _update_agent_name_and_description(self, agent_name: str | None, description: str | None = None) -> None:
        """Update the agent name in the chat client.

        Args:
            agent_name: The new name for the agent.
            description: The new description for the agent.
        """
        # This is a no-op in the base class, but can be overridden by subclasses
        # to update the agent name in the client.
        if agent_name and not self.agent_name:
            self.agent_name = agent_name
        if description and not self.agent_description:
            self.agent_description = description

    @staticmethod
    def _prepare_mcp_tool(tool: HostedMCPTool) -> MCPTool:  # type: ignore[override]
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
