# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import MutableSequence
from typing import Any, ClassVar, TypeVar

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    ChatMessage,
    ChatOptions,
    get_logger,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.observability import use_observability
from agent_framework.openai import OpenAIBaseResponsesClient
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from pydantic import ValidationError

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = get_logger("agent_framework.azure")


class AzureAISettings(AFBaseSettings):
    """Azure AI Project settings.

    The settings are first loaded from environment variables with the prefix 'AZURE_AI_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Keyword Args:
        project_endpoint: The Azure AI Project endpoint URL.
            Can be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
        model_deployment_name: The name of the model deployment to use.
            Can be set via environment variable AZURE_AI_MODEL_DEPLOYMENT_NAME.
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.

    Examples:
        .. code-block:: python

            from agent_framework_azure_ai import AzureAISettings

            # Using environment variables
            # Set AZURE_AI_PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com
            # Set AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4
            settings = AzureAISettings()

            # Or passing parameters directly
            settings = AzureAISettings(
                project_endpoint="https://your-project.cognitiveservices.azure.com", model_deployment_name="gpt-4"
            )

            # Or loading from a .env file
            settings = AzureAISettings(env_file_path="path/to/.env")
    """

    env_prefix: ClassVar[str] = "AZURE_AI_"

    project_endpoint: str | None = None
    model_deployment_name: str | None = None


TAzureAIAgentClient = TypeVar("TAzureAIAgentClient", bound="AzureAIAgentClientV2")


@use_function_invocation
@use_observability
@use_chat_middleware
class AzureAIAgentClientV2(OpenAIBaseResponsesClient):
    """Azure AI Agent Chat client."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        project_client: AIProjectClient | None = None,
        agent_name: str | None = None,
        agent_version: str | None = None,
        thread_id: str | None = None,
        project_endpoint: str | None = None,
        model_deployment_name: str | None = None,
        async_credential: AsyncTokenCredential | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure AI Agent client.

        Keyword Args:
            project_client: An existing AIProjectClient to use. If not provided, one will be created.
            agent_name: The name to use when creating new agents.
            agent_version: The version of the agent to use.
            thread_id: Default thread ID to use for conversations. Can be overridden by
                conversation_id property when making a request.
            project_endpoint: The Azure AI Project endpoint URL.
                Can also be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
                Ignored when a project_client is passed.
            model_deployment_name: The model deployment name to use for agent creation.
                Can also be set via environment variable AZURE_AI_MODEL_DEPLOYMENT_NAME.
            async_credential: Azure async credential to use for authentication.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Examples:
            .. code-block:: python

                from agent_framework_azure_ai import AzureAIAgentClient
                from azure.identity.aio import DefaultAzureCredential

                # Using environment variables
                # Set AZURE_AI_PROJECT_ENDPOINT=https://your-project.cognitiveservices.azure.com
                # Set AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4
                credential = DefaultAzureCredential()
                client = AzureAIAgentClient(async_credential=credential)

                # Or passing parameters directly
                client = AzureAIAgentClient(
                    project_endpoint="https://your-project.cognitiveservices.azure.com",
                    model_deployment_name="gpt-4",
                    async_credential=credential,
                )

                # Or loading from a .env file
                client = AzureAIAgentClient(async_credential=credential, env_file_path="path/to/.env")
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

            if not azure_ai_settings.model_deployment_name:
                raise ServiceInitializationError(
                    "Azure AI model deployment name is required. Set via 'model_deployment_name' parameter "
                    "or 'AZURE_AI_MODEL_DEPLOYMENT_NAME' environment variable."
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
            model_id=azure_ai_settings.model_deployment_name,  # type: ignore
            **kwargs,
        )

        # Initialize instance variables
        self.project_client = project_client
        self.credential = async_credential
        self.agent_name = agent_name or "UnnamedAgent"
        self.agent_version = agent_version
        self.model_id = azure_ai_settings.model_deployment_name
        self.thread_id = thread_id
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

    @classmethod
    def from_settings(cls: type[TAzureAIAgentClient], settings: dict[str, Any]) -> TAzureAIAgentClient:
        """Initialize a AzureAIAgentClient from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return cls(
            project_client=settings.get("project_client"),
            agent_id=settings.get("agent_id"),
            thread_id=settings.get("thread_id"),
            project_endpoint=settings.get("project_endpoint"),
            model_deployment_name=settings.get("model_deployment_name"),
            agent_name=settings.get("agent_name"),
            credential=settings.get("credential"),
            env_file_path=settings.get("env_file_path"),
        )

    async def _get_agent_reference_or_create(self, run_options: dict[str, Any] | None = None) -> dict[str, str]:
        """Determine which agent to use and create if needed.

        Returns:
            str: The agent_name to use
        """
        run_options = run_options or {}
        # If no agent_version is provided, create a new agent
        if self.agent_version is None:
            if "model" not in run_options or not run_options["model"]:
                raise ServiceInitializationError(
                    "Model deployment name is required for agent creation, "
                    "can also be passed to the get_response methods."
                )

            args: dict[str, Any] = {
                "model": run_options["model"],
            }
            if "tools" in run_options:
                args["tools"] = run_options["tools"]
            if "instructions" in run_options:
                args["instructions"] = run_options["instructions"]

            # TODO (dmytrostruk): Add response format

            created_agent = await self.project_client.agents.create_version(
                agent_name=self.agent_name, definition=PromptAgentDefinition(**args)
            )

            self.agent_name = created_agent.name
            self.agent_version = created_agent.version

        return {"name": self.agent_name, "version": self.agent_version, "type": "agent_reference"}

    async def _close_client_if_needed(self) -> None:
        """Close project_client session if we created it."""
        if self._should_close_client:
            await self.project_client.close()

    async def prepare_options(
        self, messages: MutableSequence[ChatMessage], chat_options: ChatOptions
    ) -> dict[str, Any]:
        run_options = await super().prepare_options(messages, chat_options)
        agent_reference = await self._get_agent_reference_or_create(run_options)

        run_options["extra_body"] = {"agent": agent_reference}

        # Remove properties that are not supported:
        if "model" in run_options:
            run_options.pop("model", None)

        if "tools" in run_options:
            run_options.pop("tools", None)

        return run_options

    async def initialize_client(self):
        """Initializes OpenAI client asynchronously."""
        self.client = await self.project_client.get_openai_client()  # type: ignore
