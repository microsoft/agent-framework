# Copyright (c) Microsoft. All rights reserved.

"""Agent Framework message mapper implementation."""

import json
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Union
from uuid import uuid4

from openai.types.responses import (
    Response,
    ResponseContentPartAddedEvent,
    ResponseCreatedEvent,
    ResponseError,
    ResponseFailedEvent,
    ResponseInProgressEvent,
)

from .models import (
    AgentFrameworkRequest,
    CustomResponseOutputItemAddedEvent,
    CustomResponseOutputItemDoneEvent,
    ExecutorActionItem,
    InputTokensDetails,
    OpenAIResponse,
    OutputTokensDetails,
    ResponseCompletedEvent,
    ResponseErrorEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionResultComplete,
    ResponseFunctionToolCall,
    ResponseOutputData,
    ResponseOutputFile,
    ResponseOutputImage,
    ResponseOutputItemAddedEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningTextDeltaEvent,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
    ResponseTraceEventComplete,
    ResponseUsage,
    ResponseWorkflowEventComplete,
)

logger = logging.getLogger(__name__)

# Type alias for all possible event types
EventType = Union[
    ResponseStreamEvent,
    ResponseWorkflowEventComplete,
    ResponseOutputItemAddedEvent,
    ResponseTraceEventComplete,
]


def _serialize_content_recursive(value: Any) -> Any:
    """Recursively serialize Agent Framework Content objects to JSON-compatible values.

    This handles nested Content objects (like TextContent inside FunctionResultContent.result)
    that can't be directly serialized by json.dumps().

    Args:
        value: Value to serialize (can be Content object, dict, list, primitive, etc.)

    Returns:
        JSON-serializable version with all Content objects converted to dicts/primitives
    """
    # Handle None and basic JSON-serializable types
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    # Check if it's a SerializationMixin (includes all Content types)
    # Content objects have to_dict() method
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict", None)):
        try:
            return value.to_dict()
        except Exception as e:
            # If to_dict() fails, fall through to other methods
            logger.debug(f"Failed to serialize with to_dict(): {e}")

    # Handle dictionaries - recursively process values
    if isinstance(value, dict):
        return {key: _serialize_content_recursive(val) for key, val in value.items()}

    # Handle lists and tuples - recursively process elements
    if isinstance(value, (list, tuple)):
        serialized = [_serialize_content_recursive(item) for item in value]
        # For single-item lists containing text Content, extract just the text
        # This handles the MCP case where result = [TextContent(text="Hello")]
        # and we want output = "Hello" not output = '[{"type": "text", "text": "Hello"}]'
        if len(serialized) == 1 and isinstance(serialized[0], dict) and serialized[0].get("type") == "text":
            return serialized[0].get("text", "")
        return serialized

    # For other objects with model_dump(), try that
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump", None)):
        try:
            return value.model_dump()
        except Exception as e:
            logger.debug(f"Failed to serialize with model_dump(): {e}")

    # Return as-is and let json.dumps handle it (may raise TypeError for non-serializable types)
    return value


