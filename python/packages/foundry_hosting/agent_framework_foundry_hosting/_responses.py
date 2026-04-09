# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable

from agent_framework import Agent, ChatOptions, Content, HistoryProvider, Message
from agent_framework._telemetry import append_to_user_agent
from azure.ai.agentserver.responses import (
    ResponseContext,
    ResponseEventStream,
    ResponseProviderProtocol,
    ResponsesServerOptions,
)
from azure.ai.agentserver.responses.hosting import ResponsesAgentServerHost
from azure.ai.agentserver.responses.models import (
    ComputerScreenshotContent,
    CreateResponse,
    FunctionCallOutputItemParam,
    MessageContent,
    MessageContentInputFileContent,
    MessageContentInputImageContent,
    MessageContentInputTextContent,
    MessageContentOutputTextContent,
    MessageContentReasoningTextContent,
    MessageContentRefusalContent,
    OutputItem,
    OutputItemFunctionToolCall,
    OutputItemMessage,
    OutputItemOutputMessage,
    OutputItemReasoningItem,
    OutputMessageContent,
    OutputMessageContentOutputTextContent,
    OutputMessageContentRefusalContent,
    SummaryTextContent,
    TextContent,
    get_input_text,
)
from typing_extensions import Any, Sequence, cast


class ResponsesHostServer(ResponsesAgentServerHost):
    """A responses server host for an agent."""

    USER_AGENT_PREFIX = "foundry-hosting-responses"

    def __init__(
        self,
        agent: Agent,
        *,
        prefix: str = "",
        options: ResponsesServerOptions | None = None,
        provider: ResponseProviderProtocol | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a ResponsesHostServer.

        Args:
            agent: The agent to handle responses for.
            prefix: The URL prefix for the server.
            options: Optional server options.
            provider: Optional response provider.
            **kwargs: Additional keyword arguments.

        Note:
            The agent must not have a history provider with `load_messages=True`,
            because history is managed by the hosting infrastructure.
        """
        super().__init__(prefix=prefix, options=options, provider=provider, **kwargs)

        self._validate_agent(agent)
        self._agent = agent
        self.create_handler(self._handle_create)  # pyright: ignore[reportUnknownMemberType]

        # Append the user agent prefix for telemetry purposes
        append_to_user_agent(self.USER_AGENT_PREFIX)

    def _validate_agent(self, agent: Agent) -> None:
        """Validate the agent to ensure it does not have a history provider with `load_messages=True`.

        History is managed by the hosting infrastructure.
        """
        for provider in agent.context_providers:
            if isinstance(provider, HistoryProvider) and provider.load_messages:
                raise RuntimeError(
                    "There shouldn't be a history provider with `load_messages=True` already present. "
                    "History is managed by the hosting infrastructure."
                )

    async def _handle_create(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncIterable[dict[str, Any]]:
        """Handle the creation of a response."""
        input_items = get_input_text(request)
        history = await context.get_history()
        messages = [*_to_messages(history), input_items]

        chat_options = _to_chat_options(request)

        stream = ResponseEventStream(response_id=context.response_id, model=request.model)

        yield stream.emit_created()
        yield stream.emit_in_progress()

        # Add reasoning

        if request.stream is None or request.stream is False:
            # Run the agent in non-streaming mode
            response = await self._agent.run(messages, stream=False, options=chat_options)
            for item in stream.output_item_message(response.text):
                yield item
            yield stream.emit_completed()
            return

        # Start the streaming response
        message_item = stream.add_output_item_message()
        yield message_item.emit_added()
        text_content = message_item.add_text_content()
        yield text_content.emit_added()

        # Invoke the MAF agent
        response_stream = self._agent.run(messages, stream=True, options=chat_options)
        async for update in response_stream:
            if update.text:
                yield text_content.emit_delta(update.text)

        # Complete the message
        final = await response_stream.get_final_response()
        yield text_content.emit_done(final.text)
        yield message_item.emit_content_done(text_content)
        yield message_item.emit_done()

        yield stream.emit_completed()


# region Option Conversion


def _to_chat_options(request: CreateResponse) -> ChatOptions:
    """Converts a CreateResponse request to ChatOptions.

    Args:
        request (CreateResponse): The request to convert.

    Returns:
        ChatOptions: The converted ChatOptions.
    """
    chat_options = ChatOptions()

    if request.temperature is not None:
        chat_options["temperature"] = request.temperature
    if request.top_p is not None:
        chat_options["top_p"] = request.top_p
    if request.max_output_tokens is not None:
        chat_options["max_tokens"] = request.max_output_tokens
    if request.parallel_tool_calls is not None:
        chat_options["allow_multiple_tool_calls"] = request.parallel_tool_calls

    return chat_options


# endregion


# region Message Conversion


def _to_messages(history: Sequence[OutputItem]) -> list[Message]:
    """Converts a sequence of OutputItem objects to a list of Message objects.

    Args:
        history (Sequence[OutputItem]): The sequence of OutputItem objects to convert.

    Returns:
        list[Message]: The list of Message objects.
    """
    messages: list[Message] = []
    for item in history:
        messages.append(_to_message(item))
    return messages


def _to_message(item: OutputItem) -> Message:
    """Converts an OutputItem to a Message.

    Args:
        item (OutputItem): The OutputItem to convert.

    Returns:
        Message: The converted Message.

    Raises:
        ValueError: If the OutputItem type is not supported.
    """
    if item.type == "output_message":
        msg = cast(OutputItemOutputMessage, item)
        contents = [_convert_output_message_content(part) for part in msg.content]
        return Message(role=msg.role, contents=contents)

    if item.type == "message":
        msg = cast(OutputItemMessage, item)
        contents = [_convert_message_content(part) for part in msg.content]
        return Message(role=msg.role, contents=contents)

    if item.type == "function_call":
        fc = cast(OutputItemFunctionToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(fc.call_id, fc.name, arguments=fc.arguments)],
        )

    if item.type == "function_call_output":
        fco = cast(FunctionCallOutputItemParam, item)
        output = fco.output if isinstance(fco.output, str) else str(fco.output)
        return Message(
            role="tool",
            contents=[Content.from_function_result(fco.call_id, result=output)],
        )

    if item.type == "reasoning":
        reasoning = cast(OutputItemReasoningItem, item)
        contents: list[Content] = []
        if reasoning.summary:
            for summary in reasoning.summary:
                contents.append(Content.from_text(summary.text))
        return Message(role="assistant", contents=contents)

    raise ValueError(f"Unsupported OutputItem type: {item.type}")


def _convert_output_message_content(content: OutputMessageContent) -> Content:
    """Converts an OutputMessageContent to a Content object.

    Args:
        content (OutputMessageContent): The OutputMessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the OutputMessageContent type is not supported.
    """
    if content.type == "output_text":
        text_content = cast(OutputMessageContentOutputTextContent, content)
        return Content.from_text(text_content.text)
    if content.type == "refusal":
        refusal_content = cast(OutputMessageContentRefusalContent, content)
        return Content.from_text(refusal_content.refusal)

    raise ValueError(f"Unsupported OutputMessageContent type: {content.type}")


def _convert_message_content(content: MessageContent) -> Content:
    """Converts a MessageContent to a Content object.

    Args:
        content (MessageContent): The MessageContent to convert.

    Returns:
        Content: The converted Content object.

    Raises:
        ValueError: If the MessageContent type is not supported.
    """
    if content.type == "input_text":
        input_text = cast(MessageContentInputTextContent, content)
        return Content.from_text(input_text.text)
    if content.type == "output_text":
        output_text = cast(MessageContentOutputTextContent, content)
        return Content.from_text(output_text.text)
    if content.type == "text":
        text = cast(TextContent, content)
        return Content.from_text(text.text)
    if content.type == "summary_text":
        summary = cast(SummaryTextContent, content)
        return Content.from_text(summary.text)
    if content.type == "refusal":
        refusal = cast(MessageContentRefusalContent, content)
        return Content.from_text(refusal.refusal)
    if content.type == "reasoning_text":
        reasoning = cast(MessageContentReasoningTextContent, content)
        return Content.from_text_reasoning(text=reasoning.text)
    if content.type == "input_image":
        image = cast(MessageContentInputImageContent, content)
        if image.image_url:
            return Content.from_uri(image.image_url)
        if image.file_id:
            return Content.from_hosted_file(image.file_id)
    if content.type == "input_file":
        file = cast(MessageContentInputFileContent, content)
        if file.file_url:
            return Content.from_uri(file.file_url)
        if file.file_id:
            return Content.from_hosted_file(file.file_id, name=file.filename)
    if content.type == "computer_screenshot":
        screenshot = cast(ComputerScreenshotContent, content)
        return Content.from_uri(screenshot.image_url)

    raise ValueError(f"Unsupported MessageContent type: {content.type}")


# endregion
