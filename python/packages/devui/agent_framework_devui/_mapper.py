# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework message mapper implementation."""

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Union

from .models import (
    AgentFrameworkRequest,
    InputTokensDetails,
    OpenAIResponse,
    OutputTokensDetails,
    ResponseErrorEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionResultComplete,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningTextDeltaEvent,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
    ResponseTraceEventComplete,
    ResponseUsage,
    ResponseUsageEventComplete,
    ResponseWorkflowEventComplete,
)

logger = logging.getLogger(__name__)

# Type alias for all possible event types
EventType = Union[
    ResponseStreamEvent,
    ResponseWorkflowEventComplete,
    ResponseFunctionResultComplete,
    ResponseTraceEventComplete,
    ResponseUsageEventComplete,
]


class MessageMapper:
    """Maps Agent Framework messages/responses to OpenAI format."""

    def __init__(self) -> None:
        """Initialize Agent Framework message mapper."""
        self.sequence_counter = 0
        self._conversion_contexts: dict[int, dict[str, Any]] = {}

        # Register content type mappers for all 12 Agent Framework content types
        self.content_mappers = {
            "TextContent": self._map_text_content,
            "TextReasoningContent": self._map_reasoning_content,
            "FunctionCallContent": self._map_function_call_content,
            "FunctionResultContent": self._map_function_result_content,
            "ErrorContent": self._map_error_content,
            "UsageContent": self._map_usage_content,
            "DataContent": self._map_data_content,
            "UriContent": self._map_uri_content,
            "HostedFileContent": self._map_hosted_file_content,
            "HostedVectorStoreContent": self._map_hosted_vector_store_content,
            "FunctionApprovalRequestContent": self._map_approval_request_content,
            "FunctionApprovalResponseContent": self._map_approval_response_content,
        }

    async def convert_event(self, raw_event: Any, request: AgentFrameworkRequest) -> Sequence[Any]:
        """Convert a single Agent Framework event to OpenAI events.

        Args:
            raw_event: Agent Framework event (AgentRunResponseUpdate, WorkflowEvent, etc.)
            request: Original request for context

        Returns:
            List of OpenAI response stream events
        """
        context = self._get_or_create_context(request)

        # Handle error events
        if isinstance(raw_event, dict) and raw_event.get("type") == "error":
            return [await self._create_error_event(raw_event.get("message", "Unknown error"), context)]

        # Handle ResponseTraceEvent objects from our trace collector
        from .models import ResponseTraceEvent

        if isinstance(raw_event, ResponseTraceEvent):
            return [
                ResponseTraceEventComplete(
                    type="response.trace.complete",
                    data=raw_event.data,
                    item_id=context["item_id"],
                    sequence_number=self._next_sequence(context),
                )
            ]

        # Import Agent Framework types for proper isinstance checks
        try:
            from agent_framework import AgentRunResponseUpdate, WorkflowEvent

            # Handle agent updates (AgentRunResponseUpdate)
            if isinstance(raw_event, AgentRunResponseUpdate):
                return await self._convert_agent_update(raw_event, context)

            # Handle workflow events (any class that inherits from WorkflowEvent)
            if isinstance(raw_event, WorkflowEvent):
                return await self._convert_workflow_event(raw_event, context)

        except ImportError as e:
            logger.warning(f"Could not import Agent Framework types: {e}")
            # Fallback to attribute-based detection
            if hasattr(raw_event, "contents"):
                return await self._convert_agent_update(raw_event, context)
            if hasattr(raw_event, "__class__") and "Event" in raw_event.__class__.__name__:
                return await self._convert_workflow_event(raw_event, context)

        # Unknown event type
        return [await self._create_unknown_event(raw_event, context)]

    async def aggregate_to_response(self, events: Sequence[Any], request: AgentFrameworkRequest) -> OpenAIResponse:
        """Aggregate streaming events into final OpenAI response.

        Args:
            events: List of OpenAI stream events
            request: Original request for context

        Returns:
            Final aggregated OpenAI response
        """
        try:
            # Extract text content from events
            content_parts = []

            for event in events:
                # Extract delta text from ResponseTextDeltaEvent
                if hasattr(event, "delta") and hasattr(event, "type") and event.type == "response.output_text.delta":
                    content_parts.append(event.delta)

            # Combine content
            full_content = "".join(content_parts)

            # Create proper OpenAI Response
            response_output_text = ResponseOutputText(type="output_text", text=full_content, annotations=[])

            response_output_message = ResponseOutputMessage(
                type="message",
                role="assistant",
                content=[response_output_text],
                id=f"msg_{uuid.uuid4().hex[:8]}",
                status="completed",
            )

            # Create usage object
            input_token_count = len(str(request.input)) // 4 if request.input else 0
            output_token_count = len(full_content) // 4

            usage = ResponseUsage(
                input_tokens=input_token_count,
                output_tokens=output_token_count,
                total_tokens=input_token_count + output_token_count,
                input_tokens_details=InputTokensDetails(cached_tokens=0),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            )

            return OpenAIResponse(
                id=f"resp_{uuid.uuid4().hex[:12]}",
                object="response",
                created_at=datetime.now().timestamp(),
                model=request.model,
                output=[response_output_message],
                usage=usage,
                parallel_tool_calls=False,
                tool_choice="none",
                tools=[],
            )

        except Exception as e:
            logger.exception(f"Error aggregating response: {e}")
            return await self._create_error_response(str(e), request)

    def _get_or_create_context(self, request: AgentFrameworkRequest) -> dict[str, Any]:
        """Get or create conversion context for this request.

        Args:
            request: Request to get context for

        Returns:
            Conversion context dictionary
        """
        request_key = id(request)
        if request_key not in self._conversion_contexts:
            self._conversion_contexts[request_key] = {
                "sequence_counter": 0,
                "item_id": f"msg_{uuid.uuid4().hex[:8]}",
                "content_index": 0,
                "output_index": 0,
            }
        return self._conversion_contexts[request_key]

    def _next_sequence(self, context: dict[str, Any]) -> int:
        """Get next sequence number for events.

        Args:
            context: Conversion context

        Returns:
            Next sequence number
        """
        context["sequence_counter"] += 1
        return int(context["sequence_counter"])

    async def _convert_agent_update(self, update: Any, context: dict[str, Any]) -> Sequence[Any]:
        """Convert AgentRunResponseUpdate to OpenAI events using comprehensive content mapping.

        Args:
            update: Agent run response update
            context: Conversion context

        Returns:
            List of OpenAI response stream events
        """
        events: list[Any] = []

        try:
            # Handle different update types
            if not hasattr(update, "contents") or not update.contents:
                return events

            for content in update.contents:
                content_type = content.__class__.__name__

                if content_type in self.content_mappers:
                    mapped_events = await self.content_mappers[content_type](content, context)
                    if isinstance(mapped_events, list):
                        events.extend(mapped_events)
                    else:
                        events.append(mapped_events)
                else:
                    # Graceful fallback for unknown content types
                    events.append(await self._create_unknown_content_event(content, context))

                context["content_index"] += 1

        except Exception as e:
            logger.warning(f"Error converting agent update: {e}")
            events.append(await self._create_error_event(str(e), context))

        return events

    async def _convert_workflow_event(self, event: Any, context: dict[str, Any]) -> Sequence[Any]:
        """Convert workflow event to structured OpenAI events.

        Args:
            event: Workflow event
            context: Conversion context

        Returns:
            List of OpenAI response stream events
        """
        try:
            # Create structured workflow event
            workflow_event = ResponseWorkflowEventComplete(
                type="response.workflow_event.complete",
                data={
                    "event_type": event.__class__.__name__,
                    "data": getattr(event, "data", None),
                    "executor_id": getattr(event, "executor_id", None),
                    "timestamp": datetime.now().isoformat(),
                },
                executor_id=getattr(event, "executor_id", None),
                item_id=context["item_id"],
                output_index=context["output_index"],
                sequence_number=self._next_sequence(context),
            )

            return [workflow_event]

        except Exception as e:
            logger.warning(f"Error converting workflow event: {e}")
            return [await self._create_error_event(str(e), context)]

    # Content type mappers - implementing our comprehensive mapping plan

    async def _map_text_content(self, content: Any, context: dict[str, Any]) -> ResponseTextDeltaEvent:
        """Map TextContent to ResponseTextDeltaEvent."""
        return self._create_text_delta_event(content.text, context)

    async def _map_reasoning_content(self, content: Any, context: dict[str, Any]) -> ResponseReasoningTextDeltaEvent:
        """Map TextReasoningContent to ResponseReasoningTextDeltaEvent."""
        return ResponseReasoningTextDeltaEvent(
            type="response.reasoning_text.delta",
            delta=content.text,
            item_id=context["item_id"],
            output_index=context["output_index"],
            content_index=context["content_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_function_call_content(
        self, content: Any, context: dict[str, Any]
    ) -> list[ResponseFunctionCallArgumentsDeltaEvent]:
        """Map FunctionCallContent to ResponseFunctionCallArgumentsDeltaEvent(s)."""
        events = []

        # For streaming, need to chunk the arguments JSON
        args_str = json.dumps(content.arguments) if hasattr(content, "arguments") and content.arguments else "{}"

        # Chunk the JSON string for streaming
        for chunk in self._chunk_json_string(args_str):
            events.append(
                ResponseFunctionCallArgumentsDeltaEvent(
                    type="response.function_call_arguments.delta",
                    delta=chunk,
                    item_id=context["item_id"],
                    output_index=context["output_index"],
                    sequence_number=self._next_sequence(context),
                )
            )

        return events

    async def _map_function_result_content(
        self, content: Any, context: dict[str, Any]
    ) -> ResponseFunctionResultComplete:
        """Map FunctionResultContent to structured event."""
        return ResponseFunctionResultComplete(
            type="response.function_result.complete",
            data={
                "call_id": getattr(content, "call_id", f"call_{uuid.uuid4().hex[:8]}"),
                "result": getattr(content, "result", None),
                "status": "completed" if not getattr(content, "exception", None) else "failed",
                "exception": str(getattr(content, "exception", None)) if getattr(content, "exception", None) else None,
                "timestamp": datetime.now().isoformat(),
            },
            call_id=getattr(content, "call_id", f"call_{uuid.uuid4().hex[:8]}"),
            item_id=context["item_id"],
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_error_content(self, content: Any, context: dict[str, Any]) -> ResponseErrorEvent:
        """Map ErrorContent to ResponseErrorEvent."""
        return ResponseErrorEvent(
            type="error",
            message=getattr(content, "message", "Unknown error"),
            code=getattr(content, "error_code", None),
            param=None,
            sequence_number=self._next_sequence(context),
        )

    async def _map_usage_content(self, content: Any, context: dict[str, Any]) -> ResponseUsageEventComplete:
        """Map UsageContent to structured usage event."""
        # Store usage data in context for aggregation
        if "usage_data" not in context:
            context["usage_data"] = []
        context["usage_data"].append(content)

        return ResponseUsageEventComplete(
            type="response.usage.complete",
            data={
                "usage_data": getattr(content, "usage_data", {}),
                "total_tokens": getattr(content, "total_tokens", 0),
                "completion_tokens": getattr(content, "completion_tokens", 0),
                "prompt_tokens": getattr(content, "prompt_tokens", 0),
                "timestamp": datetime.now().isoformat(),
            },
            item_id=context["item_id"],
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_data_content(self, content: Any, context: dict[str, Any]) -> ResponseTraceEventComplete:
        """Map DataContent to structured trace event."""
        return ResponseTraceEventComplete(
            type="response.trace.complete",
            data={
                "content_type": "data",
                "data": getattr(content, "data", None),
                "mime_type": getattr(content, "mime_type", "application/octet-stream"),
                "size_bytes": len(str(getattr(content, "data", ""))) if getattr(content, "data", None) else 0,
                "timestamp": datetime.now().isoformat(),
            },
            item_id=context["item_id"],
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_uri_content(self, content: Any, context: dict[str, Any]) -> ResponseTraceEventComplete:
        """Map UriContent to structured trace event."""
        return ResponseTraceEventComplete(
            type="response.trace.complete",
            data={
                "content_type": "uri",
                "uri": getattr(content, "uri", ""),
                "mime_type": getattr(content, "mime_type", "text/plain"),
                "timestamp": datetime.now().isoformat(),
            },
            item_id=context["item_id"],
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_hosted_file_content(self, content: Any, context: dict[str, Any]) -> ResponseTraceEventComplete:
        """Map HostedFileContent to structured trace event."""
        return ResponseTraceEventComplete(
            type="response.trace.complete",
            data={
                "content_type": "hosted_file",
                "file_id": getattr(content, "file_id", "unknown"),
                "timestamp": datetime.now().isoformat(),
            },
            item_id=context["item_id"],
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_hosted_vector_store_content(
        self, content: Any, context: dict[str, Any]
    ) -> ResponseTraceEventComplete:
        """Map HostedVectorStoreContent to structured trace event."""
        return ResponseTraceEventComplete(
            type="response.trace.complete",
            data={
                "content_type": "hosted_vector_store",
                "vector_store_id": getattr(content, "vector_store_id", "unknown"),
                "timestamp": datetime.now().isoformat(),
            },
            item_id=context["item_id"],
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_approval_request_content(self, content: Any, context: dict[str, Any]) -> dict[str, Any]:
        """Map FunctionApprovalRequestContent to custom event."""
        return {
            "type": "response.function_approval.requested",
            "request_id": getattr(content, "id", "unknown"),
            "function_call": {
                "id": getattr(content.function_call, "call_id", "") if hasattr(content, "function_call") else "",
                "name": getattr(content.function_call, "name", "") if hasattr(content, "function_call") else "",
                "arguments": getattr(content.function_call, "arguments", {})
                if hasattr(content, "function_call")
                else {},
            },
            "item_id": context["item_id"],
            "output_index": context["output_index"],
            "sequence_number": self._next_sequence(context),
        }

    async def _map_approval_response_content(self, content: Any, context: dict[str, Any]) -> dict[str, Any]:
        """Map FunctionApprovalResponseContent to custom event."""
        return {
            "type": "response.function_approval.responded",
            "request_id": getattr(content, "request_id", "unknown"),
            "approved": getattr(content, "approved", False),
            "item_id": context["item_id"],
            "output_index": context["output_index"],
            "sequence_number": self._next_sequence(context),
        }

    # Helper methods

    def _create_text_delta_event(self, text: str, context: dict[str, Any]) -> ResponseTextDeltaEvent:
        """Create a ResponseTextDeltaEvent."""
        return ResponseTextDeltaEvent(
            type="response.output_text.delta",
            item_id=context["item_id"],
            output_index=context["output_index"],
            content_index=context["content_index"],
            delta=text,
            sequence_number=self._next_sequence(context),
            logprobs=[],
        )

    async def _create_error_event(self, message: str, context: dict[str, Any]) -> ResponseErrorEvent:
        """Create a ResponseErrorEvent."""
        return ResponseErrorEvent(
            type="error", message=message, code=None, param=None, sequence_number=self._next_sequence(context)
        )

    async def _create_unknown_event(self, event_data: Any, context: dict[str, Any]) -> ResponseStreamEvent:
        """Create event for unknown event types."""
        text = f"Unknown event: {event_data!s}\\n"
        return self._create_text_delta_event(text, context)

    async def _create_unknown_content_event(self, content: Any, context: dict[str, Any]) -> ResponseStreamEvent:
        """Create event for unknown content types."""
        content_type = content.__class__.__name__
        text = f"⚠️ Unknown content type: {content_type}\\n"
        return self._create_text_delta_event(text, context)

    def _chunk_json_string(self, json_str: str, chunk_size: int = 50) -> list[str]:
        """Chunk JSON string for streaming."""
        return [json_str[i : i + chunk_size] for i in range(0, len(json_str), chunk_size)]

    async def _create_error_response(self, error_message: str, request: AgentFrameworkRequest) -> OpenAIResponse:
        """Create error response."""
        error_text = f"Error: {error_message}"

        response_output_text = ResponseOutputText(type="output_text", text=error_text, annotations=[])

        response_output_message = ResponseOutputMessage(
            type="message",
            role="assistant",
            content=[response_output_text],
            id=f"msg_{uuid.uuid4().hex[:8]}",
            status="completed",
        )

        usage = ResponseUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        )

        return OpenAIResponse(
            id=f"resp_{uuid.uuid4().hex[:12]}",
            object="response",
            created_at=datetime.now().timestamp(),
            model=request.model,
            output=[response_output_message],
            usage=usage,
            parallel_tool_calls=False,
            tool_choice="none",
            tools=[],
        )
