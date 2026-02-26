# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any, ClassVar, Generic, Literal, TypedDict, TypeVar, cast

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    Agent,
    Annotation,
    BaseContextProvider,
    ChatAndFunctionMiddlewareTypes,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationConfiguration,
    FunctionInvocationLayer,
    FunctionTool,
    Message,
    MiddlewareTypes,
    ResponseStream,
    TextSpanRegion,
)
from agent_framework._settings import load_settings
from agent_framework._tools import ToolTypes
from agent_framework.azure._entra_id_authentication import AzureCredentialTypes
from agent_framework.observability import ChatTelemetryLayer
from agent_framework.openai import OpenAIResponsesOptions
from agent_framework.openai._responses_client import RawOpenAIResponsesClient
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    ApproximateLocation,
    CodeInterpreterTool,
    CodeInterpreterToolAuto,
    ImageGenTool,
    MCPTool,
    PromptAgentDefinition,
    PromptAgentDefinitionText,
    RaiConfig,
    Reasoning,
    WebSearchPreviewTool,
)
from azure.ai.projects.models import FileSearchTool as ProjectsFileSearchTool
from azure.core.exceptions import ResourceNotFoundError

from ._shared import AzureAISettings, create_text_format_config

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore[import] # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self, TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import Self, TypedDict  # type: ignore # pragma: no cover


logger = logging.getLogger("agent_framework.azure")


class AzureAIProjectAgentOptions(OpenAIResponsesOptions, total=False):
    """Azure AI Project Agent options."""

    rai_config: RaiConfig
    """Configuration for Responsible AI (RAI) content filtering and safety features."""

    reasoning: Reasoning  # type: ignore[misc]
    """Configuration for enabling reasoning capabilities (requires azure.ai.projects.models.Reasoning)."""


AzureAIClientOptionsT = TypeVar(
    "AzureAIClientOptionsT",
    bound=TypedDict,  # type: ignore[valid-type]
    default="AzureAIProjectAgentOptions",
    covariant=True,
)

_DOC_INDEX_PATTERN = re.compile(r"doc_(\d+)")


