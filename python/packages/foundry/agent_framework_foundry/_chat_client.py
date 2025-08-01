# Copyright (c) Microsoft. All rights reserved.

import contextlib
import json
import sys
from collections.abc import AsyncIterable, MutableMapping, MutableSequence
from typing import Any, ClassVar

from agent_framework import (
    AIContents,
    AIFunction,
    ChatClientBase,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    ChatToolMode,
    DataContent,
    FunctionCallContent,
    FunctionResultContent,
    HostedCodeInterpreterTool,
    TextContent,
    UriContent,
    UsageContent,
    UsageDetails,
    use_tool_calling,
)
from agent_framework._clients import ai_function_to_json_schema_spec
from agent_framework._pydantic import AFBaseSettings
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.telemetry import use_telemetry
from azure.ai.agents.models import (
    AgentsNamedToolChoice,
    AgentsNamedToolChoiceType,
    AgentsToolChoiceOptionMode,
    AgentStreamEvent,
    AsyncAgentEventHandler,
    AsyncAgentRunStream,
    CodeInterpreterToolDefinition,
    FunctionName,
    ListSortOrder,
    MessageDeltaChunk,
    MessageImageUrlParam,
    MessageInputContentBlock,
    MessageInputImageUrlBlock,
    MessageInputTextBlock,
    MessageRole,
    RequiredFunctionToolCall,
    ResponseFormatJsonSchema,
    ResponseFormatJsonSchemaType,
    RunStatus,
    RunStep,
    SubmitToolOutputsAction,
    ThreadMessageOptions,
    ThreadRun,
    ToolOutput,
)
from azure.ai.projects.aio import AIProjectClient
from azure.core.credentials_async import AsyncTokenCredential
from pydantic import Field, PrivateAttr, ValidationError

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


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


