# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterable, AsyncIterator, Generator, Mapping

from agent_framework import ChatOptions, Content, HistoryProvider, Message, RawAgent, SupportsAgentRun
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
    FunctionShellAction,
    FunctionShellCallOutputContent,
    FunctionShellCallOutputExitOutcome,
    LocalEnvironmentResource,
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
    ResponseStreamEvent,
    SummaryTextContent,
    TextContent,
)
from azure.ai.agentserver.responses.streaming._builders import (
    OutputItemFunctionCallBuilder,
    OutputItemMcpCallBuilder,
    OutputItemMessageBuilder,
    OutputItemReasoningItemBuilder,
    ReasoningSummaryPartBuilder,
    TextContentBuilder,
)
from typing_extensions import Any, Sequence, cast

logger = logging.getLogger(__name__)


class ResponsesHostServer(ResponsesAgentServerHost):
    """A responses server host for an agent."""

    USER_AGENT_PREFIX = "foundry-hosting"

    def __init__(
        self,
        agent: SupportsAgentRun,
        *,
        prefix: str = "",
        options: ResponsesServerOptions | None = None,
        store: ResponseProviderProtocol | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a ResponsesHostServer.

        Args:
            agent: The agent to handle responses for.
            prefix: The URL prefix for the server.
            options: Optional server options.
            store: Optional response store.
            **kwargs: Additional keyword arguments.

        Note:
            The agent must not have a history provider with `load_messages=True`,
            because history is managed by the hosting infrastructure.
        """
        super().__init__(prefix=prefix, options=options, store=store, **kwargs)

        for provider in getattr(agent, "context_providers", []):
            if isinstance(provider, HistoryProvider) and provider.load_messages:
                raise RuntimeError(
                    "There shouldn't be a history provider with `load_messages=True` already present. "
                    "History is managed by the hosting infrastructure."
                )
        self._agent = agent

        self.response_handler(self._handler)  # pyright: ignore[reportUnknownMemberType]

        # Append the user agent prefix for telemetry purposes
        append_to_user_agent(self.USER_AGENT_PREFIX)

    async def _handler(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response."""
        input_text = await context.get_input_text()
        history = await context.get_history()
        messages = [*_to_messages(history), input_text]

        chat_options = _to_chat_options(request)

        stream = ResponseEventStream(response_id=context.response_id, model=request.model)

        yield stream.emit_created()
        yield stream.emit_in_progress()

        if request.stream is None or request.stream is False:
            # Run the agent in non-streaming mode
            if isinstance(self._agent, RawAgent):
                raw_agent = cast("RawAgent[Any]", self._agent)  # pyright: ignore[reportUnknownMemberType]
                response = await raw_agent.run(messages, stream=False, options=chat_options)
            else:
                response = await self._agent.run(messages, stream=False)

            for message in response.messages:
                for content in message.contents:
                    async for item in _to_outputs(stream, content):
                        yield item

            yield stream.emit_completed()
            return

        # Start the streaming response
        if isinstance(self._agent, RawAgent):
            raw_agent = cast("RawAgent[Any]", self._agent)  # pyright: ignore[reportUnknownMemberType]
            response_stream = raw_agent.run(messages, stream=True, options=chat_options)
        else:
            response_stream = self._agent.run(messages, stream=True)

        # Track the current active output item builder for streaming;
        # lazily created on matching content, closed when a different type arrives.
        tracker = _OutputItemTracker(stream)

        async for update in response_stream:
            for content in update.contents:
                for event in tracker.handle(content):
                    yield event
                if tracker.needs_async:
                    async for item in _to_outputs(stream, content):
                        yield item
                    tracker.needs_async = False

        # Close any remaining active builder
        for event in tracker.close():
            yield event

        yield stream.emit_completed()


# region Active Builder State


class _OutputItemTracker:
    """Tracks the current active output item builder during streaming.

    Handles lazy creation, delta emission, and closing of streaming builders
    for text messages, reasoning, function calls, and MCP calls.
    """

    _DELTA_TYPES = frozenset({"text", "text_reasoning", "function_call", "mcp_server_tool_call"})

    def __init__(self, stream: ResponseEventStream) -> None:
        self._stream = stream
        self._active_type: str | None = None
        self._active_id: str | None = None
        # Accumulated delta text for the current active builder
        self._accumulated: list[str] = []
        # Builder state — only one is active at a time
        self._message_item: OutputItemMessageBuilder | None = None
        self._text_content: TextContentBuilder | None = None
        self._reasoning_item: OutputItemReasoningItemBuilder | None = None
        self._summary_part: ReasoningSummaryPartBuilder | None = None
        self._fc_builder: OutputItemFunctionCallBuilder | None = None
        self._mcp_builder: OutputItemMcpCallBuilder | None = None
        self.needs_async = False

    def handle(self, content: Content) -> Generator[ResponseStreamEvent, None, None]:
        """Process a content item, yielding sync events.

        Sets ``needs_async = True`` if the caller must also drain an
        async ``_to_outputs`` call for this content.
        """
        if content.type == "text" and content.text is not None:
            if self._active_type != "text":
                yield from self._close()
                yield from self._open_message()
            assert self._text_content is not None  # noqa: S101
            self._accumulated.append(content.text)
            yield self._text_content.emit_delta(content.text)

        elif content.type == "text_reasoning" and content.text is not None:
            if self._active_type != "text_reasoning":
                yield from self._close()
                yield from self._open_reasoning()
            assert self._summary_part is not None  # noqa: S101
            self._accumulated.append(content.text)
            yield self._summary_part.emit_text_delta(content.text)

        elif content.type == "function_call" and content.call_id is not None:
            if self._active_type != "function_call" or self._active_id != content.call_id:
                yield from self._close()
                yield from self._open_function_call(content)
            assert self._fc_builder is not None  # noqa: S101
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            yield self._fc_builder.emit_arguments_delta(args_str)

        elif content.type == "mcp_server_tool_call" and content.tool_name:
            key = f"{content.server_name or 'default'}::{content.tool_name}"
            if self._active_type != "mcp_server_tool_call" or self._active_id != key:
                yield from self._close()
                yield from self._open_mcp_call(content)
            assert self._mcp_builder is not None  # noqa: S101
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            yield self._mcp_builder.emit_arguments_delta(args_str)

        else:
            yield from self._close()
            self.needs_async = True

    def close(self) -> Generator[ResponseStreamEvent, None, None]:
        """Close any remaining active builder."""
        yield from self._close()

    # -- Private open/close helpers --

    def _open_message(self) -> Generator[ResponseStreamEvent, None, None]:
        self._message_item = self._stream.add_output_item_message()
        self._text_content = self._message_item.add_text_content()
        self._active_type = "text"
        self._active_id = None
        yield self._message_item.emit_added()
        yield self._text_content.emit_added()

    def _open_reasoning(self) -> Generator[ResponseStreamEvent, None, None]:
        self._reasoning_item = self._stream.add_output_item_reasoning_item()
        self._summary_part = self._reasoning_item.add_summary_part()
        self._active_type = "text_reasoning"
        self._active_id = None
        yield self._reasoning_item.emit_added()
        yield self._summary_part.emit_added()

    def _open_function_call(self, content: Content) -> Generator[ResponseStreamEvent, None, None]:
        self._fc_builder = self._stream.add_output_item_function_call(
            name=content.name or "",
            call_id=content.call_id or "",
        )
        self._active_type = "function_call"
        self._active_id = content.call_id
        yield self._fc_builder.emit_added()

    def _open_mcp_call(self, content: Content) -> Generator[ResponseStreamEvent, None, None]:
        self._mcp_builder = self._stream.add_output_item_mcp_call(
            server_label=content.server_name or "default",
            name=content.tool_name or "",
        )
        self._active_type = "mcp_server_tool_call"
        self._active_id = f"{content.server_name or 'default'}::{content.tool_name}"
        yield self._mcp_builder.emit_added()

    def _close(self) -> Generator[ResponseStreamEvent, None, None]:
        accumulated = "".join(self._accumulated)

        if self._active_type == "text" and self._text_content and self._message_item:
            yield self._text_content.emit_text_done(accumulated)
            yield self._text_content.emit_done()
            yield self._message_item.emit_done()
            self._text_content = None
            self._message_item = None

        elif self._active_type == "text_reasoning" and self._summary_part and self._reasoning_item:
            yield self._summary_part.emit_text_done(accumulated)
            yield self._summary_part.emit_done()
            yield self._reasoning_item.emit_done()
            self._summary_part = None
            self._reasoning_item = None

        elif self._active_type == "function_call" and self._fc_builder:
            yield self._fc_builder.emit_arguments_done(accumulated)
            yield self._fc_builder.emit_done()
            self._fc_builder = None

        elif self._active_type == "mcp_server_tool_call" and self._mcp_builder:
            yield self._mcp_builder.emit_arguments_done(accumulated)
            yield self._mcp_builder.emit_completed()
            yield self._mcp_builder.emit_done()
            self._mcp_builder = None

        self._active_type = None
        self._active_id = None
        self._accumulated.clear()


# endregion


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


# region Input Message Conversion


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

# region Output Item Conversion


def _arguments_to_str(arguments: str | Mapping[str, Any] | None) -> str:
    """Convert arguments to a JSON string.

    Args:
        arguments: The arguments to convert, can be a string, mapping, or None.

    Returns:
        The arguments as a JSON string.
    """
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments)