class RawAzureAIClient(RawOpenAIResponsesClient[AzureAIClientOptionsT], Generic[AzureAIClientOptionsT]):
    """Raw Azure AI client without middleware, telemetry, or function invocation layers.

    Warning:
        **This class should not normally be used directly.** It does not include middleware,
        telemetry, or function invocation support that you most likely need. If you do use it,
        you should consider which additional layers to apply. There is a defined ordering that
        you should follow:

        1. **ChatMiddlewareLayer** - Should be applied first as it also prepares function middleware
        2. **FunctionInvocationLayer** - Handles tool/function calling loop
        3. **ChatTelemetryLayer** - Must be inside the function calling loop for correct per-call telemetry

        Use ``AzureAIClient`` instead for a fully-featured client with all layers applied.
    """

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
        credential: AzureCredentialTypes | None = None,
        use_latest_version: bool | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a bare Azure AI client.

        This is the core implementation without middleware, telemetry, or function invocation layers.
        For most use cases, prefer :class:`AzureAIClient` which includes all standard layers.

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
            credential: Azure credential for authentication. Accepts a TokenCredential,
                AsyncTokenCredential, or a callable token provider.
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

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework import ChatOptions


                class MyOptions(ChatOptions, total=False):
                    my_custom_option: str


                client: AzureAIClient[MyOptions] = AzureAIClient(credential=credential)
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        azure_ai_settings = load_settings(
            AzureAISettings,
            env_prefix="AZURE_AI_",
            project_endpoint=project_endpoint,
            model_deployment_name=model_deployment_name,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )

        # If no project_client is provided, create one
        should_close_client = False
        if project_client is None:
            resolved_endpoint = azure_ai_settings.get("project_endpoint")
            if not resolved_endpoint:
                raise ValueError(
                    "Azure AI project endpoint is required. Set via 'project_endpoint' parameter "
                    "or 'AZURE_AI_PROJECT_ENDPOINT' environment variable."
                )

            # Use provided credential
            if not credential:
                raise ValueError("Azure credential is required when project_client is not provided.")
            project_client = AIProjectClient(
                endpoint=resolved_endpoint,
                credential=credential,  # type: ignore[arg-type]
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
        self.model_id = azure_ai_settings.get("model_deployment_name")
        self.conversation_id = conversation_id

        # Track whether the application endpoint is used
        self._is_application_endpoint = "/applications/" in project_client._config.endpoint  # type: ignore
        # Track whether we should close client connection
        self._should_close_client = should_close_client
        # Track creation-time agent configuration for runtime mismatch warnings.
        self.warn_runtime_tools_and_structure_changed = False
        self._created_agent_tool_names: set[str] = set()
        self._created_agent_structured_output_signature: str | None = None

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

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the project_client."""
        await self._close_client_if_needed()

    async def _get_agent_reference_or_create(
        self,
        run_options: dict[str, Any],
        messages_instructions: str | None,
        chat_options: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
        """Determine which agent to use and create if needed.

        Args:
            run_options: The prepared options for the API call.
            messages_instructions: Instructions extracted from messages.
            chat_options: The chat options containing response_format and other settings.

        Returns:
            dict[str, str]: The agent reference to use.
        """
        # Agent name must be explicitly provided by the user.
        if self.agent_name is None:
            raise ValueError(
                "Agent name is required. Provide 'agent_name' when initializing AzureAIClient "
                "or 'name' when initializing Agent."
            )
        # If the agent exists and we do not want to track agent configuration, return early
        if self.agent_version is not None and not self.warn_runtime_tools_and_structure_changed:
            return {"name": self.agent_name, "version": self.agent_version, "type": "agent_reference"}

        # If no agent_version is provided, either use latest version or create a new agent:
        if self.agent_version is None:
            # Try to use latest version if requested and agent exists
            if self.use_latest_version:
                with suppress(ResourceNotFoundError):
                    existing_agent = await self.project_client.agents.get(self.agent_name)
                    self.agent_version = existing_agent.versions.latest.version
                    return {"name": self.agent_name, "version": self.agent_version, "type": "agent_reference"}

            if "model" not in run_options or not run_options["model"]:
                raise ValueError(
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
            if "reasoning" in run_options:
                args["reasoning"] = run_options["reasoning"]
            if "rai_config" in run_options:
                args["rai_config"] = run_options["rai_config"]

            # response_format is accessed from chat_options or additional_properties
            # since the base class excludes it from run_options
            if chat_options and (response_format := chat_options.get("response_format")):
                args["text"] = PromptAgentDefinitionText(format=create_text_format_config(response_format))

            # Combine instructions from messages and options
            # instructions is accessed from chat_options since the base class excludes it from run_options
            combined_instructions = [
                instructions
                for instructions in [messages_instructions, chat_options.get("instructions") if chat_options else None]
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
            self.warn_runtime_tools_and_structure_changed = True
            self._created_agent_tool_names = self._extract_tool_names(run_options.get("tools"))
            self._created_agent_structured_output_signature = self._get_structured_output_signature(chat_options)
        return {"name": self.agent_name, "version": self.agent_version, "type": "agent_reference"}

    async def _close_client_if_needed(self) -> None:
        """Close project_client session if we created it."""
        if self._should_close_client:
            await self.project_client.close()

    def _extract_tool_names(self, tools: Any) -> set[str]:
        """Extract comparable tool names from runtime tool payloads."""
        if not isinstance(tools, Sequence) or isinstance(tools, str | bytes):
            return set()
        return {self._get_tool_name(tool) for tool in tools}

    def _get_tool_name(self, tool: Any) -> str:
        """Get a stable name for a tool for runtime comparison."""
        if isinstance(tool, FunctionTool):
            return tool.name
        if isinstance(tool, Mapping):
            tool_type = tool.get("type")
            if tool_type == "function":
                if isinstance(function_data := tool.get("function"), Mapping) and function_data.get("name"):
                    return str(function_data["name"])
                if tool.get("name"):
                    return str(tool["name"])
            if tool.get("name"):
                return str(tool["name"])
            if tool.get("server_label"):
                return f"mcp:{tool['server_label']}"
            if tool_type:
                return str(tool_type)
        if getattr(tool, "name", None):
            return str(tool.name)
        if getattr(tool, "server_label", None):
            return f"mcp:{tool.server_label}"
        if getattr(tool, "type", None):
            return str(tool.type)
        return type(tool).__name__

    def _get_structured_output_signature(self, chat_options: Mapping[str, Any] | None) -> str | None:
        """Build a stable signature for structured_output/response_format values."""
        if not chat_options:
            return None
        response_format = chat_options.get("response_format")
        if response_format is None:
            return None
        if isinstance(response_format, type):
            return f"{response_format.__module__}.{response_format.__qualname__}"
        if isinstance(response_format, Mapping):
            return json.dumps(response_format, sort_keys=True, default=str)
        return str(response_format)

    def _remove_agent_level_run_options(
        self,
        run_options: dict[str, Any],
        chat_options: Mapping[str, Any] | None = None,
    ) -> None:
        """Remove request-level options that Azure AI only supports at agent creation time."""
        runtime_tools = run_options.get("tools")
        runtime_structured_output = self._get_structured_output_signature(chat_options)

        if runtime_tools is not None or runtime_structured_output is not None:
            tools_changed = runtime_tools is not None
            structured_output_changed = runtime_structured_output is not None

            if self.warn_runtime_tools_and_structure_changed:
                if runtime_tools is not None:
                    tools_changed = self._extract_tool_names(runtime_tools) != self._created_agent_tool_names
                if runtime_structured_output is not None:
                    structured_output_changed = (
                        runtime_structured_output != self._created_agent_structured_output_signature
                    )

            if tools_changed or structured_output_changed:
                logger.warning(
                    "AzureAIClient does not support runtime tools or structured_output overrides after agent creation. "
                    "Use AzureOpenAIResponsesClient instead."
                )

        agent_level_option_to_run_keys = {
            "model_id": ("model",),
            "tools": ("tools",),
            "response_format": ("response_format", "text", "text_format"),
            "rai_config": ("rai_config",),
            "temperature": ("temperature",),
            "top_p": ("top_p",),
            "reasoning": ("reasoning",),
        }

        for run_keys in agent_level_option_to_run_keys.values():
            for run_key in run_keys:
                run_options.pop(run_key, None)

    @override
    async def _prepare_options(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Take ChatOptions and create the specific options for Azure AI."""
        prepared_messages, instructions = self._prepare_messages_for_azure_ai(messages)
        run_options = await super()._prepare_options(prepared_messages, options, **kwargs)

        # WORKAROUND: Azure AI Projects 'create responses' API has schema divergence from OpenAI's
        # Responses API. Azure requires 'type' at item level and 'annotations' in content items.
        # See: https://github.com/Azure/azure-sdk-for-python/issues/44493
        # See: https://github.com/microsoft/agent-framework/issues/2926
        # TODO(agent-framework#2926): Remove this workaround when Azure SDK aligns with OpenAI schema.
        if "input" in run_options and isinstance(run_options["input"], list):
            run_options["input"] = self._transform_input_for_azure_ai(cast(list[dict[str, Any]], run_options["input"]))

        if not self._is_application_endpoint:
            # Application-scoped response APIs do not support "agent" property.
            agent_reference = await self._get_agent_reference_or_create(run_options, instructions, options)
            run_options["extra_body"] = {"agent": agent_reference}

        # Remove only keys that map to this client's declared options TypedDict.
        self._remove_agent_level_run_options(run_options, options)

        return run_options

    @override
    def _check_model_presence(self, run_options: dict[str, Any]) -> None:
        # Skip model check for application endpoints - model is pre-configured on server
        if self._is_application_endpoint:
            return
        if not run_options.get("model"):
            if not self.model_id:
                raise ValueError("model_deployment_name must be a non-empty string")
            run_options["model"] = self.model_id

    def _transform_input_for_azure_ai(self, input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform input items to match Azure AI Projects expected schema.

        WORKAROUND: Azure AI Projects 'create responses' API expects a different schema than OpenAI's
        Responses API. Azure requires 'type' at the item level, and requires 'annotations'
        only for output_text content items (assistant messages), not for input_text content items
        (user messages). This helper adapts the OpenAI-style input to the Azure schema.

        See: https://github.com/Azure/azure-sdk-for-python/issues/44493
        TODO(agent-framework#2926): Remove when Azure SDK aligns with OpenAI schema.
        """
        transformed: list[dict[str, Any]] = []
        for item in input_items:
            new_item: dict[str, Any] = dict(item)

            # Add 'type': 'message' at item level for role-based items
            if "role" in new_item and "type" not in new_item:
                new_item["type"] = "message"

            # Add 'annotations' only to output_text content items (assistant messages)
            # User messages (input_text) do NOT support annotations in Azure AI
            if "content" in new_item and isinstance(new_item["content"], list):
                new_content: list[dict[str, Any] | Any] = []
                for content_item in new_item["content"]:
                    if isinstance(content_item, dict):
                        new_content_item: dict[str, Any] = dict(content_item)
                        # Only add annotations to output_text (assistant content)
                        if new_content_item.get("type") == "output_text" and "annotations" not in new_content_item:
                            new_content_item["annotations"] = []
                        new_content.append(new_content_item)
                    else:
                        new_content.append(content_item)
                new_item["content"] = new_content

            transformed.append(new_item)

        return transformed

    @override
    def _get_current_conversation_id(self, options: Mapping[str, Any], **kwargs: Any) -> str | None:
        """Get the current conversation ID from chat options or kwargs."""
        return options.get("conversation_id") or kwargs.get("conversation_id") or self.conversation_id

    def _prepare_messages_for_azure_ai(self, messages: Sequence[Message]) -> tuple[list[Message], str | None]:
        """Prepare input from messages and convert system/developer messages to instructions."""
        result: list[Message] = []
        instructions_list: list[str] = []
        instructions: str | None = None

        # System/developer messages are turned into instructions, since there is no such message roles in Azure AI.
        for message in messages:
            if message.role in ["system", "developer"]:
                for text_content in [content for content in message.contents if content.type == "text"]:
                    instructions_list.append(text_content.text)  # type: ignore[arg-type]
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

    # region Azure AI Search Citation Enhancement

    def _extract_azure_search_urls(self, output_items: Any) -> list[str]:
        """Extract document URLs from azure_ai_search_call_output items.

        Args:
            output_items: The response output items to scan.

        Returns:
            A flat list of get_urls from all azure_ai_search_call_output items.
        """
        get_urls: list[str] = []
        for item in output_items:
            if item.type != "azure_ai_search_call_output":
                continue
            output = item.output
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    continue
            if isinstance(output, list):
                # Streaming "added" events send output as an empty list; skip.
                continue
            if output is not None:
                urls = output.get("get_urls") if isinstance(output, dict) else output.get_urls
                if urls and isinstance(urls, list):
                    get_urls.extend(urls)
        return get_urls

    def _get_search_doc_url(self, citation_title: str | None, get_urls: list[str]) -> str | None:
        """Map a citation title like 'doc_0' to its corresponding get_url.

        Args:
            citation_title: The annotation title (e.g., "doc_0").
            get_urls: The list of document URLs from azure_ai_search_call_output.

        Returns:
            The matching document URL if found, otherwise None.
        """
        if not citation_title or not get_urls:
            return None
        match = _DOC_INDEX_PATTERN.search(citation_title)
        if not match:
            return None
        doc_index = int(match.group(1))
        if 0 <= doc_index < len(get_urls):
            return str(get_urls[doc_index])
        return None

    def _enrich_annotations_with_search_urls(self, contents: list[Content], get_urls: list[str]) -> None:
        """Enrich citation annotations in contents with real document URLs from Azure AI Search.

        Looks for annotations with ``type == "citation"`` and a ``title`` matching ``doc_N``,
        then adds the corresponding document URL from *get_urls* to ``additional_properties["get_url"]``.

        Args:
            contents: The parsed content list from a ChatResponse or ChatResponseUpdate.
            get_urls: Document URLs extracted from azure_ai_search_call_output.
        """
        if not get_urls:
            return
        for content in contents:
            if not content.annotations:
                continue
            for annotation in content.annotations:
                if not isinstance(annotation, dict):
                    continue
                if annotation.get("type") != "citation":
                    continue
                title = annotation.get("title")
                doc_url = self._get_search_doc_url(title, get_urls)
                if doc_url:
                    annotation.setdefault("additional_properties", {})["get_url"] = doc_url

    def _build_url_citation_content(
        self, annotation_data: dict[str, Any], get_urls: list[str], raw_event: Any
    ) -> Content:
        """Build a Content with a citation Annotation from a url_citation streaming event.

        The base class does not handle ``url_citation`` annotations in streaming, so this
        method creates the appropriate framework content for them.

        Args:
            annotation_data: The raw annotation dict from the streaming event.
            get_urls: Captured document URLs for enrichment.
            raw_event: The raw streaming event for raw_representation.

        Returns:
            A Content object containing the citation annotation.
        """
        ann_title = str(annotation_data.get("title") or "")
        ann_url = str(annotation_data.get("url") or "")
        ann_start = annotation_data.get("start_index")
        ann_end = annotation_data.get("end_index")

        additional_props: dict[str, Any] = {
            "annotation_index": raw_event.annotation_index,
        }
        doc_url = self._get_search_doc_url(ann_title, get_urls)
        if doc_url:
            additional_props["get_url"] = doc_url

        annotation_obj = Annotation(
            type="citation",
            title=ann_title,
            url=ann_url,
            additional_properties=additional_props,
            raw_representation=annotation_data,
        )
        if ann_start is not None and ann_end is not None:
            annotation_obj["annotated_regions"] = [
                TextSpanRegion(type="text_span", start_index=ann_start, end_index=ann_end)
            ]

        return Content.from_text(text="", annotations=[annotation_obj], raw_representation=raw_event)

    @override
    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        stream: bool = False,
        **kwargs: Any,
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        """Wrap base response to enrich Azure AI Search citation annotations.

        For non-streaming responses, the ``ChatResponse.raw_representation`` carries the
        full response including ``azure_ai_search_call_output`` items.  After the base class
        parses the response, ``url_citation`` annotations are enriched with per-document URLs.

        For streaming responses, a transform hook is registered on the ``ResponseStream`` to
        capture ``get_urls`` from search output events and enrich ``url_citation`` annotations
        as they arrive.  The captured URL state is local to the stream closure, so concurrent
        streams do not interfere.
        """
        if not stream:

            async def _enrich_response() -> ChatResponse:
                response = await super(RawAzureAIClient, self)._inner_get_response(
                    messages=messages, options=options, stream=False, **kwargs
                )
                get_urls = self._extract_azure_search_urls(response.raw_representation.output)  # type: ignore[union-attr]
                if get_urls:
                    for msg in response.messages:
                        self._enrich_annotations_with_search_urls(list(msg.contents or []), get_urls)
                return response

            return _enrich_response()

        # Streaming: use a closure-local list so concurrent streams don't interfere
        stream_result = super()._inner_get_response(  # type: ignore[assignment]
            messages=messages, options=options, stream=True, **kwargs
        )
        search_get_urls: list[str] = []

        def _enrich_update(update: ChatResponseUpdate) -> ChatResponseUpdate:
            raw = update.raw_representation
            if raw is None:
                return update
            event_type = raw.type

            # Capture get_urls from azure_ai_search_call_output items.
            # Check both "added" and "done" events because the output data (including
            # get_urls) may only be fully populated in the "done" event.
            if event_type in ("response.output_item.added", "response.output_item.done"):
                urls = self._extract_azure_search_urls([raw.item])
                if urls:
                    search_get_urls.extend(urls)

            # Handle url_citation annotations (not handled by the base class in streaming)
            if event_type == "response.output_text.annotation.added":
                ann = raw.annotation
                if ann.get("type") == "url_citation":
                    citation_content = self._build_url_citation_content(ann, search_get_urls, raw)
                    contents_list = list(update.contents or [])
                    contents_list.append(citation_content)
                    return ChatResponseUpdate(
                        contents=contents_list,
                        conversation_id=update.conversation_id,
                        response_id=update.response_id,
                        role=update.role,
                        model_id=update.model_id,
                        continuation_token=update.continuation_token,
                        additional_properties=update.additional_properties,
                        raw_representation=update.raw_representation,
                    )

            # Enrich any citation annotations already parsed by the base class
            if update.contents and search_get_urls:
                self._enrich_annotations_with_search_urls(list(update.contents), search_get_urls)

            return update

        stream_result.with_transform_hook(_enrich_update)  # type: ignore[union-attr]
        return stream_result

    # endregion

    # region Hosted Tool Factory Methods (Azure-specific overrides)

    @staticmethod
    def get_code_interpreter_tool(  # type: ignore[override]
        *,
        file_ids: list[str] | None = None,
        container: Literal["auto"] | dict[str, Any] = "auto",
        **kwargs: Any,
    ) -> CodeInterpreterTool:
        """Create a code interpreter tool configuration for Azure AI Projects.

        Keyword Args:
            file_ids: Optional list of file IDs to make available to the code interpreter.
            container: Container configuration. Use "auto" for automatic container management.
                Note: Custom container settings from this parameter are not used by Azure AI Projects;
                use file_ids instead.
            **kwargs: Additional arguments passed to the SDK CodeInterpreterTool constructor.

        Returns:
            A CodeInterpreterTool ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureAIClient

                tool = AzureAIClient.get_code_interpreter_tool()
                agent = ChatAgent(client, tools=[tool])
        """
        # Extract file_ids from container if provided as dict and file_ids not explicitly set
        if file_ids is None and isinstance(container, dict):
            file_ids = container.get("file_ids")
        tool_container = CodeInterpreterToolAuto(file_ids=file_ids if file_ids else None)
        return CodeInterpreterTool(container=tool_container, **kwargs)

    @staticmethod
    def get_file_search_tool(
        *,
        vector_store_ids: list[str],
        max_num_results: int | None = None,
        ranking_options: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ProjectsFileSearchTool:
        """Create a file search tool configuration for Azure AI Projects.

        Keyword Args:
            vector_store_ids: List of vector store IDs to search.
            max_num_results: Maximum number of results to return (1-50).
            ranking_options: Ranking options for search results.
            filters: A filter to apply (ComparisonFilter or CompoundFilter).
            **kwargs: Additional arguments passed to the SDK FileSearchTool constructor.

        Returns:
            A FileSearchTool ready to pass to ChatAgent.

        Raises:
            ValueError: If vector_store_ids is empty.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureAIClient

                tool = AzureAIClient.get_file_search_tool(
                    vector_store_ids=["vs_abc123"],
                )
                agent = ChatAgent(client, tools=[tool])
        """
        if not vector_store_ids:
            raise ValueError("File search tool requires 'vector_store_ids' to be specified.")
        return ProjectsFileSearchTool(
            vector_store_ids=vector_store_ids,
            max_num_results=max_num_results,
            ranking_options=ranking_options,  # type: ignore[arg-type]
            filters=filters,  # type: ignore[arg-type]
            **kwargs,
        )

    @staticmethod
    def get_web_search_tool(  # type: ignore[override]
        *,
        user_location: dict[str, str] | None = None,
        search_context_size: Literal["low", "medium", "high"] | None = None,
        **kwargs: Any,
    ) -> WebSearchPreviewTool:
        """Create a web search preview tool configuration for Azure AI Projects.

        Keyword Args:
            user_location: Location context for search results. Dict with keys like
                "city", "country", "region", "timezone".
            search_context_size: Amount of context to include from search results.
                One of "low", "medium", or "high". Defaults to "medium".
            **kwargs: Additional arguments passed to the SDK WebSearchPreviewTool constructor.

        Returns:
            A WebSearchPreviewTool ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureAIClient

                tool = AzureAIClient.get_web_search_tool()
                agent = ChatAgent(client, tools=[tool])

                # With location and context size
                tool = AzureAIClient.get_web_search_tool(
                    user_location={"city": "Seattle", "country": "US"},
                    search_context_size="high",
                )
        """
        ws_tool = WebSearchPreviewTool(search_context_size=search_context_size, **kwargs)

        if user_location:
            ws_tool.user_location = ApproximateLocation(
                city=user_location.get("city"),
                country=user_location.get("country"),
                region=user_location.get("region"),
                timezone=user_location.get("timezone"),
            )

        return ws_tool

    @staticmethod
    def get_image_generation_tool(  # type: ignore[override]
        *,
        model: Literal["gpt-image-1"] | str | None = None,
        size: Literal["1024x1024", "1024x1536", "1536x1024", "auto"] | None = None,
        output_format: Literal["png", "webp", "jpeg"] | None = None,
        quality: Literal["low", "medium", "high", "auto"] | None = None,
        background: Literal["transparent", "opaque", "auto"] | None = None,
        partial_images: int | None = None,
        moderation: Literal["auto", "low"] | None = None,
        output_compression: int | None = None,
        **kwargs: Any,
    ) -> ImageGenTool:
        """Create an image generation tool configuration for Azure AI Projects.

        Keyword Args:
            model: The model to use for image generation.
            size: Output image size.
            output_format: Output image format.
            quality: Output image quality.
            background: Background transparency setting.
            partial_images: Number of partial images to return during generation.
            moderation: Moderation level.
            output_compression: Compression level.
            **kwargs: Additional arguments passed to the SDK ImageGenTool constructor.

        Returns:
            An ImageGenTool ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureAIClient

                tool = AzureAIClient.get_image_generation_tool()
                agent = ChatAgent(client, tools=[tool])
        """
        return ImageGenTool(  # type: ignore[misc]
            model=model,  # type: ignore[arg-type]
            size=size,
            output_format=output_format,
            quality=quality,
            background=background,
            partial_images=partial_images,
            moderation=moderation,
            output_compression=output_compression,
            **kwargs,
        )

    @staticmethod
    def get_mcp_tool(
        *,
        name: str,
        url: str | None = None,
        description: str | None = None,
        approval_mode: Literal["always_require", "never_require"] | dict[str, list[str]] | None = None,
        allowed_tools: list[str] | None = None,
        headers: dict[str, str] | None = None,
        project_connection_id: str | None = None,
        **kwargs: Any,
    ) -> MCPTool:
        """Create a hosted MCP tool configuration for Azure AI.

        This configures an MCP (Model Context Protocol) server that will be called
        by Azure AI's service. The tools from this MCP server are executed remotely
        by Azure AI, not locally by your application.

        Note:
            For local MCP execution where your application calls the MCP server
            directly, use the MCP client tools instead of this method.

        Keyword Args:
            name: A label/name for the MCP server.
            url: The URL of the MCP server. Required if project_connection_id is not provided.
            description: A description of what the MCP server provides.
            approval_mode: Tool approval mode. Use "always_require" or "never_require" for all tools,
                or provide a dict with "always_require_approval" and/or "never_require_approval"
                keys mapping to lists of tool names.
            allowed_tools: List of tool names that are allowed to be used from this MCP server.
            headers: HTTP headers to include in requests to the MCP server.
            project_connection_id: Azure AI Foundry connection ID for managed MCP connections.
                If provided, url and headers are not required.
            **kwargs: Additional arguments passed to the SDK MCPTool constructor.

        Returns:
            An MCPTool configuration ready to pass to ChatAgent.

        Examples:
            .. code-block:: python

                from agent_framework.azure import AzureAIClient

                # With URL
                tool = AzureAIClient.get_mcp_tool(
                    name="my_mcp",
                    url="https://mcp.example.com",
                )

                # With Azure AI Foundry connection
                tool = AzureAIClient.get_mcp_tool(
                    name="github_mcp",
                    project_connection_id="conn_abc123",
                    description="GitHub MCP via Azure AI Foundry",
                )

                agent = ChatAgent(client, tools=[tool])
        """
        mcp = MCPTool(server_label=name.replace(" ", "_"), server_url=url or "", **kwargs)

        if description:
            mcp["server_description"] = description

        if project_connection_id:
            mcp["project_connection_id"] = project_connection_id
        elif headers:
            mcp["headers"] = headers

        if allowed_tools:
            mcp["allowed_tools"] = allowed_tools

        if approval_mode:
            if isinstance(approval_mode, str):
                mcp["require_approval"] = "always" if approval_mode == "always_require" else "never"
            else:
                if always_require := approval_mode.get("always_require_approval"):
                    mcp["require_approval"] = {"always": {"tool_names": always_require}}
                if never_require := approval_mode.get("never_require_approval"):
                    mcp["require_approval"] = {"never": {"tool_names": never_require}}

        return mcp

    # endregion

    @override
    def as_agent(
        self,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        tools: ToolTypes | Callable[..., Any] | Sequence[ToolTypes | Callable[..., Any]] | None = None,
        default_options: AzureAIClientOptionsT | Mapping[str, Any] | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
        middleware: Sequence[MiddlewareTypes] | None = None,
        **kwargs: Any,
    ) -> Agent[AzureAIClientOptionsT]:
        """Convert this chat client to a Agent.

        This method creates a Agent instance with this client pre-configured.
        It does NOT create an agent on the Azure AI service - the actual agent
        will be created on the server during the first invocation (run).

        For creating and managing persistent agents on the server, use
        :class:`~agent_framework_azure_ai.AzureAIProjectAgentProvider` instead.

        Keyword Args:
            id: The unique identifier for the agent. Will be created automatically if not provided.
            name: The name of the agent.
            description: A brief description of the agent's purpose.
            instructions: Optional instructions for the agent.
            tools: The tools to use for the request.
            default_options: A TypedDict containing chat options.
            context_providers: Context providers to include during agent invocation.
            middleware: List of middleware to intercept agent and function invocations.
            kwargs: Any additional keyword arguments.

        Returns:
            A Agent instance configured with this chat client.
        """
        return super().as_agent(
            id=id,
            name=name,
            description=description,
            instructions=instructions,
            tools=tools,
            default_options=default_options,
            context_providers=context_providers,
            middleware=middleware,
            **kwargs,
        )


class AzureAIClient(
    ChatMiddlewareLayer[AzureAIClientOptionsT],
    FunctionInvocationLayer[AzureAIClientOptionsT],
    ChatTelemetryLayer[AzureAIClientOptionsT],
    RawAzureAIClient[AzureAIClientOptionsT],
    Generic[AzureAIClientOptionsT],
):
    """Azure AI client with middleware, telemetry, and function invocation support.

    This is the recommended client for most use cases. It includes:
    - Chat middleware support for request/response interception
    - OpenTelemetry-based telemetry for observability
    - Automatic function/tool invocation handling

    For a minimal implementation without these features, use :class:`RawAzureAIClient`.
    """

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
        credential: AzureCredentialTypes | None = None,
        use_latest_version: bool | None = None,
        middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
        function_invocation_configuration: FunctionInvocationConfiguration | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure AI client with full layer support.

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
            credential: Azure credential for authentication. Accepts a TokenCredential
                or AsyncTokenCredential.
            use_latest_version: Boolean flag that indicates whether to use latest agent version
                if it exists in the service.
            middleware: Optional sequence of chat middlewares to include.
            function_invocation_configuration: Optional function invocation configuration.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            kwargs: Additional keyword arguments passed to the parent class.

        Examples:
            .. code-block:: python

                from agent_framework_azure_ai import AzureAIClient
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

                # Using custom ChatOptions with type safety:
                from typing import TypedDict
                from agent_framework import ChatOptions


                class MyOptions(ChatOptions, total=False):
                    my_custom_option: str


                client: AzureAIClient[MyOptions] = AzureAIClient(credential=credential)
                response = await client.get_response("Hello", options={"my_custom_option": "value"})
        """
        super().__init__(
            project_client=project_client,
            agent_name=agent_name,
            agent_version=agent_version,
            agent_description=agent_description,
            conversation_id=conversation_id,
            project_endpoint=project_endpoint,
            model_deployment_name=model_deployment_name,
            credential=credential,
            use_latest_version=use_latest_version,
            middleware=middleware,
            function_invocation_configuration=function_invocation_configuration,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
            **kwargs,
        )
