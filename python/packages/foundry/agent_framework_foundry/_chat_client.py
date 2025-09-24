# Copyright (c) Microsoft. All rights reserved.

import json
import os
import sys
from collections.abc import AsyncIterable, MutableMapping, MutableSequence
from typing import Any, ClassVar, TypeVar

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    AIFunction,
    BaseChatClient,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatToolMode,
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
    ToolProtocol,
    UriContent,
    UsageContent,
    UsageDetails,
    get_logger,
    use_function_invocation,
)
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError, ServiceResponseException
from agent_framework.observability import use_observability
from azure.ai.agents.models import (
    AgentsNamedToolChoice,
    AgentsNamedToolChoiceType,
    AgentsToolChoiceOptionMode,
    AgentStreamEvent,
    AsyncAgentEventHandler,
    AsyncAgentRunStream,
    AzureAISearchQueryType,
    AzureAISearchTool,
    BingCustomSearchTool,
    BingGroundingTool,
    CodeInterpreterToolDefinition,
    FileSearchTool,
    FunctionName,
    FunctionToolOutput,
    ListSortOrder,
    McpTool,
    MessageDeltaChunk,
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
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import ConnectionType
from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import HttpResponseError
from pydantic import BaseModel, Field, PrivateAttr, ValidationError

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


logger = get_logger("agent_framework.foundry")


class FoundrySettings(AFBaseSettings):
    """Foundry model settings.

    The settings are first loaded from environment variables with the prefix 'FOUNDRY_'.
    If the environment variables are not found, the settings can be loaded from a .env file
    with the encoding 'utf-8'. If the settings are not found in the .env file, the settings
    are ignored; however, validation will fail alerting that the settings are missing.

    Attributes:
        project_endpoint: The Azure AI Foundry project endpoint URL.
            (Env var FOUNDRY_PROJECT_ENDPOINT)
        model_deployment_name: The name of the model deployment to use.
            (Env var FOUNDRY_MODEL_DEPLOYMENT_NAME)
        agent_name: Default name for automatically created agents.
            (Env var FOUNDRY_AGENT_NAME)
    Parameters:
        env_file_path: If provided, the .env settings are read from this file path location.
        env_file_encoding: The encoding of the .env file, defaults to 'utf-8'.
    """

    env_prefix: ClassVar[str] = "FOUNDRY_"

    project_endpoint: str | None = None
    model_deployment_name: str | None = None
    agent_name: str | None = "UnnamedAgent"


TFoundryChatClient = TypeVar("TFoundryChatClient", bound="FoundryChatClient")


@use_function_invocation
@use_observability
class FoundryChatClient(BaseChatClient):
    """Azure AI Foundry Chat client."""

    OTEL_PROVIDER_NAME: ClassVar[str] = "azure.ai.foundry"  # type: ignore[reportIncompatibleVariableOverride, misc]
    client: AIProjectClient = Field(...)
    credential: AsyncTokenCredential | None = Field(...)
    agent_id: str | None = Field(default=None)
    agent_name: str | None = Field(default=None)
    ai_model_id: str | None = Field(default=None)
    thread_id: str | None = Field(default=None)
    _should_delete_agent: bool = PrivateAttr(default=False)  # Track whether we should delete the agent
    _should_close_client: bool = PrivateAttr(default=False)  # Track whether we should close client connection

    def __init__(
        self,
        *,
        client: AIProjectClient | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        thread_id: str | None = None,
        project_endpoint: str | None = None,
        model_deployment_name: str | None = None,
        async_credential: AsyncTokenCredential | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a FoundryChatClient.

        Args:
            client: An existing AIProjectClient to use. If not provided, one will be created.
            agent_id: The ID of an existing agent to use. If not provided and client is provided,
                a new agent will be created (and deleted after the request). If neither client
                nor agent_id is provided, both will be created and managed automatically.
            agent_name: The name to use when creating new agents.
            thread_id: Default thread ID to use for conversations. Can be overridden by
                conversation_id property, when making a request.
            project_endpoint: The Azure AI Foundry project endpoint URL. Used if client is not provided.
            model_deployment_name: The model deployment name to use for agent creation.
            async_credential: Azure async credential to use for authentication.
            setup_tracing: Whether to setup tracing for the client. Defaults to True.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
            **kwargs: Additional keyword arguments passed to the parent class.
        """
        try:
            foundry_settings = FoundrySettings(
                project_endpoint=project_endpoint,
                model_deployment_name=model_deployment_name,
                agent_name=agent_name,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create Foundry settings.", ex) from ex

        # If no client is provided, create one
        should_close_client = False
        if client is None:
            if not foundry_settings.project_endpoint:
                raise ServiceInitializationError(
                    "Foundry project endpoint is required. Set via 'project_endpoint' parameter "
                    "or 'FOUNDRY_PROJECT_ENDPOINT' environment variable."
                )

            if agent_id is None and not foundry_settings.model_deployment_name:
                raise ServiceInitializationError(
                    "Foundry model deployment name is required. Set via 'model_deployment_name' parameter "
                    "or 'FOUNDRY_MODEL_DEPLOYMENT_NAME' environment variable."
                )

            # Use provided credential
            if not async_credential:
                raise ServiceInitializationError("Azure credential is required when client is not provided.")
            client = AIProjectClient(
                endpoint=foundry_settings.project_endpoint,
                credential=async_credential,
                user_agent=AGENT_FRAMEWORK_USER_AGENT,
            )
            should_close_client = True

        super().__init__(
            client=client,  # type: ignore[reportCallIssue]
            credential=async_credential,  # type: ignore[reportCallIssue]
            agent_id=agent_id,  # type: ignore[reportCallIssue]
            thread_id=thread_id,  # type: ignore[reportCallIssue]
            agent_name=foundry_settings.agent_name,  # type: ignore[reportCallIssue]
            ai_model_id=foundry_settings.model_deployment_name,  # type: ignore[reportCallIssue]
            **kwargs,
        )
        self._should_close_client = should_close_client

    async def setup_foundry_observability(self, enable_live_metrics: bool = False) -> None:
        """Call this method to setup tracing with Foundry.

        This will take the connection string from the project client.
        It will override any connection string that is set in the environment variables.
        It will disable any OTLP endpoint that might have been set.
        """
        from agent_framework.observability import setup_observability

        setup_observability(
            applicationinsights_connection_string=await self.client.telemetry.get_application_insights_connection_string(),  # noqa: E501
            enable_live_metrics=enable_live_metrics,
        )

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit - clean up any agents we created."""
        await self.close()

    async def close(self) -> None:
        """Close the client and clean up any agents we created."""
        await self._cleanup_agent_if_needed()
        await self._close_client_if_needed()

    @classmethod
    def from_dict(cls: type[TFoundryChatClient], settings: dict[str, Any]) -> TFoundryChatClient:
        """Initialize a FoundryChatClient from a dictionary of settings.

        Args:
            settings: A dictionary of settings for the service.
        """
        return cls(
            client=settings.get("client"),
            agent_id=settings.get("agent_id"),
            thread_id=settings.get("thread_id"),
            project_endpoint=settings.get("project_endpoint"),
            model_deployment_name=settings.get("model_deployment_name"),
            agent_name=settings.get("agent_name"),
            credential=settings.get("credential"),
            env_file_path=settings.get("env_file_path"),
        )

    async def _inner_get_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> ChatResponse:
        return await ChatResponse.from_chat_response_generator(
            updates=self._inner_get_streaming_response(messages=messages, chat_options=chat_options, **kwargs)
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions,
        **kwargs: Any,
    ) -> AsyncIterable[ChatResponseUpdate]:
        # Extract necessary state from messages and options
        run_options, required_action_results = await self._create_run_options(messages, chat_options, **kwargs)

        # Get the thread ID
        thread_id: str | None = (
            chat_options.conversation_id
            if chat_options.conversation_id is not None
            else run_options.get("conversation_id", self.thread_id)
        )

        if thread_id is None and required_action_results is not None:
            raise ValueError("No thread ID was provided, but chat messages includes tool results.")

        # Determine which agent to use and create if needed
        agent_id = await self._get_agent_id_or_create(run_options)

        # Process and yield each update from the stream
        async for update in self._process_stream(
            *(await self._create_agent_stream(thread_id, agent_id, run_options, required_action_results))
        ):
            yield update

    async def _get_agent_id_or_create(self, run_options: dict[str, Any] | None = None) -> str:
        """Determine which agent to use and create if needed.

        Returns:
            str: The agent_id to use
        """
        # If no agent_id is provided, create a temporary agent
        if self.agent_id is None:
            if not self.ai_model_id:
                raise ServiceInitializationError("Model deployment name is required for agent creation.")

            agent_name = self.agent_name
            args = {"model": self.ai_model_id, "name": agent_name}
            if run_options:
                if "tools" in run_options:
                    args["tools"] = run_options["tools"]
                if "instructions" in run_options:
                    args["instructions"] = run_options["instructions"]
                if "response_format" in run_options:
                    args["response_format"] = run_options["response_format"]
            created_agent = await self.client.agents.create_agent(**args)  # type: ignore[arg-type]
            self.agent_id = created_agent.id
            self._should_delete_agent = True

        return self.agent_id

    async def _create_agent_stream(
        self,
        thread_id: str | None,
        agent_id: str,
        run_options: dict[str, Any],
        required_action_results: list[FunctionResultContent | FunctionApprovalResponseContent] | None,
    ) -> tuple[AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any], str]:
        """Create the agent stream for processing.

        Returns:
            tuple: (stream, final_thread_id)
        """
        # Get any active run for this thread
        thread_run = await self._get_active_thread_run(thread_id)

        stream: AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any]
        handler: AsyncAgentEventHandler[Any] = AsyncAgentEventHandler()
        tool_run_id, tool_outputs, tool_approvals = self._convert_required_action_to_tool_output(
            required_action_results
        )

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
            await self.client.agents.runs.submit_tool_outputs_stream(**args)  # type: ignore[reportUnknownMemberType]
            # Pass the handler to the stream to continue processing
            stream = handler  # type: ignore
            final_thread_id = thread_run.thread_id
        else:
            # Handle thread creation or cancellation
            final_thread_id = await self._prepare_thread(thread_id, thread_run, run_options)

            # Now create a new run and stream the results.
            run_options.pop("conversation_id", None)
            stream = await self.client.agents.runs.stream(  # type: ignore[reportUnknownMemberType]
                final_thread_id, agent_id=agent_id, **run_options
            )

        return stream, final_thread_id

    async def _get_active_thread_run(self, thread_id: str | None) -> ThreadRun | None:
        """Get any active run for the given thread."""
        if thread_id is None:
            return None

        async for run in self.client.agents.runs.list(thread_id=thread_id, limit=1, order=ListSortOrder.DESCENDING):  # type: ignore[reportUnknownMemberType]
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
                await self.client.agents.runs.cancel(thread_id, thread_run.id)

            return thread_id

        # No thread ID was provided, so create a new thread.
        thread = await self.client.agents.threads.create(
            tool_resources=run_options.get("tool_resources"), metadata=run_options.get("metadata")
        )
        thread_id = thread.id
        # workaround for: https://github.com/Azure/azure-sdk-for-python/issues/42805
        # this occurs when otel is enabled
        # once fixed, in the function above, readd:
        # `messages=run_options.pop("additional_messages")`
        for msg in run_options.pop("additional_messages", []):
            await self.client.agents.messages.create(
                thread_id=thread_id, role=msg.role, content=msg.content, metadata=msg.metadata
            )
        # and remove until here.
        return thread_id

    async def _process_stream(
        self, stream: AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any], thread_id: str
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Process events from the stream iterator and yield ChatResponseUpdate objects."""
        response_id: str | None = None
        response_stream = await stream.__aenter__() if isinstance(stream, AsyncAgentRunStream) else stream  # type: ignore[no-untyped-call]
        try:
            async for event_type, event_data, _ in response_stream:  # type: ignore
                match event_data:
                    case MessageDeltaChunk():
                        # only one event_type: AgentStreamEvent.THREAD_MESSAGE_DELTA
                        role = Role.USER if event_data.delta.role == MessageRole.USER else Role.ASSISTANT
                        yield ChatResponseUpdate(
                            role=role,
                            text=event_data.text,
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
                                    contents = self._create_function_call_contents(event_data, response_id)
                                    if contents:
                                        yield ChatResponseUpdate(
                                            role=Role.ASSISTANT,
                                            contents=contents,
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
                                    ai_model_id=event_data.model,
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
                                    contents = []
                                    if tool_call.code_interpreter.input is not None:
                                        logger.debug(f"Code Interpreter Input: {tool_call.code_interpreter.input}")
                                    if tool_call.code_interpreter.outputs is not None:
                                        for output in tool_call.code_interpreter.outputs:
                                            if isinstance(output, RunStepDeltaCodeInterpreterLogOutput) and output.logs:
                                                contents.append(TextContent(text=output.logs))
                                            if (
                                                isinstance(output, RunStepDeltaCodeInterpreterImageOutput)
                                                and output.image is not None
                                                and output.image.file_id is not None
                                            ):
                                                contents.append(HostedFileContent(file_id=output.image.file_id))
                                    yield ChatResponseUpdate(
                                        role=Role.ASSISTANT,
                                        contents=contents,
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

    def _create_function_call_contents(self, event_data: ThreadRun, response_id: str | None) -> list[Contents]:
        """Create function call contents from a tool action event."""
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
        """Close client session if we created it."""
        if self._should_close_client:
            await self.client.close()

    async def _cleanup_agent_if_needed(self) -> None:
        """Clean up the agent if we created it."""
        if self._should_delete_agent and self.agent_id is not None:
            await self.client.agents.delete_agent(self.agent_id)
            self.agent_id = None
            self._should_delete_agent = False

    async def _create_run_options(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions | None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], list[FunctionResultContent | FunctionApprovalResponseContent] | None]:
        run_options: dict[str, Any] = {**kwargs}

        if chat_options is not None:
            run_options["max_completion_tokens"] = chat_options.max_tokens
            run_options["model"] = chat_options.ai_model_id
            run_options["top_p"] = chat_options.top_p
            run_options["temperature"] = chat_options.temperature
            run_options["parallel_tool_calls"] = chat_options.allow_multiple_tool_calls

            if chat_options.tool_choice is not None:
                if chat_options.tool_choice != "none" and chat_options.tools:
                    tool_definitions = await self._prep_tools(chat_options.tools)
                    if tool_definitions:
                        run_options["tools"] = tool_definitions

                if chat_options.tool_choice == "none":
                    run_options["tool_choice"] = AgentsToolChoiceOptionMode.NONE
                elif chat_options.tool_choice == "auto":
                    run_options["tool_choice"] = AgentsToolChoiceOptionMode.AUTO
                elif (
                    isinstance(chat_options.tool_choice, ChatToolMode)
                    and chat_options.tool_choice == "required"
                    and chat_options.tool_choice.required_function_name is not None
                ):
                    run_options["tool_choice"] = AgentsNamedToolChoice(
                        type=AgentsNamedToolChoiceType.FUNCTION,
                        function=FunctionName(name=chat_options.tool_choice.required_function_name),
                    )

            if chat_options.response_format is not None:
                run_options["response_format"] = ResponseFormatJsonSchemaType(
                    json_schema=ResponseFormatJsonSchema(
                        name=chat_options.response_format.__name__,
                        schema=chat_options.response_format.model_json_schema(),
                    )
                )

        instructions: list[str] = []
        required_action_results: list[FunctionResultContent | FunctionApprovalResponseContent] | None = None

        additional_messages: list[ThreadMessageOptions] | None = None

        # System/developer messages are turned into instructions, since there is no such message roles in Foundry.
        # All other messages are added 1:1, treating assistant messages as agent messages
        # and everything else as user messages.
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

            if len(message_contents) > 0:
                if additional_messages is None:
                    additional_messages = []
                additional_messages.append(
                    ThreadMessageOptions(
                        role=MessageRole.AGENT if chat_message.role == Role.ASSISTANT else MessageRole.USER,
                        content=message_contents,
                    )
                )

        if additional_messages is not None:
            run_options["additional_messages"] = additional_messages

        if len(instructions) > 0:
            run_options["instructions"] = "".join(instructions)

        return run_options, required_action_results

    async def _prep_tools(
        self, tools: list["ToolProtocol | MutableMapping[str, Any]"]
    ) -> list[ToolDefinition | dict[str, Any]]:
        """Prepare tool definitions for the run options."""
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
                    custom_connection_name = additional_props.get("custom_connection_name") or os.getenv(
                        "BING_CUSTOM_CONNECTION_NAME"
                    )
                    custom_configuration_name = additional_props.get("custom_instance_name") or os.getenv(
                        "BING_CUSTOM_INSTANCE_NAME"
                    )
                    bing_search: BingGroundingTool | BingCustomSearchTool | None = None
                    if connection_id and not custom_connection_name and not custom_configuration_name:
                        bing_search = BingGroundingTool(connection_id=connection_id, **config_args)
                    if custom_connection_name and custom_configuration_name:
                        try:
                            bing_custom_connection = await self.client.connections.get(name=custom_connection_name)
                        except HttpResponseError as err:
                            raise ServiceInitializationError(
                                f"Bing custom connection '{custom_connection_name}' not found in Foundry.", err
                            ) from err
                        else:
                            bing_search = BingCustomSearchTool(
                                connection_id=bing_custom_connection.id,
                                instance_name=custom_configuration_name,
                                **config_args,
                            )
                    if not bing_search:
                        raise ServiceInitializationError(
                            "Bing search tool requires either a 'connection_id' for Bing Grounding "
                            "or both 'custom_connection_name' and 'custom_instance_name' for Custom Bing Search. "
                            "These can be provided via the tool's additional_properties or environment variables: "
                            "'BING_CONNECTION_ID', 'BING_CUSTOM_CONNECTION_NAME', 'BING_CUSTOM_INSTANCE_NAME'"
                        )
                    tool_definitions.extend(bing_search.definitions)
                case HostedCodeInterpreterTool():
                    tool_definitions.append(CodeInterpreterToolDefinition())
                case HostedMCPTool():
                    tool_definitions.extend(
                        McpTool(
                            server_label=tool.name.replace(" ", "_"),
                            server_url=str(tool.url),
                            allowed_tools=list(tool.allowed_tools) if tool.allowed_tools else [],
                        ).definitions
                    )
                case HostedFileSearchTool():
                    vector_stores = [inp for inp in tool.inputs or [] if isinstance(inp, HostedVectorStoreContent)]
                    if vector_stores:
                        file_search = FileSearchTool(vector_store_ids=[vs.vector_store_id for vs in vector_stores])
                        tool_definitions.extend(file_search.definitions)
                    else:
                        additional_props = tool.additional_properties or {}
                        index_name = additional_props.get("index_name") or os.getenv("AZURE_AI_SEARCH_INDEX_NAME")
                        if not index_name:
                            raise ServiceInitializationError(
                                "File search tool requires at least one vector store input, for file search in Foundry "
                                "or an 'index_name' to use Azure AI Search, "
                                "in additional_properties or environment variable 'AZURE_AI_SEARCH_INDEX_NAME'."
                            )
                        try:
                            azs_conn_id = await self.client.connections.get_default(ConnectionType.AZURE_AI_SEARCH)
                        except HttpResponseError as err:
                            raise ServiceInitializationError(
                                "No default Azure AI Search connection found in Foundry. "
                                "Please create one or provide vector store inputs for the file search tool.",
                                err,
                            ) from err
                        else:
                            query_type_enum = AzureAISearchQueryType.SIMPLE
                            if query_type := additional_props.get("query_type"):
                                try:
                                    query_type_enum = AzureAISearchQueryType(query_type)
                                except ValueError as ex:
                                    raise ServiceInitializationError(
                                        f"Invalid query_type '{query_type}' for Azure AI Search. "
                                        f"Valid values are: {[qt.value for qt in AzureAISearchQueryType]}",
                                        ex,
                                    ) from ex
                            ai_search = AzureAISearchTool(
                                index_connection_id=azs_conn_id.id,
                                index_name=index_name,
                                query_type=query_type_enum,
                                top_k=additional_props.get("top_k", 3),
                                filter=additional_props.get("filter", ""),
                            )
                            tool_definitions.extend(ai_search.definitions)
                case dict():
                    tool_definitions.append(tool)
                case _:
                    raise ServiceInitializationError(f"Unsupported tool type: {type(tool)}")
        return tool_definitions

    def _convert_required_action_to_tool_output(
        self,
        required_action_results: list[FunctionResultContent | FunctionApprovalResponseContent] | None,
    ) -> tuple[str | None, list[ToolOutput] | None, list[ToolApproval] | None]:
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
                    result_contents: list[Any] = (  # type: ignore
                        content.result if isinstance(content.result, list) else [content.result]  # type: ignore
                    )
                    results: list[Any] = []
                    for item in result_contents:
                        if isinstance(item, BaseModel):
                            results.append(item.model_dump_json())
                        else:
                            results.append(json.dumps(item))
                    if len(results) == 1:
                        tool_outputs.append(FunctionToolOutput(tool_call_id=call_id, output=results[0]))
                    else:
                        tool_outputs.append(FunctionToolOutput(tool_call_id=call_id, output=json.dumps(results)))
                elif isinstance(content, FunctionApprovalResponseContent):
                    if tool_approvals is None:
                        tool_approvals = []
                    tool_approvals.append(ToolApproval(tool_call_id=call_id, approve=content.approved))

        return run_id, tool_outputs, tool_approvals

    def _update_agent_name(self, agent_name: str | None) -> None:
        """Update the agent name in the chat client.

        Args:
            agent_name: The new name for the agent.
        """
        # This is a no-op in the base class, but can be overridden by subclasses
        # to update the agent name in the client.
        if agent_name and not self.agent_name:
            self.agent_name = agent_name

    def service_url(self) -> str:
        """Get the service URL for the chat client.

        Returns:
            The service URL for the chat client, or None if not set.
        """
        return self.client._config.endpoint
