# Copyright (c) Microsoft. All rights reserved.

import json
from collections.abc import MutableMapping
from typing import Any, AsyncIterable, MutableSequence

from agent_framework import (
    AIContents,
    AITool,
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
    TextContent,
    UriContent,
    UsageContent,
    UsageDetails,
    use_tool_calling,
)
from agent_framework._clients import tool_to_json_schema_spec
from azure.ai.agents.models import (
    AgentsNamedToolChoice,
    AgentsNamedToolChoiceType,
    AgentsToolChoiceOptionMode,
    AgentStreamEvent,
    AsyncAgentEventHandler,
    AsyncAgentRunStream,
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


@use_tool_calling
class FoundryChatClient(ChatClientBase):
    client: AIProjectClient
    default_thread_id: str | None = None
    agent_id: str | None = None

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
            chat_options.conversation_id if chat_options.conversation_id is not None else self.default_thread_id
        )

        if thread_id is None and tool_results is not None:
            raise ValueError("No thread ID was provided, but chat messages includes tool results.")

        # Get any active run for this thread
        thread_run: ThreadRun | None = None

        if thread_id is not None:
            async for run in self.client.agents.runs.list(thread_id=thread_id, limit=1, order=ListSortOrder.DESCENDING):
                if (
                    run.status is not RunStatus.COMPLETED
                    and run.status is not RunStatus.CANCELLED
                    and run.status is not RunStatus.FAILED
                    and run.status is not RunStatus.EXPIRED
                ):
                    thread_run = run
                    break

        handler: AsyncAgentEventHandler[Any] = AsyncAgentEventHandler()
        stream: AsyncAgentRunStream[AsyncAgentEventHandler[Any]] | None = None

        tool_run_id, tool_outputs = self._convert_function_results_to_tool_output(tool_results)

        if thread_run is not None and tool_run_id is not None and tool_run_id == thread_run.id and tool_outputs:
            # There's an active run and we have tool results to submit, so submit the results.
            await self.client.agents.runs.submit_tool_outputs_stream(  # type: ignore[reportUnknownMemberType]
                thread_run.thread_id, tool_run_id, tool_outputs=tool_outputs, event_handler=handler
            )

            # Pass the handler to the stream to continue processing
            stream = handler  # type: ignore
        else:
            if thread_id is None:
                # No thread ID was provided, so create a new thread.
                thread = await self.client.agents.threads.create(
                    messages=run_options["additional_messages"],
                    tool_resources=run_options.get("tool_resources", None),
                    metadata=run_options.get("metadata", None),
                )
                run_options["additional_messages"] = []
                thread_id = thread.id
            elif thread_run is not None:
                # There was an active run; we need to cancel it before starting a new run.
                await self.client.agents.runs.cancel(thread_id, thread_run.id)
                thread_run = None

            # Now create a new run and stream the results.
            stream = await self.client.agents.runs.stream(  # type: ignore[reportUnknownMemberType]
                thread_id,
                agent_id=self.agent_id,
                **run_options,
            )
        # Process and yield each update.
        response_id: str | None = None

        if stream is not None:
            # Use 'async with' only if the stream supports async context management (main agent stream).
            # Tool output handlers only support async iteration, not context management.
            if hasattr(stream, "__aenter__") and hasattr(stream, "__aexit__"):
                async with stream as response_stream:
                    stream_iter = response_stream
            else:
                stream_iter = stream

            async for event_type, event_data, _ in stream_iter:  # type: ignore
                if event_type == AgentStreamEvent.THREAD_RUN_CREATED and isinstance(event_data, ThreadRun):
                    thread_id = event_data.thread_id
                    yield ChatResponseUpdate(
                        contents=[],
                        conversation_id=thread_id,
                        message_id=response_id,
                        raw_representation=event_data,
                        response_id=response_id,
                        role=ChatRole.ASSISTANT,
                    )
                elif event_type == AgentStreamEvent.THREAD_RUN_STEP_CREATED and isinstance(event_data, RunStep):
                    thread_id = event_data.thread_id
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
                    contents: list[AIContents] = []

                    for tool_call in event_data.required_action.submit_tool_outputs.tool_calls:
                        if isinstance(tool_call, RequiredFunctionToolCall):
                            call_id = json.dumps([response_id, tool_call.id])
                            function_name = tool_call.function.name
                            function_arguments = json.loads(tool_call.function.arguments)
                            contents.append(
                                FunctionCallContent(call_id=call_id, name=function_name, arguments=function_arguments)
                            )

                    if len(contents) > 0:
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

            if chat_options.tools is not None:
                tool_definitions: list[MutableMapping[str, Any]] = []

                for tool in chat_options.tools:
                    if isinstance(tool, AITool):
                        tool_definitions.append(tool_to_json_schema_spec(tool))
                    else:
                        tool_definitions.append(tool)

                if len(tool_definitions) > 0:
                    run_options["tools"] = tool_definitions

            if chat_options.tool_choice is not None:
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

        for chat_message in messages:
            if chat_message.role == ChatRole.SYSTEM or chat_message.role.value == "developer":
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