@use_telemetry
@use_tool_calling
class FoundryChatClient(ChatClientBase):
    """Azure AI Foundry Chat client."""

    MODEL_PROVIDER_NAME: ClassVar[str] = "azure_ai_foundry"  # type: ignore[reportIncompatibleVariableOverride, misc]
    client: AIProjectClient = Field(...)
    credential: AsyncTokenCredential | None = Field(...)
    agent_id: str | None = Field(default=None)
    thread_id: str | None = Field(default=None)
    _should_delete_agent: bool = PrivateAttr(default=False)  # Track whether we should delete the agent
    _should_close_client: bool = PrivateAttr(default=False)  # Track whether we should close client connection
    _should_close_credential: bool = PrivateAttr(default=False)  # Track whether we should close credential
    _foundry_settings: FoundrySettings = PrivateAttr()

    def __init__(
        self,
        client: AIProjectClient | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        thread_id: str | None = None,
        project_endpoint: str | None = None,
        model_deployment_name: str | None = None,
        credential: AsyncTokenCredential | None = None,
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
                conversation_id property from ChatOptions, when making a request.
            project_endpoint: The Azure AI Foundry project endpoint URL. Used if client is not provided.
            model_deployment_name: The model deployment name to use for agent creation.
            credential: Azure async credential to use for authentication. If not provided,
                DefaultAzureCredential will be used.
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
        should_close_credential = False
        if client is None:
            if not foundry_settings.project_endpoint:
                raise ServiceInitializationError("Project endpoint is required when client is not provided.")

            if agent_id is None and not foundry_settings.model_deployment_name:
                raise ServiceInitializationError("Model deployment name is required for agent creation.")

            # Use provided credential or fallback to DefaultAzureCredential
            if credential is None:
                from azure.identity.aio import DefaultAzureCredential

                credential = DefaultAzureCredential()
                should_close_credential = True

            client = AIProjectClient(endpoint=foundry_settings.project_endpoint, credential=credential)
            should_close_client = True

        super().__init__(
            client=client,  # type: ignore[reportCallIssue]
            credential=credential,  # type: ignore[reportCallIssue]
            agent_id=agent_id,  # type: ignore[reportCallIssue]
            thread_id=thread_id,  # type: ignore[reportCallIssue]
            **kwargs,
        )

        self._should_delete_agent = False
        self._should_close_client = should_close_client
        self._should_close_credential = should_close_credential
        self._foundry_settings = foundry_settings

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
        await self._close_credential_if_needed()

    @classmethod
    def from_dict(cls, settings: dict[str, Any]) -> "FoundryChatClient":
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
        run_options, tool_results = self._create_run_options(messages, chat_options, **kwargs)

        # Get the thread ID
        thread_id: str | None = (
            chat_options.conversation_id if chat_options.conversation_id is not None else self.thread_id
        )

        if thread_id is None and tool_results is not None:
            raise ValueError("No thread ID was provided, but chat messages includes tool results.")

        # Determine which agent to use and create if needed
        agent_id = await self._get_agent_id_or_create()

        # Create the streaming response
        stream, thread_id = await self._create_agent_stream(thread_id, agent_id, run_options, tool_results)

        # Process and yield each update from the stream
        async for update in self._process_stream_events(stream, thread_id):
            yield update

    async def _get_agent_id_or_create(self) -> str:
        """Determine which agent to use and create if needed.

        Returns:
            str: The agent_id to use
        """
        # If no agent_id is provided, create a temporary agent
        if self.agent_id is None:
            if not self._foundry_settings.model_deployment_name:
                raise ServiceInitializationError("Model deployment name is required for agent creation.")

            agent_name = self._foundry_settings.agent_name
            created_agent = await self.client.agents.create_agent(
                model=self._foundry_settings.model_deployment_name, name=agent_name
            )
            self.agent_id = created_agent.id
            self._should_delete_agent = True

        return self.agent_id

    async def _create_agent_stream(
        self,
        thread_id: str | None,
        agent_id: str,
        run_options: dict[str, Any],
        tool_results: list[FunctionResultContent] | None,
    ) -> tuple[AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any], str]:
        """Create the agent stream for processing.

        Returns:
            tuple: (stream, final_thread_id)
        """
        # Get any active run for this thread
        thread_run = await self._get_active_thread_run(thread_id)

        handler: AsyncAgentEventHandler[Any] = AsyncAgentEventHandler()
        tool_run_id, tool_outputs = self._convert_function_results_to_tool_output(tool_results)

        if thread_run is not None and tool_run_id is not None and tool_run_id == thread_run.id and tool_outputs:
            # There's an active run and we have tool results to submit, so submit the results.
            await self.client.agents.runs.submit_tool_outputs_stream(  # type: ignore[reportUnknownMemberType]
                thread_run.thread_id, tool_run_id, tool_outputs=tool_outputs, event_handler=handler
            )
            # Pass the handler to the stream to continue processing
            stream = handler  # type: ignore
            final_thread_id = thread_run.thread_id
        else:
            # Handle thread creation or cancellation
            final_thread_id = await self._prepare_thread(thread_id, thread_run, run_options)

            # Now create a new run and stream the results.
            stream = await self.client.agents.runs.stream(  # type: ignore[reportUnknownMemberType]
                final_thread_id,
                agent_id=agent_id,
                **run_options,
            )

        return stream, final_thread_id

    async def _get_active_thread_run(self, thread_id: str | None) -> ThreadRun | None:
        """Get any active run for the given thread."""
        if thread_id is None:
            return None

        async for run in self.client.agents.runs.list(thread_id=thread_id, limit=1, order=ListSortOrder.DESCENDING):
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
        if thread_id is None:
            # No thread ID was provided, so create a new thread.
            thread = await self.client.agents.threads.create(
                messages=run_options["additional_messages"],
                tool_resources=run_options.get("tool_resources"),
                metadata=run_options.get("metadata"),
            )
            run_options["additional_messages"] = []
            return thread.id

        if thread_run is not None:
            # There was an active run; we need to cancel it before starting a new run.
            await self.client.agents.runs.cancel(thread_id, thread_run.id)

        return thread_id

    async def _process_stream_events(
        self,
        stream: AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | AsyncAgentEventHandler[Any],
        thread_id: str,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Process events from the agent stream and yield ChatResponseUpdate objects."""
        response_id: str | None = None

        if stream is not None:
            # Use 'async with' only if the stream supports async context management (main agent stream).
            # Tool output handlers only support async iteration, not context management.
            if isinstance(stream, contextlib.AbstractAsyncContextManager):
                async with stream as response_stream:  # type: ignore
                    async for update in self._process_stream_events_from_iterator(
                        response_stream, thread_id, response_id
                    ):
                        yield update
            else:
                async for update in self._process_stream_events_from_iterator(stream, thread_id, response_id):
                    yield update

    async def _process_stream_events_from_iterator(
        self,
        stream_iter: Any,
        thread_id: str,
        response_id: str | None,
    ) -> AsyncIterable[ChatResponseUpdate]:
        """Process events from the stream iterator and yield ChatResponseUpdate objects."""
        async for event_type, event_data, _ in stream_iter:  # type: ignore
            if event_type == AgentStreamEvent.THREAD_RUN_CREATED and isinstance(event_data, ThreadRun):
                yield ChatResponseUpdate(
                    contents=[],
                    conversation_id=event_data.thread_id,
                    message_id=response_id,
                    raw_representation=event_data,
                    response_id=response_id,
                    role=ChatRole.ASSISTANT,
                )
            elif event_type == AgentStreamEvent.THREAD_RUN_STEP_CREATED and isinstance(event_data, RunStep):
                response_id = event_data.run_id
            elif event_type == AgentStreamEvent.THREAD_MESSAGE_DELTA and isinstance(event_data, MessageDeltaChunk):
                role = ChatRole.USER if event_data.delta.role == MessageRole.USER else ChatRole.ASSISTANT
                yield ChatResponseUpdate(
                    role=role,
                    text=event_data.text,
                    conversation_id=thread_id,
                    message_id=response_id,
                    raw_representation=event_data,
                    response_id=response_id,
                )
            elif (
                event_type == AgentStreamEvent.THREAD_RUN_REQUIRES_ACTION
                and isinstance(event_data, ThreadRun)
                and isinstance(event_data.required_action, SubmitToolOutputsAction)
            ):
                contents = self._create_function_call_contents(event_data, response_id)
                if contents:
                    yield ChatResponseUpdate(
                        role=ChatRole.ASSISTANT,
                        contents=contents,
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=event_data,
                        response_id=response_id,
                    )
            elif (
                event_type == AgentStreamEvent.THREAD_RUN_COMPLETED
                and isinstance(event_data, RunStep)
                and event_data.usage is not None
            ):
                usage_content = UsageContent(
                    UsageDetails(
                        input_token_count=event_data.usage.prompt_tokens,
                        output_token_count=event_data.usage.completion_tokens,
                        total_token_count=event_data.usage.total_tokens,
                    )
                )
                yield ChatResponseUpdate(
                    role=ChatRole.ASSISTANT,
                    contents=[usage_content],
                    conversation_id=thread_id,
                    message_id=response_id,
                    raw_representation=event_data,
                    response_id=response_id,
                )
            else:
                yield ChatResponseUpdate(
                    contents=[],
                    conversation_id=thread_id,
                    message_id=response_id,
                    raw_representation=event_data,  # type: ignore
                    response_id=response_id,
                    role=ChatRole.ASSISTANT,
                )

    def _create_function_call_contents(self, event_data: ThreadRun, response_id: str | None) -> list[AIContents]:
        """Create function call contents from a tool action event."""
        contents: list[AIContents] = []

        if isinstance(event_data.required_action, SubmitToolOutputsAction):
            for tool_call in event_data.required_action.submit_tool_outputs.tool_calls:
                if isinstance(tool_call, RequiredFunctionToolCall):
                    call_id = json.dumps([response_id, tool_call.id])
                    function_name = tool_call.function.name
                    function_arguments = json.loads(tool_call.function.arguments)
                    contents.append(
                        FunctionCallContent(call_id=call_id, name=function_name, arguments=function_arguments)
                    )

        return contents

    async def _close_credential_if_needed(self) -> None:
        """Close credential if we created it."""
        if self._should_close_credential and self.credential is not None:
            await self.credential.close()

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

    def _create_run_options(
        self,
        messages: MutableSequence[ChatMessage],
        chat_options: ChatOptions | None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], list[FunctionResultContent] | None]:
        run_options: dict[str, Any] = {**kwargs}

        if chat_options is not None:
            run_options["max_completion_tokens"] = chat_options.max_tokens
            run_options["model"] = chat_options.ai_model_id
            run_options["top_p"] = chat_options.top_p
            run_options["temperature"] = chat_options.temperature
            run_options["parallel_tool_calls"] = chat_options.allow_multiple_tool_calls

            if chat_options.tool_choice is not None:
                tool_definitions: list[MutableMapping[str, Any]] = []
                if chat_options.tool_choice != "none" and chat_options.tools is not None:
                    for tool in chat_options.tools:
                        if isinstance(tool, AIFunction):
                            tool_definitions.append(ai_function_to_json_schema_spec(tool))
                        elif isinstance(tool, HostedCodeInterpreterTool):
                            tool_definitions.append(CodeInterpreterToolDefinition())
                        elif isinstance(tool, MutableMapping):
                            tool_definitions.append(tool)

                if len(tool_definitions) > 0:
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
        tool_results: list[FunctionResultContent] | None = None

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
                elif isinstance(content, FunctionResultContent):
                    if tool_results is None:
                        tool_results = []
                    tool_results.append(content)
                elif isinstance(content.raw_representation, MessageInputContentBlock):
                    message_contents.append(content.raw_representation)

            if len(message_contents) > 0:
                if additional_messages is None:
                    additional_messages = []
                additional_messages.append(
                    ThreadMessageOptions(
                        role=MessageRole.AGENT if chat_message.role == ChatRole.ASSISTANT else MessageRole.USER,
                        content=message_contents,
                    )
                )

        if additional_messages is not None:
            run_options["additional_messages"] = additional_messages

        if len(instructions) > 0:
            run_options["instructions"] = "".join(instructions)

        return run_options, tool_results

    def _convert_function_results_to_tool_output(
        self,
        tool_results: list[FunctionResultContent] | None,
    ) -> tuple[str | None, list[ToolOutput] | None]:
        run_id: str | None = None
        tool_outputs: list[ToolOutput] | None = None

        if tool_results:
            for function_result_content in tool_results:
                # When creating the FunctionCallContent, we created it with a CallId == [runId, callId].
                # We need to extract the run ID and ensure that the ToolOutput we send back to Azure
                # is only the call ID.
                run_and_call_ids: list[str] = json.loads(function_result_content.call_id)

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

                if tool_outputs is None:
                    tool_outputs = []
                tool_outputs.append(ToolOutput(tool_call_id=call_id, output=str(function_result_content.result)))

        return run_id, tool_outputs