class MessageMapper:
    """Maps Agent Framework messages/responses to OpenAI format."""

    def __init__(self, max_contexts: int = 1000) -> None:
        """Initialize Agent Framework message mapper.

        Args:
            max_contexts: Maximum number of contexts to keep in memory (default: 1000)
        """
        self.sequence_counter = 0
        self._conversion_contexts: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._max_contexts = max_contexts

        # Track usage per request for final Response.usage (OpenAI standard)
        self._usage_accumulator: dict[str, dict[str, int]] = {}

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
                    type="response.trace.completed",
                    data=raw_event.data,
                    item_id=context["item_id"],
                    sequence_number=self._next_sequence(context),
                )
            ]

        # Handle Agent lifecycle events first
        from .models._openai_custom import AgentCompletedEvent, AgentFailedEvent, AgentStartedEvent

        if isinstance(raw_event, (AgentStartedEvent, AgentCompletedEvent, AgentFailedEvent)):
            return await self._convert_agent_lifecycle_event(raw_event, context)

        # Import Agent Framework types for proper isinstance checks
        try:
            from agent_framework import AgentRunResponse, AgentRunResponseUpdate, WorkflowEvent
            from agent_framework._workflows._events import AgentRunUpdateEvent

            # Handle AgentRunUpdateEvent - workflow event wrapping AgentRunResponseUpdate
            # This must be checked BEFORE generic WorkflowEvent check
            if isinstance(raw_event, AgentRunUpdateEvent):
                # Extract the AgentRunResponseUpdate from the event's data attribute
                if raw_event.data and isinstance(raw_event.data, AgentRunResponseUpdate):
                    return await self._convert_agent_update(raw_event.data, context)
                # If no data, treat as generic workflow event
                return await self._convert_workflow_event(raw_event, context)

            # Handle complete agent response (AgentRunResponse) - for non-streaming agent execution
            if isinstance(raw_event, AgentRunResponse):
                return await self._convert_agent_response(raw_event, context)

            # Handle agent updates (AgentRunResponseUpdate) - for direct agent execution
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

            # Get usage from accumulator (OpenAI standard)
            request_id = str(id(request))
            usage_data = self._usage_accumulator.get(request_id)

            if usage_data:
                usage = ResponseUsage(
                    input_tokens=usage_data["input_tokens"],
                    output_tokens=usage_data["output_tokens"],
                    total_tokens=usage_data["total_tokens"],
                    input_tokens_details=InputTokensDetails(cached_tokens=0),
                    output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
                )
                # Cleanup accumulator
                del self._usage_accumulator[request_id]
            else:
                # Fallback: estimate if no usage was tracked
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
                model=request.model or "devui",
                output=[response_output_message],
                usage=usage,
                parallel_tool_calls=False,
                tool_choice="none",
                tools=[],
            )

        except Exception as e:
            logger.exception(f"Error aggregating response: {e}")
            return await self._create_error_response(str(e), request)
        finally:
            # Cleanup: Remove context after aggregation to prevent memory leak
            # This handles the common case where streaming completes successfully
            request_key = id(request)
            if self._conversion_contexts.pop(request_key, None):
                logger.debug(f"Cleaned up context for request {request_key} after aggregation")

    def _get_or_create_context(self, request: AgentFrameworkRequest) -> dict[str, Any]:
        """Get or create conversion context for this request.

        Uses LRU eviction when max_contexts is reached to prevent unbounded memory growth.

        Args:
            request: Request to get context for

        Returns:
            Conversion context dictionary
        """
        request_key = id(request)

        if request_key not in self._conversion_contexts:
            # Evict oldest context if at capacity (LRU eviction)
            if len(self._conversion_contexts) >= self._max_contexts:
                evicted_key, _ = self._conversion_contexts.popitem(last=False)
                logger.debug(f"Evicted oldest context (key={evicted_key}) - at max capacity ({self._max_contexts})")

            self._conversion_contexts[request_key] = {
                "sequence_counter": 0,
                "item_id": f"msg_{uuid.uuid4().hex[:8]}",
                "content_index": 0,
                "output_index": 0,
                "request_id": str(request_key),  # For usage accumulation
                "request": request,  # Store the request for model name access
                # Track active function calls: {call_id: {name, item_id, args_chunks}}
                "active_function_calls": {},
            }
        else:
            # Move to end (mark as recently used for LRU)
            self._conversion_contexts.move_to_end(request_key)

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

    def _serialize_value(self, value: Any) -> Any:
        """Recursively serialize a value, handling complex nested objects.

        Handles:
        - Primitives (str, int, float, bool, None)
        - Collections (list, tuple, set, dict)
        - SerializationMixin objects (ChatMessage, etc.) - calls to_dict()
        - Pydantic models - calls model_dump()
        - Dataclasses - recursively serializes with asdict()
        - Enums - extracts value
        - datetime/date/UUID - converts to ISO string

        Args:
            value: Value to serialize

        Returns:
            JSON-serializable representation
        """
        from dataclasses import is_dataclass
        from datetime import date, datetime
        from enum import Enum
        from uuid import UUID

        # Handle None
        if value is None:
            return None

        # Handle primitives
        if isinstance(value, (str, int, float, bool)):
            return value

        # Handle datetime/date - convert to ISO format
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()

        # Handle UUID - convert to string
        if isinstance(value, UUID):
            return str(value)

        # Handle Enums - extract value
        if isinstance(value, Enum):
            return value.value

        # Handle lists/tuples/sets - recursively serialize elements
        if isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, set):
            return [self._serialize_value(item) for item in value]

        # Handle dicts - recursively serialize values
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}

        # Handle SerializationMixin (like ChatMessage) - call to_dict()
        if hasattr(value, "to_dict") and callable(getattr(value, "to_dict", None)):
            try:
                return value.to_dict()  # type: ignore[attr-defined, no-any-return]
            except Exception as e:
                logger.debug(f"Failed to serialize with to_dict(): {e}")
                return str(value)

        # Handle Pydantic models - call model_dump()
        if hasattr(value, "model_dump") and callable(getattr(value, "model_dump", None)):
            try:
                return value.model_dump()  # type: ignore[attr-defined, no-any-return]
            except Exception as e:
                logger.debug(f"Failed to serialize Pydantic model: {e}")
                return str(value)

        # Handle dataclasses - recursively serialize with asdict
        if is_dataclass(value) and not isinstance(value, type):
            try:
                from dataclasses import asdict

                # Use our custom serializer as dict_factory
                return asdict(value, dict_factory=lambda items: {k: self._serialize_value(v) for k, v in items})
            except Exception as e:
                logger.debug(f"Failed to serialize nested dataclass: {e}")
                return str(value)

        # Fallback: convert to string (for unknown types)
        logger.debug(f"Serializing unknown type {type(value).__name__} as string")
        return str(value)

    def _serialize_request_data(self, request_data: Any) -> dict[str, Any]:
        """Serialize RequestInfoMessage to dict for JSON transmission.

        Handles nested SerializationMixin objects (like ChatMessage) within dataclasses.

        Args:
            request_data: The RequestInfoMessage instance

        Returns:
            Serialized dict representation
        """
        from dataclasses import asdict, fields, is_dataclass

        if request_data is None:
            return {}

        # Handle dict first (most common)
        if isinstance(request_data, dict):
            return {k: self._serialize_value(v) for k, v in request_data.items()}

        # Handle dataclasses with nested SerializationMixin objects
        # We can't use asdict() directly because it doesn't handle ChatMessage
        if is_dataclass(request_data) and not isinstance(request_data, type):
            try:
                # Manually serialize each field to handle nested SerializationMixin
                result = {}
                for field in fields(request_data):
                    field_value = getattr(request_data, field.name)
                    result[field.name] = self._serialize_value(field_value)
                return result
            except Exception as e:
                logger.debug(f"Failed to serialize dataclass fields: {e}")
                # Fallback to asdict() if our custom serialization fails
                try:
                    return asdict(request_data)  # type: ignore[arg-type]
                except Exception as e2:
                    logger.debug(f"Failed to serialize dataclass with asdict(): {e2}")

        # Handle Pydantic models (have model_dump method)
        if hasattr(request_data, "model_dump") and callable(getattr(request_data, "model_dump", None)):
            try:
                return request_data.model_dump()  # type: ignore[attr-defined, no-any-return]
            except Exception as e:
                logger.debug(f"Failed to serialize Pydantic model: {e}")

        # Handle SerializationMixin (have to_dict method)
        if hasattr(request_data, "to_dict") and callable(getattr(request_data, "to_dict", None)):
            try:
                return request_data.to_dict()  # type: ignore[attr-defined, no-any-return]
            except Exception as e:
                logger.debug(f"Failed to serialize with to_dict(): {e}")

        # Fallback: string representation
        return {"raw": str(request_data)}

    async def _convert_agent_update(self, update: Any, context: dict[str, Any]) -> Sequence[Any]:
        """Convert agent text updates to proper content part events.

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

            # Check if we're streaming text content
            has_text_content = any(content.__class__.__name__ == "TextContent" for content in update.contents)

            # If we have text content and haven't created a message yet, create one
            if has_text_content and "current_message_id" not in context:
                message_id = f"msg_{uuid4().hex[:8]}"
                context["current_message_id"] = message_id
                context["output_index"] = context.get("output_index", -1) + 1

                # Add message output item
                events.append(
                    ResponseOutputItemAddedEvent(
                        type="response.output_item.added",
                        output_index=context["output_index"],
                        sequence_number=self._next_sequence(context),
                        item=ResponseOutputMessage(
                            type="message", id=message_id, role="assistant", content=[], status="in_progress"
                        ),
                    )
                )

                # Add content part for text
                context["content_index"] = 0
                events.append(
                    ResponseContentPartAddedEvent(
                        type="response.content_part.added",
                        output_index=context["output_index"],
                        content_index=context["content_index"],
                        item_id=message_id,
                        sequence_number=self._next_sequence(context),
                        part=ResponseOutputText(type="output_text", text="", annotations=[]),
                    )
                )

            # Process each content item
            for content in update.contents:
                content_type = content.__class__.__name__

                # Special handling for TextContent to use proper delta events
                if content_type == "TextContent" and "current_message_id" in context:
                    # Stream text content via proper delta events
                    events.append(
                        ResponseTextDeltaEvent(
                            type="response.output_text.delta",
                            output_index=context["output_index"],
                            content_index=context.get("content_index", 0),
                            item_id=context["current_message_id"],
                            delta=content.text,
                            logprobs=[],  # We don't have logprobs from Agent Framework
                            sequence_number=self._next_sequence(context),
                        )
                    )
                elif content_type in self.content_mappers:
                    # Use existing mappers for other content types
                    mapped_events = await self.content_mappers[content_type](content, context)
                    if mapped_events is not None:  # Handle None returns (e.g., UsageContent)
                        if isinstance(mapped_events, list):
                            events.extend(mapped_events)
                        else:
                            events.append(mapped_events)
                else:
                    # Graceful fallback for unknown content types
                    events.append(await self._create_unknown_content_event(content, context))

                # Don't increment content_index for text deltas within the same part
                if content_type != "TextContent":
                    context["content_index"] = context.get("content_index", 0) + 1

        except Exception as e:
            logger.warning(f"Error converting agent update: {e}")
            events.append(await self._create_error_event(str(e), context))

        return events

    async def _convert_agent_response(self, response: Any, context: dict[str, Any]) -> Sequence[Any]:
        """Convert complete AgentRunResponse to OpenAI events.

        This handles non-streaming agent execution where agent.run() returns
        a complete AgentRunResponse instead of streaming AgentRunResponseUpdate objects.

        Args:
            response: Agent run response (AgentRunResponse)
            context: Conversion context

        Returns:
            List of OpenAI response stream events
        """
        events: list[Any] = []

        try:
            # Extract all messages from the response
            messages = getattr(response, "messages", [])

            # Convert each message's contents to streaming events
            for message in messages:
                if hasattr(message, "contents") and message.contents:
                    for content in message.contents:
                        content_type = content.__class__.__name__

                        if content_type in self.content_mappers:
                            mapped_events = await self.content_mappers[content_type](content, context)
                            if mapped_events is not None:  # Handle None returns (e.g., UsageContent)
                                if isinstance(mapped_events, list):
                                    events.extend(mapped_events)
                                else:
                                    events.append(mapped_events)
                        else:
                            # Graceful fallback for unknown content types
                            events.append(await self._create_unknown_content_event(content, context))

                        context["content_index"] += 1

            # Add usage information if present
            usage_details = getattr(response, "usage_details", None)
            if usage_details:
                from agent_framework import UsageContent

                usage_content = UsageContent(details=usage_details)
                await self._map_usage_content(usage_content, context)
                # Note: _map_usage_content returns None - it accumulates usage for final Response.usage

        except Exception as e:
            logger.warning(f"Error converting agent response: {e}")
            events.append(await self._create_error_event(str(e), context))

        return events

    async def _convert_agent_lifecycle_event(self, event: Any, context: dict[str, Any]) -> Sequence[Any]:
        """Convert agent lifecycle events to OpenAI response events.

        Args:
            event: AgentStartedEvent, AgentCompletedEvent, or AgentFailedEvent
            context: Conversion context

        Returns:
            List of OpenAI response stream events
        """
        from .models._openai_custom import AgentCompletedEvent, AgentFailedEvent, AgentStartedEvent

        try:
            # Get model name from request or use 'devui' as default
            request_obj = context.get("request")
            model_name = request_obj.model if request_obj and request_obj.model else "devui"

            if isinstance(event, AgentStartedEvent):
                execution_id = f"agent_{uuid4().hex[:12]}"
                context["execution_id"] = execution_id

                # Create Response object
                response_obj = Response(
                    id=f"resp_{execution_id}",
                    object="response",
                    created_at=float(time.time()),
                    model=model_name,
                    output=[],
                    status="in_progress",
                    parallel_tool_calls=False,
                    tool_choice="none",
                    tools=[],
                )

                # Emit both created and in_progress events
                return [
                    ResponseCreatedEvent(
                        type="response.created", sequence_number=self._next_sequence(context), response=response_obj
                    ),
                    ResponseInProgressEvent(
                        type="response.in_progress", sequence_number=self._next_sequence(context), response=response_obj
                    ),
                ]

            if isinstance(event, AgentCompletedEvent):
                execution_id = context.get("execution_id", f"agent_{uuid4().hex[:12]}")

                response_obj = Response(
                    id=f"resp_{execution_id}",
                    object="response",
                    created_at=float(time.time()),
                    model=model_name,
                    output=[],
                    status="completed",
                    parallel_tool_calls=False,
                    tool_choice="none",
                    tools=[],
                )

                return [
                    ResponseCompletedEvent(
                        type="response.completed", sequence_number=self._next_sequence(context), response=response_obj
                    )
                ]

            if isinstance(event, AgentFailedEvent):
                execution_id = context.get("execution_id", f"agent_{uuid4().hex[:12]}")

                # Create error object
                response_error = ResponseError(
                    message=str(event.error) if event.error else "Unknown error", code="server_error"
                )

                response_obj = Response(
                    id=f"resp_{execution_id}",
                    object="response",
                    created_at=float(time.time()),
                    model=model_name,
                    output=[],
                    status="failed",
                    error=response_error,
                    parallel_tool_calls=False,
                    tool_choice="none",
                    tools=[],
                )

                return [
                    ResponseFailedEvent(
                        type="response.failed", sequence_number=self._next_sequence(context), response=response_obj
                    )
                ]

            return []

        except Exception as e:
            logger.warning(f"Error converting agent lifecycle event: {e}")
            return [await self._create_error_event(str(e), context)]

    async def _convert_workflow_event(self, event: Any, context: dict[str, Any]) -> Sequence[Any]:
        """Convert workflow events to standard OpenAI event objects.

        Args:
            event: Workflow event
            context: Conversion context

        Returns:
            List of OpenAI response stream events
        """
        try:
            event_class = event.__class__.__name__

            # Response-level events - construct proper OpenAI objects
            if event_class == "WorkflowStartedEvent":
                workflow_id = getattr(event, "workflow_id", str(uuid4()))
                context["workflow_id"] = workflow_id

                # Import Response type for proper construction
                from openai.types.responses import Response

                # Return proper OpenAI event objects
                events: list[Any] = []

                # Get model name from request or use 'devui' as default
                request_obj = context.get("request")
                model_name = request_obj.model if request_obj and request_obj.model else "devui"

                # Create a full Response object with all required fields
                response_obj = Response(
                    id=f"resp_{workflow_id}",
                    object="response",
                    created_at=float(time.time()),
                    model=model_name,
                    output=[],  # Empty output list initially
                    status="in_progress",
                    # Required fields with safe defaults
                    parallel_tool_calls=False,
                    tool_choice="none",
                    tools=[],
                )

                # First emit response.created
                events.append(
                    ResponseCreatedEvent(
                        type="response.created", sequence_number=self._next_sequence(context), response=response_obj
                    )
                )

                # Then emit response.in_progress (reuse same response object)
                events.append(
                    ResponseInProgressEvent(
                        type="response.in_progress", sequence_number=self._next_sequence(context), response=response_obj
                    )
                )

                return events

            # Handle WorkflowOutputEvent separately to preserve output data
            if event_class == "WorkflowOutputEvent":
                output_data = getattr(event, "data", None)
                source_executor_id = getattr(event, "source_executor_id", "unknown")

                if output_data is not None:
                    # Import required types
                    from openai.types.responses import ResponseOutputMessage, ResponseOutputText
                    from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent

                    # Increment output index for each yield_output
                    context["output_index"] = context.get("output_index", -1) + 1

                    # Extract text from output data based on type
                    text = None
                    if hasattr(output_data, "__class__") and output_data.__class__.__name__ == "ChatMessage":
                        # Handle ChatMessage (from Magentic and AgentExecutor with output_response=True)
                        text = getattr(output_data, "text", None)
                        if not text:
                            # Fallback to string representation
                            text = str(output_data)
                    elif isinstance(output_data, str):
                        # String output
                        text = output_data
                    else:
                        # Object/dict/list → JSON string
                        try:
                            text = json.dumps(output_data, indent=2)
                        except (TypeError, ValueError):
                            # Fallback to string representation if not JSON serializable
                            text = str(output_data)

                    # Create output message with text content
                    text_content = ResponseOutputText(type="output_text", text=text, annotations=[])

                    output_message = ResponseOutputMessage(
                        type="message",
                        id=f"msg_{uuid4().hex[:8]}",
                        role="assistant",
                        content=[text_content],
                        status="completed",
                    )

                    # Emit output_item.added for each yield_output
                    logger.debug(
                        f"WorkflowOutputEvent converted to output_item.added "
                        f"(executor: {source_executor_id}, length: {len(text)})"
                    )
                    return [
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            item=output_message,
                            output_index=context["output_index"],
                            sequence_number=self._next_sequence(context),
                        )
                    ]

            # Handle WorkflowCompletedEvent - emit response.completed
            if event_class == "WorkflowCompletedEvent":
                workflow_id = context.get("workflow_id", str(uuid4()))

                # Import Response type for proper construction
                from openai.types.responses import Response

                # Get model name from request or use 'devui' as default
                request_obj = context.get("request")
                model_name = request_obj.model if request_obj and request_obj.model else "devui"

                # Create a full Response object for completed state
                response_obj = Response(
                    id=f"resp_{workflow_id}",
                    object="response",
                    created_at=float(time.time()),
                    model=model_name,
                    output=[],  # Output items already sent via output_item.added events
                    status="completed",
                    parallel_tool_calls=False,
                    tool_choice="none",
                    tools=[],
                )

                return [
                    ResponseCompletedEvent(
                        type="response.completed", sequence_number=self._next_sequence(context), response=response_obj
                    )
                ]

            if event_class == "WorkflowFailedEvent":
                workflow_id = context.get("workflow_id", str(uuid4()))
                error_info = getattr(event, "error", None)

                # Import Response and ResponseError types
                from openai.types.responses import Response, ResponseError

                # Get model name from request or use 'devui' as default
                request_obj = context.get("request")
                model_name = request_obj.model if request_obj and request_obj.model else "devui"

                # Create error object
                error_message = str(error_info) if error_info else "Unknown error"

                # Create ResponseError object (code must be one of the allowed values)
                response_error = ResponseError(
                    message=error_message,
                    code="server_error",  # Use generic server_error code for workflow failures
                )

                # Create a full Response object for failed state
                response_obj = Response(
                    id=f"resp_{workflow_id}",
                    object="response",
                    created_at=float(time.time()),
                    model=model_name,
                    output=[],
                    status="failed",
                    error=response_error,
                    parallel_tool_calls=False,
                    tool_choice="none",
                    tools=[],
                )

                return [
                    ResponseFailedEvent(
                        type="response.failed", sequence_number=self._next_sequence(context), response=response_obj
                    )
                ]

            # Executor-level events (output items)
            if event_class == "ExecutorInvokedEvent":
                executor_id = getattr(event, "executor_id", "unknown")
                item_id = f"exec_{executor_id}_{uuid4().hex[:8]}"
                context[f"exec_item_{executor_id}"] = item_id
                context["output_index"] = context.get("output_index", -1) + 1

                # Create ExecutorActionItem with proper type
                executor_item = ExecutorActionItem(
                    type="executor_action",
                    id=item_id,
                    executor_id=executor_id,
                    status="in_progress",
                    metadata=getattr(event, "metadata", {}),
                )

                # Use our custom event type that accepts ExecutorActionItem
                return [
                    CustomResponseOutputItemAddedEvent(
                        type="response.output_item.added",
                        output_index=context["output_index"],
                        sequence_number=self._next_sequence(context),
                        item=executor_item,
                    )
                ]

            if event_class == "ExecutorCompletedEvent":
                executor_id = getattr(event, "executor_id", "unknown")
                item_id = context.get(f"exec_item_{executor_id}", f"exec_{executor_id}_unknown")

                # Create ExecutorActionItem with completed status
                # ExecutorCompletedEvent uses 'data' field, not 'result'
                executor_item = ExecutorActionItem(
                    type="executor_action",
                    id=item_id,
                    executor_id=executor_id,
                    status="completed",
                    result=getattr(event, "data", None),
                )

                # Use our custom event type
                return [
                    CustomResponseOutputItemDoneEvent(
                        type="response.output_item.done",
                        output_index=context.get("output_index", 0),
                        sequence_number=self._next_sequence(context),
                        item=executor_item,
                    )
                ]

            if event_class == "ExecutorFailedEvent":
                executor_id = getattr(event, "executor_id", "unknown")
                item_id = context.get(f"exec_item_{executor_id}", f"exec_{executor_id}_unknown")
                error_info = getattr(event, "error", None)

                # Create ExecutorActionItem with failed status
                executor_item = ExecutorActionItem(
                    type="executor_action",
                    id=item_id,
                    executor_id=executor_id,
                    status="failed",
                    error={"message": str(error_info)} if error_info else None,
                )

                # Use our custom event type
                return [
                    CustomResponseOutputItemDoneEvent(
                        type="response.output_item.done",
                        output_index=context.get("output_index", 0),
                        sequence_number=self._next_sequence(context),
                        item=executor_item,
                    )
                ]

            # Handle RequestInfoEvent specially - emit as HIL event with schema
            if event_class == "RequestInfoEvent":
                from .models._openai_custom import ResponseRequestInfoEvent

                request_id = getattr(event, "request_id", "")
                source_executor_id = getattr(event, "source_executor_id", "")
                request_type_class = getattr(event, "request_type", None)
                request_data = getattr(event, "data", None)

                logger.info("📨 [MAPPER] Processing RequestInfoEvent")
                logger.info(f"   request_id: {request_id}")
                logger.info(f"   source_executor_id: {source_executor_id}")
                logger.info(f"   request_type_class: {request_type_class}")
                logger.info(f"   request_data: {request_data}")

                # Serialize request data
                serialized_data = self._serialize_request_data(request_data)
                logger.info(f"   serialized_data: {serialized_data}")

                # Get request type name for debugging
                request_type_name = "Unknown"
                if request_type_class:
                    request_type_name = f"{request_type_class.__module__}:{request_type_class.__name__}"

                # Get response schema that was attached by executor
                # This tells the UI what format to collect from the user
                response_schema = getattr(event, "_response_schema", None)
                if not response_schema:
                    # Fallback to string if somehow not set (shouldn't happen with current executor enrichment)
                    logger.warning(f"⚠️  Response schema not found for {request_type_name}, using default")
                    response_schema = {"type": "string"}
                else:
                    logger.info(f"   response_schema: {response_schema}")

                # Wrap primitive schemas in object for form rendering
                # The UI's SchemaFormRenderer expects an object with properties
                if response_schema.get("type") in ["string", "integer", "number", "boolean"]:
                    # Wrap primitive type in object with "response" field
                    wrapped_schema = {
                        "type": "object",
                        "properties": {"response": response_schema},
                        "required": ["response"],
                    }
                    logger.info("   wrapped primitive schema in object")
                else:
                    wrapped_schema = response_schema

                # Create HIL request event with response schema
                hil_event = ResponseRequestInfoEvent(
                    type="response.request_info.requested",
                    request_id=request_id,
                    source_executor_id=source_executor_id,
                    request_type=request_type_name,
                    request_data=serialized_data,
                    request_schema=wrapped_schema,  # Send wrapped schema for form rendering
                    response_schema=response_schema,  # Keep original for reference
                    item_id=context["item_id"],
                    output_index=context.get("output_index", 0),
                    sequence_number=self._next_sequence(context),
                    timestamp=datetime.now().isoformat(),
                )

                logger.info("✅ [MAPPER] Created ResponseRequestInfoEvent:")
                logger.info(f"   type: {hil_event.type}")
                logger.info(f"   request_id: {hil_event.request_id}")
                logger.info(f"   sequence_number: {hil_event.sequence_number}")

                return [hil_event]

            # Handle other informational workflow events (status, warnings, errors)
            if event_class in ["WorkflowStatusEvent", "WorkflowWarningEvent", "WorkflowErrorEvent"]:
                # These are informational events that don't map to OpenAI lifecycle events
                # Convert them to trace events for debugging visibility
                event_data: dict[str, Any] = {}

                # Extract relevant data based on event type
                if event_class == "WorkflowStatusEvent":
                    event_data["state"] = str(getattr(event, "state", "unknown"))
                elif event_class == "WorkflowWarningEvent":
                    event_data["message"] = str(getattr(event, "message", ""))
                elif event_class == "WorkflowErrorEvent":
                    event_data["message"] = str(getattr(event, "message", ""))
                    event_data["error"] = str(getattr(event, "error", ""))

                # Create a trace event for debugging
                trace_event = ResponseTraceEventComplete(
                    type="response.trace.completed",
                    data={
                        "trace_type": "workflow_info",
                        "event_type": event_class,
                        "data": event_data,
                        "timestamp": datetime.now().isoformat(),
                    },
                    span_id=f"workflow_info_{uuid4().hex[:8]}",
                    item_id=context["item_id"],
                    output_index=context.get("output_index", 0),
                    sequence_number=self._next_sequence(context),
                )

                return [trace_event]

            # Handle Magentic-specific events
            if event_class == "MagenticAgentDeltaEvent":
                agent_id = getattr(event, "agent_id", "unknown_agent")
                text = getattr(event, "text", None)

                if text:
                    events = []

                    # Track Magentic agent messages separately from regular messages
                    # Use timestamp to ensure uniqueness for multiple runs of same agent
                    magentic_key = f"magentic_message_{agent_id}"

                    # Check if this is the first delta from this agent (need to create message container)
                    if magentic_key not in context:
                        # Create a unique message ID for this agent's streaming session
                        message_id = f"msg_{agent_id}_{uuid4().hex[:8]}"
                        context[magentic_key] = message_id
                        context["output_index"] = context.get("output_index", -1) + 1

                        # Import required types
                        from openai.types.responses import ResponseOutputMessage, ResponseOutputText
                        from openai.types.responses.response_content_part_added_event import (
                            ResponseContentPartAddedEvent,
                        )
                        from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent

                        # Emit message output item (container for the agent's message)
                        # This matches what _convert_agent_update does for regular agents
                        events.append(
                            ResponseOutputItemAddedEvent(
                                type="response.output_item.added",
                                output_index=context["output_index"],
                                sequence_number=self._next_sequence(context),
                                item=ResponseOutputMessage(
                                    type="message",
                                    id=message_id,
                                    role="assistant",
                                    content=[],
                                    status="in_progress",
                                    # Add metadata to identify this as a Magentic agent message
                                    metadata={"agent_id": agent_id, "source": "magentic"},  # type: ignore[call-arg]
                                ),
                            )
                        )

                        # Add content part for text (establishes the text container)
                        events.append(
                            ResponseContentPartAddedEvent(
                                type="response.content_part.added",
                                output_index=context["output_index"],
                                content_index=0,
                                item_id=message_id,
                                sequence_number=self._next_sequence(context),
                                part=ResponseOutputText(type="output_text", text="", annotations=[]),
                            )
                        )

                    # Get the message ID for this agent
                    message_id = context[magentic_key]

                    # Emit text delta event using the message ID (matches regular agent behavior)
                    events.append(
                        ResponseTextDeltaEvent(
                            type="response.output_text.delta",
                            output_index=context["output_index"],
                            content_index=0,  # Always 0 for single text content
                            item_id=message_id,
                            delta=text,
                            logprobs=[],
                            sequence_number=self._next_sequence(context),
                        )
                    )
                    return events

                # Handle function calls from Magentic agents
                if getattr(event, "function_call_id", None) and getattr(event, "function_call_name", None):
                    # Handle function call initiation
                    function_call_id = getattr(event, "function_call_id", None)
                    function_call_name = getattr(event, "function_call_name", None)
                    function_call_arguments = getattr(event, "function_call_arguments", None)

                    # Track function call for accumulating arguments
                    context["active_function_calls"][function_call_id] = {
                        "item_id": function_call_id,
                        "name": function_call_name,
                        "arguments_chunks": [],
                    }

                    # Emit function call output item
                    return [
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            item=ResponseFunctionToolCall(
                                id=function_call_id,
                                call_id=function_call_id,
                                name=function_call_name,
                                arguments=json.dumps(function_call_arguments) if function_call_arguments else "",
                                type="function_call",
                                status="in_progress",
                            ),
                            output_index=context["output_index"],
                            sequence_number=self._next_sequence(context),
                        )
                    ]

                # For other non-text deltas, emit as trace for debugging
                return [
                    ResponseTraceEventComplete(
                        type="response.trace.completed",
                        data={
                            "trace_type": "magentic_delta",
                            "agent_id": agent_id,
                            "function_call_id": getattr(event, "function_call_id", None),
                            "function_call_name": getattr(event, "function_call_name", None),
                            "function_result_id": getattr(event, "function_result_id", None),
                            "timestamp": datetime.now().isoformat(),
                        },
                        span_id=f"magentic_delta_{uuid4().hex[:8]}",
                        item_id=context["item_id"],
                        output_index=context.get("output_index", 0),
                        sequence_number=self._next_sequence(context),
                    )
                ]

            if event_class == "MagenticAgentMessageEvent":
                agent_id = getattr(event, "agent_id", "unknown_agent")
                message = getattr(event, "message", None)

                # Track Magentic agent messages
                magentic_key = f"magentic_message_{agent_id}"

                # Check if we were streaming for this agent
                if magentic_key in context:
                    # Mark the streaming message as complete
                    message_id = context[magentic_key]

                    # Import required types
                    from openai.types.responses import ResponseOutputMessage
                    from openai.types.responses.response_output_item_done_event import ResponseOutputItemDoneEvent

                    # Extract text from ChatMessage for the completed message
                    text = None
                    if message and hasattr(message, "text"):
                        text = message.text

                    # Emit output_item.done to mark message as complete
                    events = [
                        ResponseOutputItemDoneEvent(
                            type="response.output_item.done",
                            output_index=context["output_index"],
                            sequence_number=self._next_sequence(context),
                            item=ResponseOutputMessage(
                                type="message",
                                id=message_id,
                                role="assistant",
                                content=[],  # Content already streamed via deltas
                                status="completed",
                                metadata={"agent_id": agent_id, "source": "magentic"},  # type: ignore[call-arg]
                            ),
                        )
                    ]

                    # Clean up context for this agent
                    del context[magentic_key]

                    logger.debug(f"MagenticAgentMessageEvent from {agent_id} marked streaming message as complete")
                    return events
                # No streaming occurred, create a complete message (shouldn't happen normally)
                # Extract text from ChatMessage
                text = None
                if message and hasattr(message, "text"):
                    text = message.text

                if text:
                    # Emit as output item for this agent
                    from openai.types.responses import ResponseOutputMessage, ResponseOutputText
                    from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent

                    context["output_index"] = context.get("output_index", -1) + 1

                    text_content = ResponseOutputText(type="output_text", text=text, annotations=[])

                    output_message = ResponseOutputMessage(
                        type="message",
                        id=f"msg_{agent_id}_{uuid4().hex[:8]}",
                        role="assistant",
                        content=[text_content],
                        status="completed",
                        metadata={"agent_id": agent_id, "source": "magentic"},  # type: ignore[call-arg]
                    )

                    logger.debug(
                        f"MagenticAgentMessageEvent from {agent_id} converted to output_item.added (non-streaming)"
                    )
                    return [
                        ResponseOutputItemAddedEvent(
                            type="response.output_item.added",
                            item=output_message,
                            output_index=context["output_index"],
                            sequence_number=self._next_sequence(context),
                        )
                    ]

            if event_class == "MagenticOrchestratorMessageEvent":
                orchestrator_id = getattr(event, "orchestrator_id", "orchestrator")
                message = getattr(event, "message", None)
                kind = getattr(event, "kind", "unknown")

                # Extract text from ChatMessage
                text = None
                if message and hasattr(message, "text"):
                    text = message.text

                # Emit as trace event for orchestrator messages (typically task ledger, instructions)
                return [
                    ResponseTraceEventComplete(
                        type="response.trace.completed",
                        data={
                            "trace_type": "magentic_orchestrator",
                            "orchestrator_id": orchestrator_id,
                            "kind": kind,
                            "text": text or str(message),
                            "timestamp": datetime.now().isoformat(),
                        },
                        span_id=f"magentic_orch_{uuid4().hex[:8]}",
                        item_id=context["item_id"],
                        output_index=context.get("output_index", 0),
                        sequence_number=self._next_sequence(context),
                    )
                ]

            # For unknown/legacy events, still emit as workflow event for backward compatibility
            # Get event data and serialize if it's a SerializationMixin
            raw_event_data = getattr(event, "data", None)
            serialized_event_data: dict[str, Any] | str | None = raw_event_data
            if raw_event_data is not None and hasattr(raw_event_data, "to_dict"):
                # SerializationMixin objects - convert to dict for JSON serialization
                try:
                    serialized_event_data = raw_event_data.to_dict()
                except Exception as e:
                    logger.debug(f"Failed to serialize event data with to_dict(): {e}")
                    serialized_event_data = str(raw_event_data)

            # Create structured workflow event (keeping for backward compatibility)
            workflow_event = ResponseWorkflowEventComplete(
                type="response.workflow_event.completed",
                data={
                    "event_type": event.__class__.__name__,
                    "data": serialized_event_data,
                    "executor_id": getattr(event, "executor_id", None),
                    "timestamp": datetime.now().isoformat(),
                },
                executor_id=getattr(event, "executor_id", None),
                item_id=context["item_id"],
                output_index=context["output_index"],
                sequence_number=self._next_sequence(context),
            )

            logger.debug(f"Unhandled workflow event type: {event_class}, emitting as legacy workflow event")
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
    ) -> list[ResponseFunctionCallArgumentsDeltaEvent | ResponseOutputItemAddedEvent]:
        """Map FunctionCallContent to OpenAI events following Responses API spec.

        Agent Framework emits FunctionCallContent in two patterns:
        1. First event: call_id + name + empty/no arguments
        2. Subsequent events: empty call_id/name + argument chunks

        We emit:
        1. response.output_item.added (with full metadata) for the first event
        2. response.function_call_arguments.delta (referencing item_id) for chunks
        """
        events: list[ResponseFunctionCallArgumentsDeltaEvent | ResponseOutputItemAddedEvent] = []

        # CASE 1: New function call (has call_id and name)
        # This is the first event that establishes the function call
        if content.call_id and content.name:
            # Use call_id as item_id (simpler, and call_id uniquely identifies the call)
            item_id = content.call_id

            # Track this function call for later argument deltas
            context["active_function_calls"][content.call_id] = {
                "item_id": item_id,
                "name": content.name,
                "arguments_chunks": [],
            }

            logger.debug(f"New function call: {content.name} (call_id={content.call_id})")

            # Emit response.output_item.added event per OpenAI spec
            events.append(
                ResponseOutputItemAddedEvent(
                    type="response.output_item.added",
                    item=ResponseFunctionToolCall(
                        id=content.call_id,  # Use call_id as the item id
                        call_id=content.call_id,
                        name=content.name,
                        arguments="",  # Empty initially, will be filled by deltas
                        type="function_call",
                        status="in_progress",
                    ),
                    output_index=context["output_index"],
                    sequence_number=self._next_sequence(context),
                )
            )

        # CASE 2: Argument deltas (content has arguments, possibly without call_id/name)
        if content.arguments:
            # Find the active function call for these arguments
            active_call = self._get_active_function_call(content, context)

            if active_call:
                item_id = active_call["item_id"]

                # Convert arguments to string if it's a dict (Agent Framework may send either)
                delta_str = content.arguments if isinstance(content.arguments, str) else json.dumps(content.arguments)

                # Emit argument delta referencing the item_id
                events.append(
                    ResponseFunctionCallArgumentsDeltaEvent(
                        type="response.function_call_arguments.delta",
                        delta=delta_str,
                        item_id=item_id,
                        output_index=context["output_index"],
                        sequence_number=self._next_sequence(context),
                    )
                )

                # Track chunk for debugging
                active_call["arguments_chunks"].append(delta_str)
            else:
                logger.warning(f"Received function call arguments without active call: {content.arguments[:50]}...")

        return events

    def _get_active_function_call(self, content: Any, context: dict[str, Any]) -> dict[str, Any] | None:
        """Find the active function call for this content.

        Uses call_id if present, otherwise falls back to most recent call.
        Necessary because Agent Framework may send argument chunks without call_id.

        Args:
            content: FunctionCallContent with possible call_id
            context: Conversion context with active_function_calls

        Returns:
            Active call dict or None
        """
        active_calls: dict[str, dict[str, Any]] = context["active_function_calls"]

        # If content has call_id, use it to find the exact call
        if hasattr(content, "call_id") and content.call_id:
            result = active_calls.get(content.call_id)
            return result if result is not None else None

        # Otherwise, use the most recent call (last one added)
        # This handles the case where Agent Framework sends argument chunks
        # without call_id in subsequent events
        if active_calls:
            return list(active_calls.values())[-1]

        return None

    async def _map_function_result_content(
        self, content: Any, context: dict[str, Any]
    ) -> ResponseFunctionResultComplete:
        """Map FunctionResultContent to DevUI custom event.

        DevUI extension: The OpenAI Responses API doesn't stream function execution results
        (in OpenAI's model, the application executes functions, not the API).
        """
        # Get call_id from content
        call_id = getattr(content, "call_id", None)
        if not call_id:
            call_id = f"call_{uuid.uuid4().hex[:8]}"

        # Extract result
        result = getattr(content, "result", None)
        exception = getattr(content, "exception", None)

        # Convert result to string, handling nested Content objects from MCP tools
        if isinstance(result, str):
            output = result
        elif result is not None:
            # Recursively serialize any nested Content objects (e.g., from MCP tools)
            serialized = _serialize_content_recursive(result)
            # Convert to JSON string if still not a string
            output = serialized if isinstance(serialized, str) else json.dumps(serialized)
        else:
            output = ""

        # Determine status based on exception
        status = "incomplete" if exception else "completed"

        # Generate item_id
        item_id = f"item_{uuid.uuid4().hex[:8]}"

        # Return DevUI custom event
        return ResponseFunctionResultComplete(
            type="response.function_result.complete",
            call_id=call_id,
            output=output,
            status=status,
            item_id=item_id,
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
            timestamp=datetime.now().isoformat(),
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

    async def _map_usage_content(self, content: Any, context: dict[str, Any]) -> None:
        """Accumulate usage data for final Response.usage field.

        OpenAI does NOT stream usage events. Usage appears only in final Response.
        This method accumulates usage data per request for later inclusion in Response.usage.

        Returns:
            None - no event emitted (usage goes in final Response.usage)
        """
        # Extract usage from UsageContent.details (UsageDetails object)
        details = getattr(content, "details", None)
        total_tokens = getattr(details, "total_token_count", 0) or 0
        prompt_tokens = getattr(details, "input_token_count", 0) or 0
        completion_tokens = getattr(details, "output_token_count", 0) or 0

        # Accumulate for final Response.usage
        request_id = context.get("request_id", "default")
        if request_id not in self._usage_accumulator:
            self._usage_accumulator[request_id] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        self._usage_accumulator[request_id]["input_tokens"] += prompt_tokens
        self._usage_accumulator[request_id]["output_tokens"] += completion_tokens
        self._usage_accumulator[request_id]["total_tokens"] += total_tokens

        logger.debug(f"Accumulated usage for {request_id}: {self._usage_accumulator[request_id]}")

        # NO EVENT RETURNED - usage goes in final Response only
        return

    async def _map_data_content(
        self, content: Any, context: dict[str, Any]
    ) -> ResponseOutputItemAddedEvent | ResponseTraceEventComplete:
        """Map DataContent to proper output item (image/file/data) or fallback to trace.

        Maps Agent Framework DataContent to appropriate output types:
        - Images (image/*) → ResponseOutputImage
        - Common files (pdf, audio, video) → ResponseOutputFile
        - Generic data → ResponseOutputData
        - Unknown/debugging content → ResponseTraceEventComplete (fallback)
        """
        mime_type = getattr(content, "mime_type", "application/octet-stream")
        item_id = f"item_{uuid.uuid4().hex[:16]}"

        # Extract data/uri
        data_value = getattr(content, "data", None)
        uri_value = getattr(content, "uri", None)

        # Handle images
        if mime_type.startswith("image/"):
            # Prefer URI, but create data URI from data if needed
            if uri_value:
                image_url = uri_value
            elif data_value:
                # Convert bytes to base64 data URI
                import base64

                if isinstance(data_value, bytes):
                    b64_data = base64.b64encode(data_value).decode("utf-8")
                else:
                    b64_data = str(data_value)
                image_url = f"data:{mime_type};base64,{b64_data}"
            else:
                # No data available, fallback to trace
                logger.warning(f"DataContent with {mime_type} has no data or uri, falling back to trace")
                return ResponseTraceEventComplete(
                    type="response.trace.completed",
                    data={"content_type": "data", "mime_type": mime_type, "error": "No data or uri"},
                    item_id=context["item_id"],
                    output_index=context["output_index"],
                    sequence_number=self._next_sequence(context),
                )

            return ResponseOutputItemAddedEvent(
                type="response.output_item.added",
                item=ResponseOutputImage(  # type: ignore[arg-type]
                    id=item_id,
                    type="output_image",
                    image_url=image_url,
                    mime_type=mime_type,
                    alt_text=None,
                ),
                output_index=context["output_index"],
                sequence_number=self._next_sequence(context),
            )

        # Handle common file types
        if mime_type in [
            "application/pdf",
            "audio/mp3",
            "audio/wav",
            "audio/m4a",
            "audio/ogg",
            "audio/flac",
            "audio/aac",
            "audio/mpeg",
            "video/mp4",
            "video/webm",
        ]:
            # Determine filename from mime type
            ext = mime_type.split("/")[-1]
            if ext == "mpeg":
                ext = "mp3"  # audio/mpeg → .mp3
            filename = f"output.{ext}"

            # Prefer URI
            if uri_value:
                file_url = uri_value
                file_data = None
            elif data_value:
                # Convert bytes to base64
                import base64

                if isinstance(data_value, bytes):
                    b64_data = base64.b64encode(data_value).decode("utf-8")
                else:
                    b64_data = str(data_value)
                file_url = f"data:{mime_type};base64,{b64_data}"
                file_data = b64_data
            else:
                # No data available, fallback to trace
                logger.warning(f"DataContent with {mime_type} has no data or uri, falling back to trace")
                return ResponseTraceEventComplete(
                    type="response.trace.completed",
                    data={"content_type": "data", "mime_type": mime_type, "error": "No data or uri"},
                    item_id=context["item_id"],
                    output_index=context["output_index"],
                    sequence_number=self._next_sequence(context),
                )

            return ResponseOutputItemAddedEvent(
                type="response.output_item.added",
                item=ResponseOutputFile(  # type: ignore[arg-type]
                    id=item_id,
                    type="output_file",
                    filename=filename,
                    file_url=file_url,
                    file_data=file_data,
                    mime_type=mime_type,
                ),
                output_index=context["output_index"],
                sequence_number=self._next_sequence(context),
            )

        # Handle generic data (structured data, JSON, etc.)
        data_str = ""
        if uri_value:
            data_str = uri_value
        elif data_value:
            if isinstance(data_value, bytes):
                try:
                    data_str = data_value.decode("utf-8")
                except UnicodeDecodeError:
                    # Binary data, encode as base64 for display
                    import base64

                    data_str = base64.b64encode(data_value).decode("utf-8")
            else:
                data_str = str(data_value)

        return ResponseOutputItemAddedEvent(
            type="response.output_item.added",
            item=ResponseOutputData(  # type: ignore[arg-type]
                id=item_id,
                type="output_data",
                data=data_str,
                mime_type=mime_type,
                description=None,
            ),
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_uri_content(
        self, content: Any, context: dict[str, Any]
    ) -> ResponseOutputItemAddedEvent | ResponseTraceEventComplete:
        """Map UriContent to proper output item (image/file) based on MIME type.

        UriContent has a URI and MIME type, so we can create appropriate output items:
        - Images → ResponseOutputImage
        - Common files → ResponseOutputFile
        - Other URIs → ResponseTraceEventComplete (fallback for debugging)
        """
        mime_type = getattr(content, "mime_type", "text/plain")
        uri = getattr(content, "uri", "")
        item_id = f"item_{uuid.uuid4().hex[:16]}"

        if not uri:
            # No URI available, fallback to trace
            logger.warning("UriContent has no uri, falling back to trace")
            return ResponseTraceEventComplete(
                type="response.trace.completed",
                data={"content_type": "uri", "mime_type": mime_type, "error": "No uri"},
                item_id=context["item_id"],
                output_index=context["output_index"],
                sequence_number=self._next_sequence(context),
            )

        # Handle images
        if mime_type.startswith("image/"):
            return ResponseOutputItemAddedEvent(
                type="response.output_item.added",
                item=ResponseOutputImage(  # type: ignore[arg-type]
                    id=item_id,
                    type="output_image",
                    image_url=uri,
                    mime_type=mime_type,
                    alt_text=None,
                ),
                output_index=context["output_index"],
                sequence_number=self._next_sequence(context),
            )

        # Handle common file types
        if mime_type in [
            "application/pdf",
            "audio/mp3",
            "audio/wav",
            "audio/m4a",
            "audio/ogg",
            "audio/flac",
            "audio/aac",
            "audio/mpeg",
            "video/mp4",
            "video/webm",
        ]:
            # Extract filename from URI or use generic name
            filename = uri.split("/")[-1] if "/" in uri else f"output.{mime_type.split('/')[-1]}"

            return ResponseOutputItemAddedEvent(
                type="response.output_item.added",
                item=ResponseOutputFile(  # type: ignore[arg-type]
                    id=item_id,
                    type="output_file",
                    filename=filename,
                    file_url=uri,
                    file_data=None,
                    mime_type=mime_type,
                ),
                output_index=context["output_index"],
                sequence_number=self._next_sequence(context),
            )

        # For other URI types (text/plain, application/json, etc.), use trace for now
        logger.debug(f"UriContent with unsupported MIME type {mime_type}, using trace event")
        return ResponseTraceEventComplete(
            type="response.trace.completed",
            data={
                "content_type": "uri",
                "uri": uri,
                "mime_type": mime_type,
                "timestamp": datetime.now().isoformat(),
            },
            item_id=context["item_id"],
            output_index=context["output_index"],
            sequence_number=self._next_sequence(context),
        )

    async def _map_hosted_file_content(self, content: Any, context: dict[str, Any]) -> ResponseTraceEventComplete:
        """Map HostedFileContent to trace event.

        HostedFileContent references external file IDs (like OpenAI file IDs).
        These remain as traces since they're metadata about hosted resources,
        not direct content to display. To display them, agents should return
        DataContent or UriContent with the actual file data/URL.
        """
        return ResponseTraceEventComplete(
            type="response.trace.completed",
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
        """Map HostedVectorStoreContent to trace event.

        HostedVectorStoreContent references external vector store IDs.
        These remain as traces since they're metadata about hosted resources,
        not direct content to display.
        """
        return ResponseTraceEventComplete(
            type="response.trace.completed",
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
        # Parse arguments to ensure they're always a dict, not a JSON string
        # This prevents double-escaping when the frontend calls JSON.stringify()
        arguments: dict[str, Any] = {}
        if hasattr(content, "function_call"):
            if hasattr(content.function_call, "parse_arguments"):
                # Use parse_arguments() to convert string arguments to dict
                arguments = content.function_call.parse_arguments() or {}
            else:
                # Fallback to direct access if parse_arguments doesn't exist
                arguments = getattr(content.function_call, "arguments", {})

        return {
            "type": "response.function_approval.requested",
            "request_id": getattr(content, "id", "unknown"),
            "function_call": {
                "id": getattr(content.function_call, "call_id", "") if hasattr(content, "function_call") else "",
                "name": getattr(content.function_call, "name", "") if hasattr(content, "function_call") else "",
                "arguments": arguments,
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
        text = f"Unknown event: {event_data!s}\n"
        return self._create_text_delta_event(text, context)

    async def _create_unknown_content_event(self, content: Any, context: dict[str, Any]) -> ResponseStreamEvent:
        """Create event for unknown content types."""
        content_type = content.__class__.__name__
        text = f"Warning: Unknown content type: {content_type}\n"
        return self._create_text_delta_event(text, context)

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
            model=request.model or "devui",
            output=[response_output_message],
            usage=usage,
            parallel_tool_calls=False,
            tool_choice="none",
            tools=[],
        )