async def _to_outputs(stream: ResponseEventStream, content: Content) -> AsyncIterator[ResponseStreamEvent]:
    """Converts a Content object to an async sequence of ResponseStreamEvent objects.

    Args:
        stream: The ResponseEventStream to use for building events.
        content: The Content to convert.

    Yields:
        ResponseStreamEvent: The converted event objects.

    Raises:
        ValueError: If the Content type is not supported.
    """
    if content.type == "text" and content.text is not None:
        async for event in stream.aoutput_item_message(content.text):
            yield event
    elif content.type == "text_reasoning" and content.text is not None:
        async for event in stream.aoutput_item_reasoning_item(content.text):
            yield event
    elif content.type == "function_call":
        async for event in stream.aoutput_item_function_call(
            content.name,  # type: ignore[arg-type]
            content.call_id,  # type: ignore[arg-type]
            _arguments_to_str(content.arguments),
        ):
            yield event
    elif content.type == "function_result":
        async for event in stream.aoutput_item_function_call_output(
            content.call_id,  # type: ignore[arg-type]
            str(content.result or ""),
        ):
            yield event
    elif content.type == "image_generation_tool_result" and content.outputs is not None:
        async for event in stream.aoutput_item_image_gen_call(str(content.outputs)):
            yield event
    elif content.type == "mcp_server_tool_call":
        mcp_call = stream.add_output_item_mcp_call(
            server_label=content.server_name or "default",
            name=content.tool_name or "",
        )
        yield mcp_call.emit_added()
        async for event in mcp_call.aarguments(_arguments_to_str(content.arguments)):
            yield event
        yield mcp_call.emit_completed()
        yield mcp_call.emit_done()
    elif content.type == "mcp_server_tool_result":
        output = (
            content.output
            if isinstance(content.output, str)
            else str(content.output)
            if content.output is not None
            else ""
        )
        async for event in stream.aoutput_item_custom_tool_call_output(content.call_id or "", output):
            yield event
    elif content.type == "shell_tool_call":
        action = FunctionShellAction(commands=content.commands or [], timeout_ms=0, max_output_length=0)
        async for event in stream.aoutput_item_function_shell_call(
            content.call_id or "",
            action,
            LocalEnvironmentResource(),
            status=content.status or "completed",
        ):
            yield event
    elif content.type == "shell_tool_result":
        output_items: list[FunctionShellCallOutputContent] = []
        if content.outputs:
            for out in content.outputs:
                exit_code = getattr(out, "exit_code", None)
                output_items.append(
                    FunctionShellCallOutputContent(
                        stdout=getattr(out, "stdout", "") or "",
                        stderr=getattr(out, "stderr", "") or "",
                        outcome=FunctionShellCallOutputExitOutcome(exit_code=exit_code if exit_code is not None else 0),
                    )
                )
        async for event in stream.aoutput_item_function_shell_call_output(
            content.call_id or "",
            output_items,
            status=content.status or "completed",
            max_output_length=content.max_output_length,
        ):
            yield event
    else:
        # Log a warning for unsupported content types instead of raising an error to avoid breaking the response stream.
        logger.warning(f"Content type '{content.type}' is not supported yet.")


# endregion
