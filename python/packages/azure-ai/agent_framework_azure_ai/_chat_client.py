# Copyright (c) Microsoft. All rights reserved.

import ast
import json
import os
import re
import sys
from collections.abc import AsyncIterable, MutableMapping, MutableSequence, Sequence
from typing import Any, ClassVar, TypeVar

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AIFunction,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    CitationAnnotation,
    Contents,
    DataContent,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedCodeInterpreterTool,
    HostedFileContent,
    HostedFileSearchTool,
    HostedMCPTool,
    HostedVectorStoreContent,
    HostedWebSearchTool,
    Role,
    TextContent,
    TextSpanRegion,
    ToolMode,
    ToolProtocol,
    UriContent,
    UsageContent,
    UsageDetails,
    get_logger,
    prepare_function_call_results,
    use_chat_middleware,
    use_function_invocation,
)
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.observability import use_instrumentation
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import (
    Agent,
    AgentsNamedToolChoice,
    AgentsNamedToolChoiceType,
    AgentsToolChoiceOptionMode,
    AgentStreamEvent,
    AsyncAgentEventHandler,
    AsyncAgentRunStream,
    BingCustomSearchTool,
    BingGroundingTool,
    CodeInterpreterToolDefinition,
    FileSearchTool,
    FunctionName,
    FunctionToolDefinition,
    ListSortOrder,
    McpTool,
    MessageDeltaChunk,
    MessageDeltaTextContent,
    MessageDeltaTextFileCitationAnnotation,
    MessageDeltaTextFilePathAnnotation,
    MessageDeltaTextUrlCitationAnnotation,
    MessageImageUrlParam,
    MessageInputContentBlock,
    MessageInputImageUrlBlock,
    MessageInputTextBlock,
    MessageRole,
    RequiredFunctionToolCall,
    RequiredMcpToolCall,
    ResponseFormatJsonSchema,
    ResponseFormatJsonSchemaType,
    RunStatus,
    RunStep,
    RunStepDeltaChunk,
    RunStepDeltaCodeInterpreterDetailItemObject,
    RunStepDeltaCodeInterpreterImageOutput,
    RunStepDeltaCodeInterpreterLogOutput,
    SubmitToolApprovalAction,
    SubmitToolOutputsAction,
    ThreadMessageOptions,
    ThreadRun,
    ToolApproval,
    ToolDefinition,
    ToolOutput,
)
from azure.core.credentials_async import AsyncTokenCredential
from pydantic import ValidationError

from ._shared import AzureAISettings

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = get_logger("agent_framework.azure")


TAzureAIAgentClient = TypeVar("TAzureAIAgentClient", bound="AzureAIAgentClient")


