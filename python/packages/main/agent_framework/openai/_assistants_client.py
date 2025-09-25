# Copyright (c) Microsoft. All rights reserved.

import json
import sys
from collections.abc import AsyncIterable, Mapping, MutableMapping, MutableSequence
from typing import Any

from openai import AsyncOpenAI
from openai.types.beta.threads import (
    ImageURLContentBlockParam,
    ImageURLParam,
    MessageContentPartParam,
    MessageDeltaEvent,
    Run,
    TextContentBlockParam,
    TextDeltaBlock,
)
from openai.types.beta.threads.run_create_params import AdditionalMessage
from openai.types.beta.threads.run_submit_tool_outputs_params import ToolOutput
from openai.types.beta.threads.runs import RunStep
from pydantic import Field, PrivateAttr, SecretStr, ValidationError

from .._clients import BaseChatClient
from .._tools import AIFunction, HostedCodeInterpreterTool, HostedFileSearchTool, use_function_invocation
from .._types import (
    ChatMessage,
    ChatOptions,
    ChatResponse,
    ChatResponseUpdate,
    ChatToolMode,
    Contents,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    UriContent,
    UsageContent,
    UsageDetails,
)
from ..exceptions import ServiceInitializationError
from ..observability import use_observability
from ._shared import OpenAIConfigMixin, OpenAISettings

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover


__all__ = ["OpenAIAssistantsClient"]


