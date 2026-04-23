# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable, AsyncIterator, Generator, Mapping, Sequence
from typing import cast

from agent_framework import (
    ChatOptions,
    Content,
    ContextProvider,
    FileCheckpointStorage,
    HistoryProvider,
    Message,
    RawAgent,
    SupportsAgentRun,
    WorkflowAgent,
)
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
    OAuthConsentRequestOutputItem,
    OutputItem,
    OutputItemApplyPatchToolCall,
    OutputItemApplyPatchToolCallOutput,
    OutputItemCodeInterpreterToolCall,
    OutputItemComputerToolCall,
    OutputItemComputerToolCallOutputResource,
    OutputItemCustomToolCall,
    OutputItemCustomToolCallOutput,
    OutputItemFileSearchToolCall,
    OutputItemFunctionShellCall,
    OutputItemFunctionShellCallOutput,
    OutputItemFunctionToolCall,
    OutputItemImageGenToolCall,
    OutputItemLocalShellToolCall,
    OutputItemLocalShellToolCallOutput,
    OutputItemMcpApprovalRequest,
    OutputItemMcpApprovalResponseResource,
    OutputItemMcpToolCall,
    OutputItemMessage,
    OutputItemOutputMessage,
    OutputItemReasoningItem,
    OutputItemWebSearchToolCall,
    OutputMessageContent,
    OutputMessageContentOutputTextContent,
    OutputMessageContentRefusalContent,
    ResponseStreamEvent,
    StructuredOutputsOutputItem,
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
from typing_extensions import Any

logger = logging.getLogger(__name__)