@use_function_invocation
@use_instrumentation
@use_chat_middleware
class AzureAIAgentClient(BaseChatClient):
    """Azure AI Agent Chat client."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai"  # type: ignore[reportIncompatibleVariableOverride, misc]

    def __init__(
        self,
        *,
        agents_client: AgentsClient | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        agent_description: str | None = None,
        thread_id: str | None = None,
        project_endpoint: str | None = None,
        model_deployment_name: str | None = None,
        credential: AsyncTokenCredential | None = None,
        should_cleanup_agent: bool = True,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an Azure AI Agent client.

        Keyword Args:
            agents_client: An existing AgentsClient to use. If not provided, one will be created.
            agent_id: The ID of an existing agent to use. If not provided and agents_client is provided,
                a new agent will be created (and deleted after the request). If neither agents_client
                nor agent_id is provided, both will be created and managed automatically.
            agent_name: The name to use when creating new agents.
            agent_description: The description to use when creating new agents.
            thread_id: Default thread ID to use for conversations. Can be overridden by
                conversation_id property when making a request.
            project_endpoint: The Azure AI Project endpoint URL.
                Can also be set via environment variable AZURE_AI_PROJECT_ENDPOINT.
                Ignored when a agents_client is passed.
            model_deployment_name: The model deployment name to use for agent creation.
                Can also be set via environment variable AZURE_AI_MODEL_DEPLOYMENT_NAME.
            credential: Azure async credential to use for authentication.
            should_cleanup_agent: Whether to cleanup (delete) agents created by this client when
                the client is closed or context is exited. Defaults to True. Only affects agents
                created by this client instance; existing agents passed via agent_id are never deleted.
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
                client = AzureAIAgentClient(credential=credential)

                # Or passing parameters directly
                client = AzureAIAgentClient(
                    project_endpoint="https://your-project.cognitiveservices.azure.com",
                    model_deployment_name="gpt-4",
                    credential=credential,
                )

                # Or loading from a .env file
                client = AzureAIAgentClient(credential=credential, env_file_path="path/to/.env")
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

        # If no agents_client is provided, create one
        should_close_client = False
        if agents_client is None:
            if not azure_ai_settings.project_endpoint:
                raise ServiceInitializationError(
                    "Azure AI project endpoint is required. Set via 'project_endpoint' parameter "
                    "or 'AZURE_AI_PROJECT_ENDPOINT' environment variable."
                )

            if agent_id is None and not azure_ai_settings.model_deployment_name:
                raise ServiceInitializationError(
                    "Azure AI model deployment name is required. Set via 'model_deployment_name' parameter "
                    "or 'AZURE_AI_MODEL_DEPLOYMENT_NAME' environment variable."
                )

            # Use provided credential
            if not credential:
                raise ServiceInitializationError("Azure credential is required when agents_client is not provided.")
            agents_client = AgentsClient(
                endpoint=azure_ai_settings.project_endpoint,
                credential=credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )
            should_close_client = True

        # Initialize parent
        super().__init__(**kwargs)

        # Initialize instance variables
        self.agents_client = agents_client
        self.credential = credential
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.model_id = azure_ai_settings.model_deployment_name
        self.thread_id = thread_id
        self.should_cleanup_agent = should_cleanup_agent  # Track whether we should delete the agent
        self._agent_created = False  # Track whether agent was created inside this class
        self._should_close_client = should_close_client  # Track whether we should close client connection
        self._agent_definition: Agent | None = None  # Cached definition for existing agent

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit - clean up any agents we created."""
        await self.close()

    async def close(self) -> None:
        """Close the agents_client and clean up any agents we created."""
        await self._cleanup_agent_if_needed()
        await self._close_client_if_needed()

    @classmethod
    def from_settings(cls: type[TAzureAIAgentClient], settings: dict[str, Any]) -> TAzureAIAgentClient:
        """Initialize a AzureAIAgentClient from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return cls(
            agents_client=settings.get("agents_client"),
            agent_id=settings.get("agent_id"),
            thread_id=settings.get("thread_id"),
            project_endpoint=settings.get("project_endpoint"),
            model_deployment_name=settings.get("model_deployment_name"),
            agent_name=settings.get("agent_name"),
            credential=settings.get("credential"),
            env_file_path=settings.get("env_file_path"),
            should_cleanup_agent=settings.get("should_cleanup_agent", True),
        )

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        return await ChatResponse.from_chat_response_generator(
            updates=self._inner_get_streaming_response(messages=messages, chat_options=chat_options, **kwargs),
            output_format_type=chat_options.response_format,
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        # prepare
        run_options, required_action_results = await self._prepare_options(messages, chat_options, **kwargs)
        agent_id = await self._get_agent_id_or_create(run_options)

        # execute and process
        async for update in self._process_stream(
            *(await self._create_agent_stream(agent_id, run_options, required_action_results))
        ):
            yield update

    async def _get_agent_id_or_create(self, run_options: dict[str, Any] | None = None) -> str:
        """Determine which agent to use and create if needed.

        Returns:
            str: The agent_id to use
        """
        run_options = run_options or {}
        # If no agent_id is provided, create a temporary agent
        if self.agent_id is None:
            if "model" not in run_options or not run_options["model"]:
                raise ServiceInitializationError(
                    "Model deployment name is required for agent creation, "
                    "can also be passed to the get_response methods."
                )

            agent_name: str = self.agent_name or "UnnamedAgent"
            args: dict[str, Any] = {
                "model": run_options["model"],
                "name": agent_name,
                "description": self.agent_description,
            }
            if "tools" in run_options:
                args["tools"] = run_options["tools"]
            if "tool_resources" in run_options:
                args["tool_resources"] = run_options["tool_resources"]
            if "instructions" in run_options:
                args["instructions"] = run_options["instructions"]
            if "response_format" in run_options:
                args["response_format"] = run_options["response_format"]

            if "temperature" in run_options:
                args["temperature"] = run_options["temperature"]
            if "top_p" in run_options:
                args["top_p"] = run_options["top_p"]

            created_agent = await self.agents_client.create_agent(**args)

            self.agent_id = str(created_agent.id)
            self._agent_definition = created_agent
            self._agent_created = True

        return self.agent_id

    async def _create_agent_stream(
        self,
        agent_id: str,
        run_options: dict[str, Any],
        required_action_results: list[FunctionResultContent | FunctionApprovalResponseContent] | None,
    ) -> tuple[AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any], str]:
        """Create the agent stream for processing.

        Returns:
            tuple: (stream, final_thread_id)
        """
        thread_id = run_options.pop("thread_id", None)

        # Get any active run for this thread
        thread_run = await self._get_active_thread_run(thread_id)

        stream: AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any]
        handler: AsyncAgentEventHandler[Any] = AsyncAgentEventHandler()
        tool_run_id, tool_outputs, tool_approvals = self._prepare_tool_outputs_for_azure_ai(required_action_results)

        if (
            thread_run is not None
            and tool_run_id is not None
            and tool_run_id == thread_run.id
            and (tool_outputs or tool_approvals)
        ):  # type: ignore[reportUnknownMemberType]
            # There's an active run and we have tool results to submit, so submit the results.
            args: dict[str, Any] = {
                "thread_id": thread_run.thread_id,
                "run_id": tool_run_id,
                "event_handler": handler,
            }
            if tool_outputs:
                args["tool_outputs"] = tool_outputs
            if tool_approvals:
                args["tool_approvals"] = tool_approvals
            await self.agents_client.runs.submit_tool_outputs_stream(**args)  # type: ignore[reportUnknownMemberType]
            # Pass the handler to the stream to continue processing
            stream = handler  # type: ignore
            final_thread_id = thread_run.thread_id
        else:
            # Handle thread creation or cancellation
            final_thread_id = await self._prepare_thread(thread_id, thread_run, run_options)

            # Now create a new run and stream the results.
            run_options.pop("conversation_id", None)
            stream = await self.agents_client.runs.stream(  # type: ignore[reportUnknownMemberType]
                final_thread_id, agent_id=agent_id, **run_options
            )

        return stream, final_thread_id

    async def _get_active_thread_run(self, thread_id: str | None) -> ThreadRun | None:
        """Get any active run for the given thread."""
        if thread_id is None:
            return None

        async for run in self.agents_client.runs.list(thread_id=thread_id, limit=1, order=ListSortOrder.DESCENDING):  # type: ignore[reportUnknownMemberType]
            if run.status not in [
                RunStatus.COMPLETED,
                RunStatus.CANCELLED,
                RunStatus.FAILED,
                RunStatus.EXPIRED,
            ]:
                return run
        return None

    async def _prepare_thread(
        self, thread_id: str | None, thread_run: ThreadRun | None, run_options: dict[str, Any]
    ) -> str:
        """Prepare the thread for a new run, creating or cleaning up as needed."""
        if thread_id is not None:
            if thread_run is not None:
                # There was an active run; we need to cancel it before starting a new run.
                await self.agents_client.runs.cancel(thread_id, thread_run.id)

            return thread_id

        # No thread ID was provided, so create a new thread.
        thread = await self.agents_client.threads.create(
            tool_resources=run_options.get("tool_resources"),
            metadata=run_options.get("metadata"),
            messages=run_options.get("additional_messages"),
        )
        return thread.id

    def _extract_url_citations(
        self, message_delta_chunk: MessageDeltaChunk, azure_search_tool_calls: list[dict[str, Any]]
    ) -> list[CitationAnnotation]:
        """Extract URL citations from MessageDeltaChunk."""
        url_citations: list[CitationAnnotation] = []

        # Process each content item in the delta to find citations
        for content in message_delta_chunk.delta.content:
            if isinstance(content, MessageDeltaTextContent) and content.text and content.text.annotations:
                for annotation in content.text.annotations:
                    if isinstance(annotation, MessageDeltaTextUrlCitationAnnotation):
                        # Create annotated regions only if both start and end indices are available
                        annotated_regions = []
                        if annotation.start_index and annotation.end_index:
                            annotated_regions = [
                                TextSpanRegion(
                                    start_index=annotation.start_index,
                                    end_index=annotation.end_index,
                                )
                            ]

                        # Extract real URL from Azure AI Search tool calls
                        real_url = self._get_real_url_from_citation_reference(
                            annotation.url_citation.url, azure_search_tool_calls
                        )

                        # Create CitationAnnotation with real URL
                        citation = CitationAnnotation(
                            title=getattr(annotation.url_citation, "title", None),
                            url=real_url,
                            snippet=None,
                            annotated_regions=annotated_regions,
                            raw_representation=annotation,
                        )
                        url_citations.append(citation)

        return url_citations

    def _extract_file_path_contents(self, message_delta_chunk: MessageDeltaChunk) -> list[HostedFileContent]:
        """Extract file references from MessageDeltaChunk annotations.

        Code interpreter generates files that are referenced via file path or file citation
        annotations in the message content. This method extracts those file IDs and returns
        them as HostedFileContent objects.

        Handles two annotation types:
        - MessageDeltaTextFilePathAnnotation: Contains file_path.file_id
        - MessageDeltaTextFileCitationAnnotation: Contains file_citation.file_id

        Args:
            message_delta_chunk: The message delta chunk to process

        Returns:
            List of HostedFileContent objects for any files referenced in annotations
        """
        file_contents: list[HostedFileContent] = []

        for content in message_delta_chunk.delta.content:
            if isinstance(content, MessageDeltaTextContent) and content.text and content.text.annotations:
                for annotation in content.text.annotations:
                    if isinstance(annotation, MessageDeltaTextFilePathAnnotation):
                        # Extract file_id from the file_path annotation
                        file_path = getattr(annotation, "file_path", None)
                        if file_path is not None:
                            file_id = getattr(file_path, "file_id", None)
                            if file_id:
                                file_contents.append(HostedFileContent(file_id=file_id))
                    elif isinstance(annotation, MessageDeltaTextFileCitationAnnotation):
                        # Extract file_id from the file_citation annotation
                        file_citation = getattr(annotation, "file_citation", None)
                        if file_citation is not None:
                            file_id = getattr(file_citation, "file_id", None)
                            if file_id:
                                file_contents.append(HostedFileContent(file_id=file_id))

        return file_contents

    def _get_real_url_from_citation_reference(
        self, citation_url: str, azure_search_tool_calls: list[dict[str, Any]]
    ) -> str:
        """Extract real URL from Azure AI Search tool calls based on citation reference.

        Args:
            citation_url: Citation reference URL (e.g., "doc_0", "#doc_1", or full URL with doc_N)
            azure_search_tool_calls: List of captured Azure AI Search tool calls

        Returns:
            Real document URL if found, otherwise original citation_url
        """
        # Extract document index from citation URL (e.g., "doc_0" -> 0)
        match = re.search(r"doc_(\d+)", citation_url)
        if not match:
            return citation_url

        doc_index = int(match.group(1))

        # Get Azure AI Search tool calls
        if not azure_search_tool_calls:
            return citation_url

        try:
            # Extract URLs from the most recent Azure AI Search tool call
            tool_call = azure_search_tool_calls[-1]  # Most recent call
            output_str = tool_call["azure_ai_search"]["output"]

            # Parse the tool call output to get URLs
            output_data = ast.literal_eval(output_str)
            all_urls = output_data["metadata"]["get_urls"]

            # Return the URL at the specified index, if it exists
            if 0 <= doc_index < len(all_urls):
                return str(all_urls[doc_index])

        except (KeyError, IndexError, TypeError, ValueError, SyntaxError) as ex:
            logger.debug(f"Failed to extract real URL for {citation_url}: {ex}")

        return citation_url

    async def _process_stream(
        self, stream: AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any], thread_id: str
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Process events from the stream iterator and yield ChatResponseUpdate objects."""
        response_id: str | None = None
        # Track Azure Search tool calls for this stream only
        azure_search_tool_calls: list[dict[str, Any]] = []
        response_stream = await stream.__aenter__() if isinstance(stream, AsyncAgentRunStream) else stream  # type: ignore[no-untyped-call]
        try:
            async for event_type, event_data, _ in response_stream:  # type: ignore
                match event_data:
                    case MessageDeltaChunk():
                        # only one event_type: AgentStreamEvent.THREAD_MESSAGE_DELTA
                        role = Role.USER if event_data.delta.role == MessageRole.USER else Role.ASSISTANT

                        # Extract URL citations from the delta chunk
                        url_citations = self._extract_url_citations(event_data, azure_search_tool_calls)

                        # Extract file path contents from code interpreter outputs
                        file_contents = self._extract_file_path_contents(event_data)

                        # Create contents with citations if any exist
                        citation_content: list[Contents] = []
                        if event_data.text or url_citations:
                            text_content_obj = TextContent(text=event_data.text or "")
                            if url_citations:
                                text_content_obj.annotations = url_citations
                            citation_content.append(text_content_obj)

                        # Add file contents from file path annotations
                        citation_content.extend(file_contents)

                        yield ChatResponseUpdate(
                            role=role,
                            contents=citation_content if citation_content else None,
                            conversation_id=thread_id,
                            message_id=response_id,
                            raw_representation=event_data,
                            response_id=response_id,
                        )
                    case ThreadRun():
                        # possible event_types:
                        # AgentStreamEvent.THREAD_RUN_CREATED
                        # AgentStreamEvent.THREAD_RUN_QUEUED
                        # AgentStreamEvent.THREAD_RUN_INCOMPLETE
                        # AgentStreamEvent.THREAD_RUN_IN_PROGRESS
                        # AgentStreamEvent.THREAD_RUN_REQUIRES_ACTION
                        # AgentStreamEvent.THREAD_RUN_COMPLETED
                        # AgentStreamEvent.THREAD_RUN_FAILED
                        # AgentStreamEvent.THREAD_RUN_CANCELLING
                        # AgentStreamEvent.THREAD_RUN_CANCELLED
                        # AgentStreamEvent.THREAD_RUN_EXPIRED
                        match event_type:
                            case AgentStreamEvent.THREAD_RUN_REQUIRES_ACTION:
                                if event_data.required_action and event_data.required_action.type in [
                                    "submit_tool_outputs",
                                    "submit_tool_approval",
                                ]:
                                    function_call_contents = self._parse_function_calls_from_azure_ai(
                                        event_data, response_id
                                    )
                                    if function_call_contents:
                                        yield ChatResponseUpdate(
                                            role=Role.ASSISTANT,
                                            contents=function_call_contents,
                                            conversation_id=thread_id,
                                            message_id=response_id,
                                            raw_representation=event_data,
                                            response_id=response_id,
                                        )
                            case AgentStreamEvent.THREAD_RUN_FAILED:
                                raise ServiceResponseException(event_data.last_error.message)
                            case _:
                                yield ChatResponseUpdate(
                                    contents=[],
                                    conversation_id=event_data.thread_id,
                                    message_id=response_id,
                                    raw_representation=event_data,
                                    response_id=response_id,
                                    role=Role.ASSISTANT,
                                    model_id=event_data.model,
                                )

                    case RunStep():
                        # possible event_types:
                        # AgentStreamEvent.THREAD_RUN_STEP_CREATED,
                        # AgentStreamEvent.THREAD_RUN_STEP_IN_PROGRESS,
                        # AgentStreamEvent.THREAD_RUN_STEP_COMPLETED,
                        # AgentStreamEvent.THREAD_RUN_STEP_FAILED,
                        # AgentStreamEvent.THREAD_RUN_STEP_CANCELLED,
                        # AgentStreamEvent.THREAD_RUN_STEP_EXPIRED,
                        match event_type:
                            case AgentStreamEvent.THREAD_RUN_STEP_CREATED:
                                response_id = event_data.run_id
                            case AgentStreamEvent.THREAD_RUN_COMPLETED | AgentStreamEvent.THREAD_RUN_STEP_COMPLETED:
                                # Capture Azure AI Search tool calls when steps complete
                                if event_type == AgentStreamEvent.THREAD_RUN_STEP_COMPLETED:
                                    self._capture_azure_search_tool_calls(event_data, azure_search_tool_calls)

                                if event_data.usage:
                                    usage_content = UsageContent(
                                        UsageDetails(
                                            input_token_count=event_data.usage.prompt_tokens,
                                            output_token_count=event_data.usage.completion_tokens,
                                            total_token_count=event_data.usage.total_tokens,
                                        )
                                    )
                                    yield ChatResponseUpdate(
                                        role=Role.ASSISTANT,
                                        contents=[usage_content],
                                        conversation_id=thread_id,
                                        message_id=response_id,
                                        raw_representation=event_data,
                                        response_id=response_id,
                                    )
                            case _:
                                yield ChatResponseUpdate(
                                    contents=[],
                                    conversation_id=thread_id,
                                    message_id=response_id,
                                    raw_representation=event_data,
                                    response_id=response_id,
                                    role=Role.ASSISTANT,
                                )
                    case RunStepDeltaChunk():  # type: ignore
                        if (
                            event_data.delta.step_details is not None
                            and event_data.delta.step_details.type == "tool_calls"
                            and event_data.delta.step_details.tool_calls is not None  # type: ignore[attr-defined]
                        ):
                            for tool_call in event_data.delta.step_details.tool_calls:  # type: ignore[attr-defined]
                                if tool_call.type == "code_interpreter" and isinstance(
                                    tool_call.code_interpreter,
                                    RunStepDeltaCodeInterpreterDetailItemObject,
                                ):
                                    code_contents: list[Contents] = []
                                    if tool_call.code_interpreter.input is not None:
                                        logger.debug(f"Code Interpreter Input: {tool_call.code_interpreter.input}")
                                    if tool_call.code_interpreter.outputs is not None:
                                        for output in tool_call.code_interpreter.outputs:
                                            if isinstance(output, RunStepDeltaCodeInterpreterLogOutput) and output.logs:
                                                code_contents.append(TextContent(text=output.logs))
                                            if (
                                                isinstance(output, RunStepDeltaCodeInterpreterImageOutput)
                                                and output.image is not None
                                                and output.image.file_id is not None
                                            ):
                                                code_contents.append(HostedFileContent(file_id=output.image.file_id))
                                    yield ChatResponseUpdate(
                                        role=Role.ASSISTANT,
                                        contents=code_contents,
                                        conversation_id=thread_id,
                                        message_id=response_id,
                                        raw_representation=tool_call.code_interpreter,
                                        response_id=response_id,
                                    )
                    case _:  # ThreadMessage or string
                        # possible event_types for ThreadMessage:
                        # AgentStreamEvent.THREAD_MESSAGE_CREATED
                        # AgentStreamEvent.THREAD_MESSAGE_IN_PROGRESS
                        # AgentStreamEvent.THREAD_MESSAGE_COMPLETED
                        # AgentStreamEvent.THREAD_MESSAGE_INCOMPLETE
                        yield ChatResponseUpdate(
                            contents=[],
                            conversation_id=thread_id,
                            message_id=response_id,
                            raw_representation=event_data,  # type: ignore
                            response_id=response_id,
                            role=Role.ASSISTANT,
                        )
        except Exception as ex:
            logger.error(f"Error processing stream: {ex}")
            raise
        finally:
            if isinstance(stream, AsyncAgentRunStream):
                await stream.__aexit__(None, None, None)  # type: ignore[no-untyped-call]

    def _capture_azure_search_tool_calls(
        self, step_data: RunStep, azure_search_tool_calls: list[dict[str, Any]]
    ) -> None:
        """Capture Azure AI Search tool call data from completed steps."""
        try:
            if (
                hasattr(step_data, "step_details")
                and hasattr(step_data.step_details, "tool_calls")
                and step_data.step_details.tool_calls
            ):
                for tool_call in step_data.step_details.tool_calls:
                    if hasattr(tool_call, "type") and tool_call.type == "azure_ai_search":
                        # Store the complete tool call as a dictionary
                        tool_call_dict = {
                            "id": getattr(tool_call, "id", None),
                            "type": tool_call.type,
                            "azure_ai_search": getattr(tool_call, "azure_ai_search", None),
                        }
                        azure_search_tool_calls.append(tool_call_dict)
                        logger.debug(f"Captured Azure AI Search tool call: {tool_call_dict['id']}")
        except Exception as ex:
            logger.debug(f"Failed to capture Azure AI Search tool call: {ex}")

    def _parse_function_calls_from_azure_ai(self, event_data: ThreadRun, response_id: str | None) -> list[Contents]:
        """Parse function call contents from an Azure AI tool action event."""
        if isinstance(event_data, ThreadRun) and event_data.required_action is not None:
            if isinstance(event_data.required_action, SubmitToolOutputsAction):
                return [
                    FunctionCallContent(
                        call_id=f'["{response_id}", "{tool.id}"]',
                        name=tool.function.name,
                        arguments=tool.function.arguments,
                    )
                    for tool in event_data.required_action.submit_tool_outputs.tool_calls
                    if isinstance(tool, RequiredFunctionToolCall)
                ]
            if isinstance(event_data.required_action, SubmitToolApprovalAction):
                return [
                    FunctionApprovalRequestContent(
                        id=f'["{response_id}", "{tool.id}"]',
                        function_call=FunctionCallContent(
                            call_id=f'["{response_id}", "{tool.id}"]',
                            name=tool.name,
                            arguments=tool.arguments,
                            raw_representation=tool,
                        ),
                        raw_representation=tool,
                    )
                    for tool in event_data.required_action.submit_tool_approval.tool_calls
                    if isinstance(tool, RequiredMcpToolCall)
                ]
        return []

    async def _close_client_if_needed(self) -> None:
        """Close agents_client session if we created it."""
        if self._should_close_client:
            await self.agents_client.close()

    async def _cleanup_agent_if_needed(self) -> None:
        """Clean up the agent if we created it."""
        if self._agent_created and self.should_cleanup_agent and self.agent_id is not None:
            await self.agents_client.delete_agent(self.agent_id)
            self.agent_id = None
            self._agent_created = False

    async def _load_agent_definition_if_needed(self) -> Agent | None:
        """Load and cache agent details if not already loaded."""
        if self._agent_definition is None and self.agent_id is not None:
            self._agent_definition = await self.agents_client.get_agent(self.agent_id)
        return self._agent_definition

    def _prepare_tool_choice(self, chat_options: ChatOptions) -> None:
        """Prepare the tools and tool choice for the chat options.

        Args:
            chat_options: The chat options to prepare.
        """
        chat_tool_mode = chat_options.tool_choice
        if chat_tool_mode is None or chat_tool_mode == ToolMode.NONE or chat_tool_mode == "none":
            chat_options.tools = None
            chat_options.tool_choice = ToolMode.NONE
            return

        chat_options.tool_choice = chat_tool_mode

    async def _prepare_options(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], list[FunctionResultContent | FunctionApprovalResponseContent] | None]:
        agent_definition = await self._load_agent_definition_if_needed()

        # Use to_dict with exclusions for properties handled separately
        run_options: dict[str, Any] = chat_options.to_dict(
            exclude={
                "type",
                "instructions",  # handled via messages
                "tools",  # handled separately
                "tool_choice",  # handled separately
                "response_format",  # handled separately
                "additional_properties",  # handled separately
                "frequency_penalty",  # not supported
                "presence_penalty",  # not supported
                "user",  # not supported
                "stop",  # not supported
                "logit_bias",  # not supported
                "seed",  # not supported
                "store",  # not supported
            }
        )

        # Translation between ChatOptions and Azure AI Agents API
        translations = {
            "model_id": "model",
            "allow_multiple_tool_calls": "parallel_tool_calls",
            "max_tokens": "max_completion_tokens",
        }
        for old_key, new_key in translations.items():
            if old_key in run_options and old_key != new_key:
                run_options[new_key] = run_options.pop(old_key)

        # model id fallback
        if not run_options.get("model"):
            run_options["model"] = self.model_id

        # tools and tool_choice
        if tool_definitions := await self._prepare_tool_definitions_and_resources(
            chat_options, agent_definition, run_options
        ):
            run_options["tools"] = tool_definitions

        if tool_choice := self._prepare_tool_choice_mode(chat_options):
            run_options["tool_choice"] = tool_choice

        # response format
        if chat_options.response_format is not None:
            run_options["response_format"] = ResponseFormatJsonSchemaType(
                json_schema=ResponseFormatJsonSchema(
                    name=chat_options.response_format.__name__,
                    schema=chat_options.response_format.model_json_schema(),
                )
            )

        # messages
        additional_messages, instructions, required_action_results = self._prepare_messages(messages)
        if additional_messages:
            run_options["additional_messages"] = additional_messages

        # Add instruction from existing agent at the beginning
        if (
            agent_definition is not None
            and agent_definition.instructions
            and agent_definition.instructions not in instructions
        ):
            instructions.insert(0, agent_definition.instructions)

        if instructions:
            run_options["instructions"] = "\n".join(instructions)

        # thread_id resolution (conversation_id takes precedence, then kwargs, then instance default)
        run_options["thread_id"] = chat_options.conversation_id or kwargs.get("conversation_id") or self.thread_id

        return run_options, required_action_results

    def _prepare_tool_choice_mode(
        self, chat_options: ChatOptions
    ) -> AgentsToolChoiceOptionMode | AgentsNamedToolChoice | None:
        """Prepare the tool choice mode for Azure AI Agents API."""
        if chat_options.tool_choice is None:
            return None
        if chat_options.tool_choice == "none":
            return AgentsToolChoiceOptionMode.NONE
        if chat_options.tool_choice == "auto":
            return AgentsToolChoiceOptionMode.AUTO
        if (
            isinstance(chat_options.tool_choice, ToolMode)
            and chat_options.tool_choice == "required"
            and chat_options.tool_choice.required_function_name is not None
        ):
            return AgentsNamedToolChoice(
                type=AgentsNamedToolChoiceType.FUNCTION,
                function=FunctionName(name=chat_options.tool_choice.required_function_name),
            )
        return None

    async def _prepare_tool_definitions_and_resources(
        self,
        chat_options: ChatOptions,
        agent_definition: Agent | None,
        run_options: dict[str, Any],
    ) -> list[ToolDefinition | dict[str, Any]]:
        """Prepare tool definitions and resources for the run options."""
        tool_definitions: list[ToolDefinition | dict[str, Any]] = []

        # Add tools from existing agent (exclude function tools - passed via chat_options.tools)
        if agent_definition is not None:
            agent_tools = [tool for tool in agent_definition.tools if not isinstance(tool, FunctionToolDefinition)]
            if agent_tools:
                tool_definitions.extend(agent_tools)
            if agent_definition.tool_resources:
                run_options["tool_resources"] = agent_definition.tool_resources

        # Add run tools if tool_choice allows
        if chat_options.tool_choice is not None and chat_options.tool_choice != "none" and chat_options.tools:
            tool_definitions.extend(await self._prepare_tools_for_azure_ai(chat_options.tools, run_options))

            # Handle MCP tool resources
            mcp_resources = self._prepare_mcp_resources(chat_options.tools)
            if mcp_resources:
                if "tool_resources" not in run_options:
                    run_options["tool_resources"] = {}
                run_options["tool_resources"]["mcp"] = mcp_resources

        return tool_definitions

    def _prepare_mcp_resources(
        self, tools: Sequence["ToolProtocol | MutableMapping[str, Any]"]
    ) -> list[dict[str, Any]]:
        """Prepare MCP tool resources for approval mode configuration."""
        mcp_tools = [tool for tool in tools if isinstance(tool, HostedMCPTool)]
        if not mcp_tools:
            return []

        mcp_resources: list[dict[str, Any]] = []
        for mcp_tool in mcp_tools:
            server_label = mcp_tool.name.replace(" ", "_")
            mcp_resource: dict[str, Any] = {"server_label": server_label}

            if mcp_tool.headers:
                mcp_resource["headers"] = mcp_tool.headers

            if mcp_tool.approval_mode is not None:
                match mcp_tool.approval_mode:
                    case str():
                        # Map agent framework approval modes to Azure AI approval modes
                        approval_mode = "always" if mcp_tool.approval_mode == "always_require" else "never"
                        mcp_resource["require_approval"] = approval_mode
                    case _:
                        if "always_require_approval" in mcp_tool.approval_mode:
                            mcp_resource["require_approval"] = {
                                "always": mcp_tool.approval_mode["always_require_approval"]
                            }
                        elif "never_require_approval" in mcp_tool.approval_mode:
                            mcp_resource["require_approval"] = {
                                "never": mcp_tool.approval_mode["never_require_approval"]
                            }

            mcp_resources.append(mcp_resource)

        return mcp_resources

    def _prepare_messages(
        self, messages: MutableSequence[ChatMessage]
    ) -> tuple[
        list[ThreadMessageOptions] | None,
        list[str],
        list[FunctionResultContent | FunctionApprovalResponseContent] | None,
    ]:
        """Prepare messages for Azure AI Agents API.

        System/developer messages are turned into instructions, since there is no such message roles in Azure AI.
        All other messages are added 1:1, treating assistant messages as agent messages
        and everything else as user messages.

        Returns:
            Tuple of (additional_messages, instructions, required_action_results)
        """
        instructions: list[str] = []
        required_action_results: list[FunctionResultContent | FunctionApprovalResponseContent] | None = None
        additional_messages: list[ThreadMessageOptions] | None = None

        for chat_message in messages:
            if chat_message.role.value in ["system", "developer"]:
                for text_content in [content for content in chat_message.contents if isinstance(content, TextContent)]:
                    instructions.append(text_content.text)
                continue

            message_contents: list[MessageInputContentBlock] = []

            for content in chat_message.contents:
                if isinstance(content, TextContent):
                    message_contents.append(MessageInputTextBlock(text=content.text))
                elif isinstance(content, (DataContent, UriContent)) and content.has_top_level_media_type("image"):
                    message_contents.append(MessageInputImageUrlBlock(image_url=MessageImageUrlParam(url=content.uri)))
                elif isinstance(content, (FunctionResultContent, FunctionApprovalResponseContent)):
                    if required_action_results is None:
                        required_action_results = []
                    required_action_results.append(content)
                elif isinstance(content.raw_representation, MessageInputContentBlock):
                    message_contents.append(content.raw_representation)

            if message_contents:
                if additional_messages is None:
                    additional_messages = []
                additional_messages.append(
                    ThreadMessageOptions(
                        role=MessageRole.AGENT if chat_message.role == Role.ASSISTANT else MessageRole.USER,
                        content=message_contents,
                    )
                )

        return additional_messages, instructions, required_action_results

    async def _prepare_tools_for_azure_ai(
        self, tools: Sequence["ToolProtocol | MutableMapping[str, Any]"], run_options: dict[str, Any] | None = None
    ) -> list[ToolDefinition | dict[str, Any]]:
        """Prepare tool definitions for the Azure AI Agents API."""
        tool_definitions: list[ToolDefinition | dict[str, Any]] = []
        for tool in tools:
            match tool:
                case AIFunction():
                    tool_definitions.append(tool.to_json_schema_spec())  # type: ignore[reportUnknownArgumentType]
                case HostedWebSearchTool():
                    additional_props = tool.additional_properties or {}
                    config_args: dict[str, Any] = {}
                    if count := additional_props.get("count"):
                        config_args["count"] = count
                    if freshness := additional_props.get("freshness"):
                        config_args["freshness"] = freshness
                    if market := additional_props.get("market"):
                        config_args["market"] = market
                    if set_lang := additional_props.get("set_lang"):
                        config_args["set_lang"] = set_lang
                    # Bing Grounding
                    connection_id = additional_props.get("connection_id") or os.getenv("BING_CONNECTION_ID")
                    # Custom Bing Search
                    custom_connection_id = additional_props.get("custom_connection_id") or os.getenv(
                        "BING_CUSTOM_CONNECTION_ID"
                    )
                    custom_instance_name = additional_props.get("custom_instance_name") or os.getenv(
                        "BING_CUSTOM_INSTANCE_NAME"
                    )
                    bing_search: BingGroundingTool | BingCustomSearchTool | None = None
                    if (connection_id) and not custom_connection_id and not custom_instance_name:
                        if connection_id:
                            conn_id = connection_id
                        else:
                            raise ServiceInitializationError("Parameter connection_id is not provided.")
                        bing_search = BingGroundingTool(connection_id=conn_id, **config_args)
                    if custom_connection_id and custom_instance_name:
                        bing_search = BingCustomSearchTool(
                            connection_id=custom_connection_id,
                            instance_name=custom_instance_name,
                            **config_args,
                        )
                    if not bing_search:
                        raise ServiceInitializationError(
                            "Bing search tool requires either 'connection_id' for Bing Grounding "
                            "or both 'custom_connection_id' and 'custom_instance_name' for Custom Bing Search. "
                            "These can be provided via additional_properties or environment variables: "
                            "'BING_CONNECTION_ID', 'BING_CUSTOM_CONNECTION_ID', "
                            "'BING_CUSTOM_INSTANCE_NAME'"
                        )
                    tool_definitions.extend(bing_search.definitions)
                case HostedCodeInterpreterTool():
                    tool_definitions.append(CodeInterpreterToolDefinition())
                case HostedMCPTool():
                    mcp_tool = McpTool(
                        server_label=tool.name.replace(" ", "_"),
                        server_url=str(tool.url),
                        allowed_tools=list(tool.allowed_tools) if tool.allowed_tools else [],
                    )
                    tool_definitions.extend(mcp_tool.definitions)
                case HostedFileSearchTool():
                    vector_stores = [inp for inp in tool.inputs or [] if isinstance(inp, HostedVectorStoreContent)]
                    if vector_stores:
                        file_search = FileSearchTool(vector_store_ids=[vs.vector_store_id for vs in vector_stores])
                        tool_definitions.extend(file_search.definitions)
                        # Set tool_resources for file search to work properly with Azure AI
                        if run_options is not None and "tool_resources" not in run_options:
                            run_options["tool_resources"] = file_search.resources
                case ToolDefinition():
                    tool_definitions.append(tool)
                case dict():
                    tool_definitions.append(tool)
                case _:
                    raise ServiceInitializationError(f"Unsupported tool type: {type(tool)}")
        return tool_definitions

    def _prepare_tool_outputs_for_azure_ai(
        self,
        required_action_results: list[FunctionResultContent | FunctionApprovalResponseContent] | None,
    ) -> tuple[str | None, list[ToolOutput] | None, list[ToolApproval] | None]:
        """Prepare function results and approvals for submission to the Azure AI API."""
        run_id: str | None = None
        tool_outputs: list[ToolOutput] | None = None
        tool_approvals: list[ToolApproval] | None = None

        if required_action_results:
            for content in required_action_results:
                # When creating the FunctionCallContent/ApprovalRequestContent,
                # we created it with a CallId == [runId, callId].
                # We need to extract the run ID and ensure that the Output/Approval we send back to Azure
                # is only the call ID.
                run_and_call_ids: list[str] = (
                    json.loads(content.call_id)
                    if isinstance(content, FunctionResultContent)
                    else json.loads(content.id)
                )

                if (
                    not run_and_call_ids
                    or len(run_and_call_ids) != 2
                    or not run_and_call_ids[0]
                    or not run_and_call_ids[1]
                    or (run_id is not None and run_id != run_and_call_ids[0])
                ):
                    continue

                run_id = run_and_call_ids[0]
                call_id = run_and_call_ids[1]

                if isinstance(content, FunctionResultContent):
                    if tool_outputs is None:
                        tool_outputs = []
                    tool_outputs.append(
                        ToolOutput(tool_call_id=call_id, output=prepare_function_call_results(content.result))
                    )
                elif isinstance(content, FunctionApprovalResponseContent):
                    if tool_approvals is None:
                        tool_approvals = []
                    tool_approvals.append(ToolApproval(tool_call_id=call_id, approve=content.approved))

        return run_id, tool_outputs, tool_approvals

    def _update_agent_name_and_description(self, agent_name: str | None, description: str | None) -> None:
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

    def service_url(self) -> str:
        """Get the service URL for the chat client.

        Returns:
            The service URL for the chat client, or None if not set.
        """
        return self.agents_client._config.endpoint  # type: ignore