@use_function_invocation
@use_observability
class OpenAIAssistantsClient(OpenAIConfigMixin, BaseChatClient):
    """OpenAI Assistants client."""

    assistant_id: str | None = Field(default=None)
    assistant_name: str | None = Field(default=None)
    thread_id: str | None = Field(default=None)
    _should_delete_assistant: bool = PrivateAttr(default=False)  # Track whether we should delete the assistant

    def __init__(
        self,
        ai_model_id: str | None = None,
        assistant_id: str | None = None,
        assistant_name: str | None = None,
        thread_id: str | None = None,
        api_key: str | None = None,
        org_id: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        async_client: AsyncOpenAI | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize an OpenAI Assistants client.

        Args:
            ai_model_id: OpenAI model name, see
                https://platform.openai.com/docs/models
            assistant_id: The ID of an OpenAI assistant to use.
                If not provided, a new assistant will be created (and deleted after the request).
            assistant_name: The name to use when creating new assistants.
            thread_id: Default thread ID to use for conversations. Can be overridden by
                conversation_id property, when making a request.
                If not provided, a new thread will be created (and deleted after the request).
            api_key: The optional API key to use. If provided will override,
                the env vars or .env file value.
            org_id: The optional org ID to use. If provided will override,
                the env vars or .env file value.
            default_headers: The default headers mapping of string keys to
                string values for HTTP requests. (Optional)
            async_client: An existing client to use. (Optional)
            env_file_path: Use the environment settings file as a fallback
                to environment variables. (Optional)
            env_file_encoding: The encoding of the environment settings file. (Optional)
        """
        try:
            openai_settings = OpenAISettings(
                api_key=SecretStr(api_key) if api_key else None,
                org_id=org_id,
                chat_model_id=ai_model_id,
                env_file_path=env_file_path,
                env_file_encoding=env_file_encoding,
            )
        except ValidationError as ex:
            raise ServiceInitializationError("Failed to create OpenAI settings.", ex) from ex

        if not async_client and not openai_settings.api_key:
            raise ServiceInitializationError(
                "OpenAI API key is required. Set via 'api_key' parameter or 'OPENAI_API_KEY' environment variable."
            )
        if not openai_settings.chat_model_id:
            raise ServiceInitializationError(
                "OpenAI model ID is required. "
                "Set via 'ai_model_id' parameter or 'OPENAI_CHAT_MODEL_ID' environment variable."
            )

        super().__init__(
            ai_model_id=openai_settings.chat_model_id,
            assistant_id=assistant_id,  # type: ignore[reportCallIssue]
            assistant_name=assistant_name,  # type: ignore[reportCallIssue]
            thread_id=thread_id,  # type: ignore[reportCallIssue]
            api_key=openai_settings.api_key.get_secret_value() if openai_settings.api_key else None,
            org_id=openai_settings.org_id,
            default_headers=default_headers,
            client=async_client,
        )

    async def __aenter__(self) -> "Self":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        """Async context manager exit - clean up any assistants we created."""
        await self.close()

    async def close(self) -> None:
        """Clean up any assistants we created."""
        if self._should_delete_assistant and self.assistant_id is not None:
            await self.client.beta.assistants.delete(self.assistant_id)
            self.assistant_id = None
            self._should_delete_assistant = False

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
        # Extract necessary state from messages and options
        run_options, tool_results = self._prepare_options(messages, chat_options, **kwargs)

        # Get the thread ID
        thread_id: str | None = (
            chat_options.conversation_id
            if chat_options.conversation_id is not None
            else run_options.get("conversation_id", self.thread_id)
        )

        if thread_id is None and tool_results is not None:
            raise ValueError("No thread ID was provided, but chat messages includes tool results.")

        # Determine which assistant to use and create if needed
        assistant_id = await self._get_assistant_id_or_create()

        # Create the streaming response
        stream, thread_id = await self._create_assistant_stream(thread_id, assistant_id, run_options, tool_results)

        # Process and yield each update from the stream
        async for update in self._process_stream_events(stream, thread_id):
            yield update

    async def _get_assistant_id_or_create(self) -> str:
        """Determine which assistant to use and create if needed.

        Returns:
            str: The assistant_id to use.
        """
        # If no assistant is provided, create a temporary assistant
        if self.assistant_id is None:
            created_assistant = await self.client.beta.assistants.create(
                name=self.assistant_name, model=self.ai_model_id
            )

            self.assistant_id = created_assistant.id
            self._should_delete_assistant = True

        return self.assistant_id

    async def _create_assistant_stream(
        self,
        thread_id: str | None,
        assistant_id: str,
        run_options: dict[str, Any],
        tool_results: list[FunctionResultContent] | None,
    ) -> tuple[Any, str]:
        """Create the assistant stream for processing.

        Returns:
            tuple: (stream, final_thread_id)
        """
        # Get any active run for this thread
        thread_run = await self._get_active_thread_run(thread_id)

        tool_run_id, tool_outputs = self._convert_function_results_to_tool_output(tool_results)

        if thread_run is not None and tool_run_id is not None and tool_run_id == thread_run.id and tool_outputs:
            # There's an active run and we have tool results to submit, so submit the results.
            stream = self.client.beta.threads.runs.submit_tool_outputs_stream(  # type: ignore[reportDeprecated]
                run_id=tool_run_id, thread_id=thread_run.thread_id, tool_outputs=tool_outputs
            )
            final_thread_id = thread_run.thread_id
        else:
            # Handle thread creation or cancellation
            final_thread_id = await self._prepare_thread(thread_id, thread_run, run_options)

            # Now create a new run and stream the results.
            stream = self.client.beta.threads.runs.stream(  # type: ignore[reportDeprecated]
                assistant_id=assistant_id, thread_id=final_thread_id, **run_options
            )

        return stream, final_thread_id

    async def _get_active_thread_run(self, thread_id: str | None) -> Run | None:
        """Get any active run for the given thread."""
        if thread_id is None:
            return None

        async for run in self.client.beta.threads.runs.list(thread_id=thread_id, limit=1, order="desc"):  # type: ignore[reportDeprecated]
            if run.status not in ["completed", "cancelled", "failed", "expired"]:
                return run
        return None

    async def _prepare_thread(self, thread_id: str | None, thread_run: Run | None, run_options: dict[str, Any]) -> str:
        """Prepare the thread for a new run, creating or cleaning up as needed."""
        if thread_id is None:
            # No thread ID was provided, so create a new thread.
            thread = await self.client.beta.threads.create(  # type: ignore[reportDeprecated]
                messages=run_options["additional_messages"],
                tool_resources=run_options.get("tool_resources"),
                metadata=run_options.get("metadata"),
            )
            run_options["additional_messages"] = []
            run_options.pop("tool_resources", None)
            return thread.id

        if thread_run is not None:
            # There was an active run; we need to cancel it before starting a new run.
            await self.client.beta.threads.runs.cancel(run_id=thread_run.id, thread_id=thread_id)  # type: ignore[reportDeprecated]

        return thread_id

    async def _process_stream_events(self, stream: Any, thread_id: str) -> AsyncIterable[ChatResponseUpdate]:
        response_id: str | None = None

        async with stream as response_stream:
            async for response in response_stream:
                if response.event == "thread.run.created":
                    yield ChatResponseUpdate(
                        contents=[],
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=response.data,
                        response_id=response_id,
                        role=Role.ASSISTANT,
                    )
                elif response.event == "thread.run.step.created" and isinstance(response.data, RunStep):
                    response_id = response.data.run_id
                elif response.event == "thread.message.delta" and isinstance(response.data, MessageDeltaEvent):
                    delta = response.data.delta
                    role = Role.USER if delta.role == "user" else Role.ASSISTANT

                    for delta_block in delta.content or []:
                        if isinstance(delta_block, TextDeltaBlock) and delta_block.text and delta_block.text.value:
                            yield ChatResponseUpdate(
                                role=role,
                                text=delta_block.text.value,
                                conversation_id=thread_id,
                                message_id=response_id,
                                raw_representation=response.data,
                                response_id=response_id,
                            )
                elif response.event == "thread.run.requires_action" and isinstance(response.data, Run):
                    contents = self._create_function_call_contents(response.data, response_id)
                    if contents:
                        yield ChatResponseUpdate(
                            role=Role.ASSISTANT,
                            contents=contents,
                            conversation_id=thread_id,
                            message_id=response_id,
                            raw_representation=response.data,
                            response_id=response_id,
                        )
                elif (
                    response.event == "thread.run.completed"
                    and isinstance(response.data, Run)
                    and response.data.usage is not None
                ):
                    usage = response.data.usage
                    usage_content = UsageContent(
                        UsageDetails(
                            input_token_count=usage.prompt_tokens,
                            output_token_count=usage.completion_tokens,
                            total_token_count=usage.total_tokens,
                        )
                    )
                    yield ChatResponseUpdate(
                        role=Role.ASSISTANT,
                        contents=[usage_content],
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=response.data,
                        response_id=response_id,
                    )
                else:
                    yield ChatResponseUpdate(
                        contents=[],
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=response.data,
                        response_id=response_id,
                        role=Role.ASSISTANT,
                    )

    def _create_function_call_contents(self, event_data: Run, response_id: str | None) -> list[Contents]:
        """Create function call contents from a tool action event."""
        contents: list[Contents] = []

        if event_data.required_action is not None:
            for tool_call in event_data.required_action.submit_tool_outputs.tool_calls:
                call_id = json.dumps([response_id, tool_call.id])
                function_name = tool_call.function.name
                function_arguments = json.loads(tool_call.function.arguments)
                contents.append(FunctionCallContent(call_id=call_id, name=function_name, arguments=function_arguments))

        return contents

    def _prepare_options(
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

            if chat_options.allow_multiple_tool_calls is not None:
                run_options["parallel_tool_calls"] = chat_options.allow_multiple_tool_calls

            if chat_options.tool_choice is not None:
                tool_definitions: list[MutableMapping[str, Any]] = []
                if chat_options.tool_choice != "none" and chat_options.tools is not None:
                    for tool in chat_options.tools:
                        if isinstance(tool, AIFunction):
                            tool_definitions.append(tool.to_json_schema_spec())  # type: ignore[reportUnknownArgumentType]
                        elif isinstance(tool, HostedCodeInterpreterTool):
                            tool_definitions.append({"type": "code_interpreter"})
                        elif isinstance(tool, HostedFileSearchTool):
                            params: dict[str, Any] = {
                                "type": "file_search",
                            }
                            if tool.max_results is not None:
                                params["max_num_results"] = tool.max_results
                            tool_definitions.append(params)
                        elif isinstance(tool, MutableMapping):
                            tool_definitions.append(tool)

                if len(tool_definitions) > 0:
                    run_options["tools"] = tool_definitions

                if chat_options.tool_choice == "none" or chat_options.tool_choice == "auto":
                    run_options["tool_choice"] = chat_options.tool_choice
                elif (
                    isinstance(chat_options.tool_choice, ChatToolMode)
                    and chat_options.tool_choice == "required"
                    and chat_options.tool_choice.required_function_name is not None
                ):
                    run_options["tool_choice"] = {
                        "type": "function",
                        "function": {"name": chat_options.tool_choice.required_function_name},
                    }

            if chat_options.response_format is not None:
                run_options["response_format"] = {
                    "type": "json_schema",
                    "json_schema": chat_options.response_format.model_json_schema(),
                }

        instructions: list[str] = []
        tool_results: list[FunctionResultContent] | None = None

        additional_messages: list[AdditionalMessage] | None = None

        # System/developer messages are turned into instructions,
        # since there is no such message roles in OpenAI Assistants.
        # All other messages are added 1:1.
        for chat_message in messages:
            if chat_message.role.value in ["system", "developer"]:
                for text_content in [content for content in chat_message.contents if isinstance(content, TextContent)]:
                    instructions.append(text_content.text)

                continue

            message_contents: list[MessageContentPartParam] = []

            for content in chat_message.contents:
                if isinstance(content, TextContent):
                    message_contents.append(TextContentBlockParam(type="text", text=content.text))
                elif isinstance(content, UriContent) and content.has_top_level_media_type("image"):
                    message_contents.append(
                        ImageURLContentBlockParam(type="image_url", image_url=ImageURLParam(url=content.uri))
                    )
                elif isinstance(content, FunctionResultContent):
                    if tool_results is None:
                        tool_results = []
                    tool_results.append(content)

            if len(message_contents) > 0:
                if additional_messages is None:
                    additional_messages = []
                additional_messages.append(
                    AdditionalMessage(
                        role="assistant" if chat_message.role == Role.ASSISTANT else "user",
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

    def _update_agent_name(self, agent_name: str | None) -> None:
        """Update the agent name in the chat client.

        Args:
            agent_name: The new name for the agent.
        """
        # This is a no-op in the base class, but can be overridden by subclasses
        # to update the agent name in the client.
        if agent_name and not self.assistant_name:
            self.assistant_name = agent_name