class ResponsesHostServer(ResponsesAgentServerHost):
    """A responses server host for an agent."""

    # TODO(@taochen): Allow a different checkpoint storage that stores checkpoints externally
    CHECKPOINT_STORAGE_PATH = "/.checkpoints"

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
            1. The agent must not have a history provider with `load_messages=True`,
               because history is managed by the hosting infrastructure.
            2. The agent must not have any context providers that maintain context
               in memory, because the hosting environment may get deactivated between
               requests, and any in-memory context would be lost.
        """
        super().__init__(prefix=prefix, options=options, store=store, **kwargs)

        for provider in getattr(agent, "context_providers", []):
            if isinstance(provider, HistoryProvider) and provider.load_messages:
                raise RuntimeError(
                    "There shouldn't be a history provider with `load_messages=True` already present. "
                    "History is managed by the hosting infrastructure."
                )
            provider = cast(ContextProvider, provider)
            logger.warning(
                "Context provider %s is present. If it maintains context in memory, "
                "the context may be lost between requests. Use with caution.",
                provider.source_id,
            )

        self._is_workflow_agent = False
        self._checkpoint_storage_path = None
        if isinstance(agent, WorkflowAgent):
            if agent.workflow._runner_context.has_checkpointing():  # pyright: ignore[reportPrivateUsage]
                raise RuntimeError(
                    "There should not be a checkpoint storage already present in the workflow agent. "
                    "The hosting infrastructure will manage checkpoints instead."
                )
            self._checkpoint_storage_path = (
                self.CHECKPOINT_STORAGE_PATH
                if self.config.is_hosted
                else os.path.join(os.getcwd(), self.CHECKPOINT_STORAGE_PATH.lstrip("/"))
            )
            self._is_workflow_agent = True

        self._agent = agent
        self.response_handler(self._handle_response)  # pyright: ignore[reportUnknownMemberType]

    @staticmethod
    def _is_streaming_request(request: CreateResponse) -> bool:
        """Check if the request is a streaming request."""
        return request.stream is not None and request.stream is True

    def _handle_response(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response."""
        if self._is_workflow_agent:
            # Workflow agents are handled differently because they require checkpoint restoration
            return self._handle_workflow_agent(request, context)

        return self._handle_regular_agent(request, context)

    async def _handle_regular_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response for a regular (non-workflow) agent."""
        input_text = await context.get_input_text()
        history = await context.get_history()
        messages: list[str | Content | Message] = [*_to_messages(history), input_text]

        chat_options, are_options_set = _to_chat_options(request)

        is_streaming_request = self._is_streaming_request(request)
        response_event_stream = ResponseEventStream(response_id=context.response_id, model=request.model)

        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        if not is_streaming_request:
            # Run the agent in non-streaming mode
            if isinstance(self._agent, RawAgent):
                raw_agent = cast("RawAgent[Any]", self._agent)  # type: ignore[redundant-cast]  # pyright: ignore[reportUnknownMemberType]
                response = await raw_agent.run(messages, stream=False, options=chat_options)
            else:
                if are_options_set:
                    logger.warning("Agent doesn't support runtime options. They will be ignored.")
                response = await self._agent.run(messages, stream=False)

            for message in response.messages:
                for content in message.contents:
                    async for item in _to_outputs(response_event_stream, content):
                        yield item

            yield response_event_stream.emit_completed()
            return

        # Run the agent in streaming mode
        if isinstance(self._agent, RawAgent):
            raw_agent = cast("RawAgent[Any]", self._agent)  # type: ignore[redundant-cast]  # pyright: ignore[reportUnknownMemberType]
            response_stream = raw_agent.run(messages, stream=True, options=chat_options)
        else:
            if are_options_set:
                logger.warning("Agent doesn't support runtime options. They will be ignored.")
            response_stream = self._agent.run(messages, stream=True)

        # Track the current active output item builder for streaming;
        # lazily created on matching content, closed when a different type arrives.
        tracker = _OutputItemTracker(response_event_stream)

        async for update in response_stream:
            for content in update.contents:
                for event in tracker.handle(content):
                    yield event
                if tracker.needs_async:
                    async for item in _to_outputs(response_event_stream, content):
                        yield item
                    tracker.needs_async = False

        # Close any remaining active builder
        for event in tracker.close():
            yield event

        yield response_event_stream.emit_completed()

    async def _handle_workflow_agent(
        self,
        request: CreateResponse,
        context: ResponseContext,
    ) -> AsyncIterable[ResponseStreamEvent | dict[str, Any]]:
        """Handle the creation of a response for a workflow agent.

        Why this is required:
        The sandbox may be deactivated after some period of inactivity, and only data managed
        by the hosting infrastructure or files will be preserved upon deactivation.
        """
        input_text = await context.get_input_text()
        is_streaming_request = self._is_streaming_request(request)

        _, are_options_set = _to_chat_options(request)
        if are_options_set:
            logger.warning("Workflow agent doesn't support runtime options. They will be ignored.")

        if request.previous_response_id is not None and context.conversation_id is not None:
            raise RuntimeError("Previous response ID cannot be used in conjunction with conversation ID.")
        context_id = request.previous_response_id or context.conversation_id

        # The following should never happen due to the checks above.
        # This is for type safety and defensive programming.
        if self._checkpoint_storage_path is None:
            raise RuntimeError("Checkpoint storage path is not configured for workflow agent.")
        if not isinstance(self._agent, WorkflowAgent):
            raise RuntimeError("Agent is not a workflow agent.")

        # Restore from the latest checkpoint if available, otherwise start with an empty history
        if context_id is not None:
            checkpoint_storage = FileCheckpointStorage(os.path.join(self._checkpoint_storage_path, context_id))
            latest_checkpoint = await checkpoint_storage.get_latest(workflow_name=self._agent.workflow.name)
            if latest_checkpoint is not None:
                if not is_streaming_request:
                    _ = await self._agent.run(
                        stream=False,
                        checkpoint_id=latest_checkpoint.checkpoint_id,
                        checkpoint_storage=checkpoint_storage,
                    )
                else:
                    # Consume the streaming or the invocation will result in a no-op
                    async for _ in self._agent.run(
                        stream=True,
                        checkpoint_id=latest_checkpoint.checkpoint_id,
                        checkpoint_storage=checkpoint_storage,
                    ):
                        pass

        # Now run the agent with the latest input
        response_event_stream = ResponseEventStream(response_id=context.response_id, model=request.model)

        # Create a new checkpoint storage for this response based on the following rules:
        # - If no previous response ID or conversation ID is provided, create a new checkpoint storage for this response
        # - If a previous response ID is provided, create a new checkpoint storage for this response
        # - If a conversation ID is provided, reuse the existing checkpoint storage for the conversation
        context_id = context.conversation_id or context.response_id
        checkpoint_storage = FileCheckpointStorage(os.path.join(self._checkpoint_storage_path, context_id))

        yield response_event_stream.emit_created()
        yield response_event_stream.emit_in_progress()

        if not is_streaming_request:
            # Run the agent in non-streaming mode
            response = await self._agent.run(input_text, stream=False, checkpoint_storage=checkpoint_storage)

            for message in response.messages:
                for content in message.contents:
                    async for item in _to_outputs(response_event_stream, content):
                        yield item

            await self._delete_not_latest_checkpoints(checkpoint_storage, self._agent.workflow.name)
            yield response_event_stream.emit_completed()
            return

        # Run the agent in streaming mode
        response_stream = self._agent.run(input_text, stream=True, checkpoint_storage=checkpoint_storage)

        # Track the current active output item builder for streaming;
        # lazily created on matching content, closed when a different type arrives.
        tracker = _OutputItemTracker(response_event_stream)

        async for update in response_stream:
            for content in update.contents:
                for event in tracker.handle(content):
                    yield event
                if tracker.needs_async:
                    async for item in _to_outputs(response_event_stream, content):
                        yield item
                    tracker.needs_async = False

        # Close any remaining active builder
        for event in tracker.close():
            yield event

        await self._delete_not_latest_checkpoints(checkpoint_storage, self._agent.workflow.name)
        yield response_event_stream.emit_completed()
        return

    @staticmethod
    async def _delete_not_latest_checkpoints(checkpoint_storage: FileCheckpointStorage, workflow_name: str) -> None:
        """Delete all checkpoints except the latest one.

        We only need the last checkpoint for each invocation.
        """
        latest_checkpoint = await checkpoint_storage.get_latest(workflow_name=workflow_name)
        if latest_checkpoint is not None:
            all_checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow_name)
            for checkpoint in all_checkpoints:
                if checkpoint.checkpoint_id != latest_checkpoint.checkpoint_id:
                    await checkpoint_storage.delete(checkpoint.checkpoint_id)


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

    def handle(self, content: Content) -> Generator[ResponseStreamEvent]:
        """Process a content item, yielding sync events.

        Sets ``needs_async = True`` if the caller must also drain an
        async ``_to_outputs`` call for this content.
        """
        if content.type == "text" and content.text is not None:
            if self._active_type != "text":
                yield from self._close()
                yield from self._open_message()
            self._accumulated.append(content.text)
            if self._text_content is not None:
                yield self._text_content.emit_delta(content.text)

        elif content.type == "text_reasoning" and content.text is not None:
            if self._active_type != "text_reasoning":
                yield from self._close()
                yield from self._open_reasoning()
            self._accumulated.append(content.text)
            if self._summary_part is not None:
                yield self._summary_part.emit_text_delta(content.text)

        elif content.type == "function_call" and content.call_id is not None:
            if self._active_type != "function_call" or self._active_id != content.call_id:
                yield from self._close()
                yield from self._open_function_call(content)
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            if self._fc_builder is not None:
                yield self._fc_builder.emit_arguments_delta(args_str)

        elif content.type == "mcp_server_tool_call" and content.tool_name:
            key = f"{content.server_name or 'default'}::{content.tool_name}"
            if self._active_type != "mcp_server_tool_call" or self._active_id != key:
                yield from self._close()
                yield from self._open_mcp_call(content)
            args_str = _arguments_to_str(content.arguments)
            self._accumulated.append(args_str)
            if self._mcp_builder is not None:
                yield self._mcp_builder.emit_arguments_delta(args_str)

        else:
            yield from self._close()
            self.needs_async = True

    def close(self) -> Generator[ResponseStreamEvent]:
        """Close any remaining active builder."""
        yield from self._close()

    # -- Private open/close helpers --

    def _open_message(self) -> Generator[ResponseStreamEvent]:
        self._message_item = self._stream.add_output_item_message()
        self._text_content = self._message_item.add_text_content()
        self._active_type = "text"
        self._active_id = None
        yield self._message_item.emit_added()
        yield self._text_content.emit_added()

    def _open_reasoning(self) -> Generator[ResponseStreamEvent]:
        self._reasoning_item = self._stream.add_output_item_reasoning_item()
        self._summary_part = self._reasoning_item.add_summary_part()
        self._active_type = "text_reasoning"
        self._active_id = None
        yield self._reasoning_item.emit_added()
        yield self._summary_part.emit_added()

    def _open_function_call(self, content: Content) -> Generator[ResponseStreamEvent]:
        self._fc_builder = self._stream.add_output_item_function_call(
            name=content.name or "",
            call_id=content.call_id or "",
        )
        self._active_type = "function_call"
        self._active_id = content.call_id
        yield self._fc_builder.emit_added()

    def _open_mcp_call(self, content: Content) -> Generator[ResponseStreamEvent]:
        self._mcp_builder = self._stream.add_output_item_mcp_call(
            server_label=content.server_name or "default",
            name=content.tool_name or "",
        )
        self._active_type = "mcp_server_tool_call"
        self._active_id = f"{content.server_name or 'default'}::{content.tool_name}"
        yield self._mcp_builder.emit_added()

    def _close(self) -> Generator[ResponseStreamEvent]:
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


def _to_chat_options(request: CreateResponse) -> tuple[ChatOptions, bool]:
    """Converts a CreateResponse request to ChatOptions.

    Args:
        request (CreateResponse): The request to convert.

    Returns:
        ChatOptions: The converted ChatOptions.
        bool: Whether any options were set.

    """
    chat_options = ChatOptions()
    are_options_set = False

    if request.temperature is not None:
        chat_options["temperature"] = request.temperature
        are_options_set = True
    if request.top_p is not None:
        chat_options["top_p"] = request.top_p
        are_options_set = True
    if request.max_output_tokens is not None:
        chat_options["max_tokens"] = request.max_output_tokens
        are_options_set = True
    if request.parallel_tool_calls is not None:
        chat_options["allow_multiple_tool_calls"] = request.parallel_tool_calls
        are_options_set = True

    return chat_options, are_options_set


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
        output_msg = cast(OutputItemOutputMessage, item)
        return Message(
            role=output_msg.role, contents=[_convert_output_message_content(part) for part in output_msg.content]
        )

    if item.type == "message":
        msg = cast(OutputItemMessage, item)
        return Message(role=msg.role, contents=[_convert_message_content(part) for part in msg.content])

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

    if item.type == "mcp_call":
        mcp = cast(OutputItemMcpToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_mcp_server_tool_call(
                    mcp.id,
                    mcp.name,
                    server_name=mcp.server_label,
                    arguments=mcp.arguments,
                )
            ],
        )

    if item.type == "mcp_approval_request":
        mcp_req = cast(OutputItemMcpApprovalRequest, item)
        mcp_call_content = Content.from_mcp_server_tool_call(
            mcp_req.id,
            mcp_req.name,
            server_name=mcp_req.server_label,
            arguments=mcp_req.arguments,
        )
        return Message(
            role="assistant",
            contents=[Content.from_function_approval_request(mcp_req.id, mcp_call_content)],
        )

    if item.type == "mcp_approval_response":
        mcp_resp = cast(OutputItemMcpApprovalResponseResource, item)
        # Build a placeholder function_call Content since the original call details are not available
        placeholder_content = Content.from_function_call(mcp_resp.approval_request_id, "mcp_approval")
        return Message(
            role="user",
            contents=[Content.from_function_approval_response(mcp_resp.approve, mcp_resp.id, placeholder_content)],
        )

    if item.type == "code_interpreter_call":
        ci = cast(OutputItemCodeInterpreterToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_code_interpreter_tool_call(call_id=ci.id)],
        )

    if item.type == "image_generation_call":
        ig = cast(OutputItemImageGenToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_image_generation_tool_call(image_id=ig.id)],
        )

    if item.type == "shell_call":
        sc = cast(OutputItemFunctionShellCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=sc.call_id,
                    commands=sc.action.commands,
                    status=str(sc.status),
                )
            ],
        )

    if item.type == "shell_call_output":
        sco = cast(OutputItemFunctionShellCallOutput, item)
        outputs = [
            Content.from_shell_command_output(
                stdout=out.stdout or "",
                stderr=out.stderr or "",
                exit_code=getattr(out.outcome, "exit_code", None) if hasattr(out, "outcome") else None,
            )
            for out in (sco.output or [])
        ]
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=sco.call_id,
                    outputs=outputs,
                    max_output_length=sco.max_output_length,
                )
            ],
        )

    if item.type == "local_shell_call":
        lsc = cast(OutputItemLocalShellToolCall, item)
        commands = lsc.action.command if hasattr(lsc.action, "command") and lsc.action.command else []
        return Message(
            role="assistant",
            contents=[
                Content.from_shell_tool_call(
                    call_id=lsc.call_id,
                    commands=commands,
                    status=str(lsc.status),
                )
            ],
        )

    if item.type == "local_shell_call_output":
        lsco = cast(OutputItemLocalShellToolCallOutput, item)
        return Message(
            role="tool",
            contents=[
                Content.from_shell_tool_result(
                    call_id=lsco.id,
                    outputs=[Content.from_shell_command_output(stdout=lsco.output)],
                )
            ],
        )

    if item.type == "file_search_call":
        fs = cast(OutputItemFileSearchToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    fs.id,
                    "file_search",
                    arguments=json.dumps({"queries": fs.queries}),
                )
            ],
        )

    if item.type == "web_search_call":
        ws = cast(OutputItemWebSearchToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(ws.id, "web_search")],
        )

    if item.type == "computer_call":
        cc = cast(OutputItemComputerToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    cc.call_id,
                    "computer_use",
                    arguments=str(cc.action),
                )
            ],
        )

    if item.type == "computer_call_output":
        cco = cast(OutputItemComputerToolCallOutputResource, item)
        return Message(
            role="tool",
            contents=[Content.from_function_result(cco.call_id, result=str(cco.output))],
        )

    if item.type == "custom_tool_call":
        ct = cast(OutputItemCustomToolCall, item)
        return Message(
            role="assistant",
            contents=[Content.from_function_call(ct.call_id, ct.name, arguments=ct.input)],
        )

    if item.type == "custom_tool_call_output":
        cto = cast(OutputItemCustomToolCallOutput, item)
        output = cto.output if isinstance(cto.output, str) else str(cto.output)
        return Message(
            role="tool",
            contents=[Content.from_function_result(cto.call_id, result=output)],
        )

    if item.type == "apply_patch_call":
        ap = cast(OutputItemApplyPatchToolCall, item)
        return Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    ap.call_id,
                    "apply_patch",
                    arguments=str(ap.operation),
                )
            ],
        )

    if item.type == "apply_patch_call_output":
        apo = cast(OutputItemApplyPatchToolCallOutput, item)
        return Message(
            role="tool",
            contents=[Content.from_function_result(apo.call_id, result=apo.output or "")],
        )

    if item.type == "oauth_consent_request":
        oauth = cast(OAuthConsentRequestOutputItem, item)
        return Message(
            role="assistant",
            contents=[Content.from_oauth_consent_request(oauth.consent_link)],
        )

    if item.type == "structured_outputs":
        so = cast(StructuredOutputsOutputItem, item)
        text = json.dumps(so.output) if not isinstance(so.output, str) else so.output
        return Message(role="assistant", contents=[Content.from_text(text)])

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
        logger.warning(f"Content type '{content.type}' is not supported yet. This is usually safe to ignore.")


# endregion
