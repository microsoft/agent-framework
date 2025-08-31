# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections.abc import AsyncIterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict, cast

from agent_framework import (
    AgentBase,
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    ChatMessage,
    ChatRole,
    FunctionCallContent,
    FunctionResultContent,
    TextContent,
    UsageDetails,
)
from agent_framework._pydantic import AFBaseModel
from agent_framework.exceptions import AgentExecutionException
from pydantic import Field

from ._events import (
    AgentRunUpdateEvent,
    RequestInfoEvent,
    WorkflowEvent,
)

if TYPE_CHECKING:
    from ._workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowAgent(AgentBase):
    """An `AIAgent` subclass that wraps a workflow and exposes it as an agent."""

    # Class variable for the request info function name
    REQUEST_INFO_FUNCTION_NAME: ClassVar[str] = "request_info"

    class RequestInfoFunctionArgs(AFBaseModel):
        request_id: str
        data: Any

    workflow: "Workflow" = Field(description="The workflow wrapped as an agent")
    pending_requests: dict[str, RequestInfoEvent] = Field(
        default_factory=dict, description="Pending request info events"
    )

    def __init__(
        self,
        workflow: "Workflow",
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the WorkflowAgent.

        Args:
            workflow: The workflow to wrap as an agent.
            id: Unique identifier for the agent. If None, will be generated.
            name: Optional name for the agent.
            description: Optional description of the agent.
            **kwargs: Additional keyword arguments passed to AgentBase.
        """
        if id is None:
            id = f"WorkflowAgent_{uuid.uuid4().hex[:8]}"
        # Initialize with standard AgentBase parameters first
        kwargs["workflow"] = workflow
        super().__init__(id=id, name=name, description=description, **kwargs)

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Get a response from the workflow agent (non-streaming).

        This method collects all streaming updates and merges them into a single response.

        Args:
            messages: The message(s) to send to the workflow.
            thread: The conversation thread. If None, a new thread will be created.
            **kwargs: Additional keyword arguments.

        Returns:
            The final workflow response as an AgentRunResponse.
        """
        # Collect all streaming updates
        response_updates: list[AgentRunResponseUpdate] = []
        input_messages = self._normalize_messages(messages)
        thread = thread or self.get_new_thread()
        response_id = str(uuid.uuid4())

        async for update in self._run_streaming_impl(input_messages, response_id):
            response_updates.append(update)

        # Convert updates to final response.
        response = self.merge_updates(response_updates, response_id)

        # Notify thread of new messages (both input and response messages)
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

        return response

    async def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Stream response updates from the workflow agent.

        Args:
            messages: The message(s) to send to the workflow.
            thread: The conversation thread. If None, a new thread will be created.
            **kwargs: Additional keyword arguments.

        Yields:
            AgentRunResponseUpdate objects representing the workflow execution progress.
        """
        input_messages = self._normalize_messages(messages)
        thread = thread or self.get_new_thread()
        response_updates: list[AgentRunResponseUpdate] = []
        response_id = str(uuid.uuid4())

        async for update in self._run_streaming_impl(input_messages, response_id):
            response_updates.append(update)
            yield update

        # Convert updates to final response.
        response = self.merge_updates(response_updates, response_id)

        # Notify thread of new messages (both input and response messages)
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

    async def _run_streaming_impl(
        self,
        input_messages: list[ChatMessage],
        response_id: str,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Internal implementation of streaming execution.

        Args:
            input_messages: Normalized input messages to process.
            response_id: The unique response ID for this workflow execution.

        Yields:
            AgentRunResponseUpdate objects representing the workflow execution progress.
        """
        # Determine the event stream based on whether we have function responses
        if bool(self.pending_requests):
            # This is a continuation - use send_responses_streaming to send function responses back
            logger.info(f"Continuing workflow to address {len(self.pending_requests)} requests")

            # Extract function responses from input messages, and ensure that
            # only function responses are present in messages if there is any
            # pending request.
            function_responses = self._extract_function_responses(input_messages)

            # Pop pending requests if fulfilled.
            for request_id in list(self.pending_requests.keys()):
                if request_id in function_responses:
                    self.pending_requests.pop(request_id)

            # NOTE: It is possible that some pending requests are not fulfilled,
            # and we will let the workflow to handle this -- the agent does not
            # have an opinion on this.
            event_stream = self.workflow.send_responses_streaming(function_responses)
        else:
            # Execute workflow with streaming (initial run or no function responses)
            # Pass the new input messages directly to the workflow
            event_stream = self.workflow.run_streaming(input_messages)

        # Process events from the stream
        async for event in event_stream:
            # Convert workflow event to agent update
            update = self._convert_workflow_event_to_agent_update(response_id, event)
            if update:
                yield update

    def _normalize_messages(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        """Normalize input messages to a list of ChatMessage objects."""
        if messages is None:
            return []

        if isinstance(messages, str):
            return [ChatMessage(role=ChatRole.USER, contents=[TextContent(text=messages)])]

        if isinstance(messages, ChatMessage):
            return [messages]

        normalized = []
        for msg in messages:
            if isinstance(msg, str):
                normalized.append(ChatMessage(role=ChatRole.USER, contents=[TextContent(text=msg)]))
            elif isinstance(msg, ChatMessage):
                normalized.append(msg)
        return normalized

    def _convert_workflow_event_to_agent_update(
        self,
        response_id: str,
        event: WorkflowEvent,
    ) -> AgentRunResponseUpdate | None:
        """Convert a workflow event to an AgentRunResponseUpdate.

        Only AgentRunUpdateEvent and RequestInfoEvent are processed and the rest
        are not relevant. Returns None if the event is not relevant.
        """
        match event:
            case AgentRunUpdateEvent(data=update):
                # Direct pass-through of update in an agent streaming event
                if update:
                    return cast(AgentRunResponseUpdate, update)
                return None

            case RequestInfoEvent(request_id=request_id):
                # Store the pending request for later correlation
                self.pending_requests[request_id] = event

                # Convert to function call content
                function_call = FunctionCallContent(
                    call_id=request_id,
                    name=self.REQUEST_INFO_FUNCTION_NAME,
                    arguments=self.RequestInfoFunctionArgs(request_id=request_id, data=event.data).model_dump(),
                )
                return AgentRunResponseUpdate(
                    contents=[function_call],
                    role=ChatRole.ASSISTANT,
                    author_name=self.name,
                    response_id=response_id,
                    message_id=str(uuid.uuid4()),
                    created_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                )
        # We only care about the above two events and discard the rest.
        return None

    def _extract_function_responses(self, input_messages: list[ChatMessage]) -> dict[str, Any]:
        """Extract function responses from input messages."""
        function_responses: dict[str, Any] = {}
        for message in input_messages:
            for content in message.contents:
                if isinstance(content, FunctionResultContent):
                    request_id = content.call_id
                    # Check if we have a pending request for this call_id
                    if request_id in self.pending_requests:
                        response_data = content.result if hasattr(content, "result") else str(content)
                        function_responses[request_id] = response_data
                    elif bool(self.pending_requests):
                        # Function result for unknown request when we have pending requests - this is an error
                        raise AgentExecutionException(
                            "Only FunctionResultContent for pending requests is allowed in input messages "
                            "when there are pending requests."
                        )
                else:
                    if bool(self.pending_requests):
                        # Non-function content when we have pending requests - this is an error
                        raise AgentExecutionException(
                            "Only FunctionResultContent is allowed in input messages when there are pending requests."
                        )
        return function_responses

    class _ResponseState(TypedDict):
        """State for grouping response updates by message_id."""

        by_msg: dict[str, list[AgentRunResponseUpdate]]
        dangling: list[AgentRunResponseUpdate]

    @staticmethod
    def merge_updates(updates: list[AgentRunResponseUpdate], response_id: str) -> AgentRunResponse:
        """Merge streaming updates into a single AgentRunResponse.

        Behavior:
        - Group updates by response_id; within each group, group by message_id and keep a
            per-group dangling bucket for updates with no message_id.
        - Convert each group (per message and dangling) into an intermediate AgentRunResponse
            using AgentRunResponse.from_agent_run_response_updates.
        - Sort those responses by created_at (valid timestamps before None) and merge them by:
            concatenating messages chronologically, summing UsageDetails, preferring the latest
            created_at and additional_properties, and collecting raw_representation values into a list.
        - Handle updates that have no response_id at all at the end ("global dangling").

        Args:
            updates: The list of AgentRunResponseUpdate objects to merge.
            response_id: The response identifier to set on the returned AgentRunResponse.

        Returns:
            An AgentRunResponse with messages in processing order and aggregated metadata.

        Notes:
            - Input updates are not mutated.
            - Intermediate responses with a response_id different from their group key are coerced
                to the group key for consistency. The returned response_id is always the provided
                response_id parameter.
        """
        # PHASE 1: GROUP UPDATES BY RESPONSE_ID AND MESSAGE_ID
        # ===================================================
        # We partition all updates into a two-level hierarchy:
        # 1. First level: group by response_id (updates from the same response)
        # 2. Second level: within each response_id, group by message_id (updates for the same message)
        # 3. Special case: updates without message_id go into a "dangling" bucket per response
        # 4. Global special case: updates without response_id go into global_dangling

        states: dict[str, WorkflowAgent._ResponseState] = {}  # response_id -> {by_msg, dangling}
        global_dangling: list[AgentRunResponseUpdate] = []  # updates with no response_id at all

        for u in updates:
            if u.response_id:
                # This update belongs to a specific response - group it appropriately
                state = states.setdefault(u.response_id, {"by_msg": {}, "dangling": []})
                by_msg = state["by_msg"]  # message_id -> list of updates for that message
                dangling = state["dangling"]  # updates with no message_id for this response

                if u.message_id:
                    # This update is part of a specific message - group with other updates for same message
                    by_msg.setdefault(u.message_id, []).append(u)
                else:
                    # This update has a response_id but no message_id - goes into response's dangling bucket
                    dangling.append(u)
            else:
                # This update has no response_id at all - goes into global dangling bucket
                global_dangling.append(u)

        # HELPER FUNCTIONS FOR SORTING AND MERGING
        # ========================================

        def _parse_dt(value: str | None) -> tuple[int, datetime | str | None]:
            """Parse created_at timestamp for sorting.

            Returns (priority, parsed_value) where priority=0 means valid timestamp (sorts first),
            priority=1 means None/invalid (sorts last).
            """
            if not value:
                return (1, None)  # None goes last in sort order

            v = value
            # Normalize ISO8601 format: trailing Z -> +00:00 for Python's fromisoformat()
            if v.endswith("Z"):
                v = v[:-1] + "+00:00"

            try:
                # Parse as proper datetime for chronological ordering
                return (0, datetime.fromisoformat(v))
            except Exception:
                # If parsing fails, fall back to string comparison (still sort before None)
                return (0, v)

        def _sum_usage(a: UsageDetails | None, b: UsageDetails | None) -> UsageDetails | None:
            """Combine usage details from two responses. UsageDetails implements __add__ for proper aggregation."""
            if a is None:
                return b
            if b is None:
                return a
            return a + b  # UsageDetails has __add__ method for token count aggregation

        def _merge_responses(current: AgentRunResponse | None, incoming: AgentRunResponse) -> AgentRunResponse:
            """Merge two AgentRunResponse objects that belong to the same logical response.

            Combines messages, prefers latest metadata, and aggregates usage/raw_representation.
            """
            if current is None:
                return incoming  # First response becomes the base

            # Collect raw representations as a list to preserve execution history
            raw_list: list[object] = []
            # Add current response's raw data
            if current.raw_representation is not None:
                if isinstance(current.raw_representation, list):
                    raw_list.extend(current.raw_representation)  # Already a list, extend it
                else:
                    raw_list.append(current.raw_representation)  # Single item, append it
            # Add incoming response's raw data
            if incoming.raw_representation is not None:
                if isinstance(incoming.raw_representation, list):
                    raw_list.extend(incoming.raw_representation)
                else:
                    raw_list.append(incoming.raw_representation)

            return AgentRunResponse(
                # Concatenate all messages in chronological order
                messages=(current.messages or []) + (incoming.messages or []),
                # Keep consistent response_id (prefer current, fall back to incoming)
                response_id=current.response_id or incoming.response_id,
                # Prefer latest timestamp (incoming is processed later, so likely newer)
                created_at=incoming.created_at or current.created_at,
                # Sum token usage from both responses
                usage_details=_sum_usage(current.usage_details, incoming.usage_details),
                # Preserve execution history as list
                raw_representation=raw_list if raw_list else None,
                # Prefer incoming properties (latest take precedence)
                additional_properties=incoming.additional_properties or current.additional_properties,
            )

        # PHASE 2: CONVERT GROUPED UPDATES TO RESPONSES AND MERGE
        # =======================================================
        # Initialize containers for final aggregated metadata
        final_messages: list[ChatMessage] = []  # All messages from all responses
        merged_usage: UsageDetails | None = None  # Aggregated token usage
        latest_created_at: str | None = None  # Latest timestamp across all responses
        merged_additional_properties: dict[str, Any] | None = None  # Merged properties
        raw_representations: list[object] = []  # All raw representations

        # Process each response_id group separately
        for grouped_response_id in states:
            state = states[grouped_response_id]
            by_msg = state["by_msg"]  # message_id -> list of updates
            dangling = state["dangling"]  # updates with no message_id

            # PHASE 2A: Convert each message group to AgentRunResponse
            per_message_responses: list[AgentRunResponse] = []

            # Convert each message_id group into a single AgentRunResponse
            for _, msg_updates in by_msg.items():
                if msg_updates:
                    # Use built-in method to merge updates for the same message
                    per_message_responses.append(AgentRunResponse.from_agent_run_response_updates(msg_updates))

            # Also convert dangling updates (no message_id) to a response
            if dangling:
                per_message_responses.append(AgentRunResponse.from_agent_run_response_updates(dangling))

            # PHASE 2B: Sort responses chronologically within this response_id group
            # This ensures messages appear in the correct temporal order
            per_message_responses.sort(key=lambda r: _parse_dt(r.created_at))

            # PHASE 2C: Merge all responses for this response_id into single response
            aggregated: AgentRunResponse | None = None
            for resp in per_message_responses:
                # Ensure response_id consistency - fix any mismatches
                if resp.response_id and grouped_response_id and resp.response_id != grouped_response_id:
                    # Prefer the grouping key (which came from the updates themselves)
                    resp.response_id = grouped_response_id
                # Progressively merge this response with the accumulated result
                aggregated = _merge_responses(aggregated, resp)

            # PHASE 2D: Add this response_id group's results to final aggregation
            if aggregated:
                # Add all messages from this response_id group to final output
                final_messages.extend(aggregated.messages)

                # Aggregate metadata across ALL response_id groups
                # Usage: sum token counts from all responses
                if aggregated.usage_details:
                    merged_usage = _sum_usage(merged_usage, aggregated.usage_details)

                # Timestamp: keep the latest timestamp seen across all responses
                if aggregated.created_at and (
                    not latest_created_at or _parse_dt(aggregated.created_at) > _parse_dt(latest_created_at)
                ):
                    latest_created_at = aggregated.created_at

                # Additional properties: merge all dictionaries (later ones win on conflicts)
                if aggregated.additional_properties:
                    if merged_additional_properties is None:
                        merged_additional_properties = {}
                    merged_additional_properties.update(aggregated.additional_properties)

                # Raw representations: collect everything as a list to preserve history
                if aggregated.raw_representation:
                    if isinstance(aggregated.raw_representation, list):
                        raw_representations.extend(aggregated.raw_representation)
                    else:
                        raw_representations.append(aggregated.raw_representation)

        # PHASE 3: HANDLE GLOBAL DANGLING UPDATES (NO RESPONSE_ID)
        # ========================================================
        # These are updates that have no response_id at all - they get appended at the very end
        if global_dangling:
            # Convert the global dangling updates to a single response
            flattened = AgentRunResponse.from_agent_run_response_updates(global_dangling)
            # Add their messages to the final output (they go at the end)
            final_messages.extend(flattened.messages)

            # Also aggregate their metadata into the final result
            if flattened.usage_details:
                merged_usage = _sum_usage(merged_usage, flattened.usage_details)
            if flattened.created_at and (
                not latest_created_at or _parse_dt(flattened.created_at) > _parse_dt(latest_created_at)
            ):
                latest_created_at = flattened.created_at
            if flattened.additional_properties:
                if merged_additional_properties is None:
                    merged_additional_properties = {}
                merged_additional_properties.update(flattened.additional_properties)
            if flattened.raw_representation:
                if isinstance(flattened.raw_representation, list):
                    raw_representations.extend(flattened.raw_representation)
                else:
                    raw_representations.append(flattened.raw_representation)

        # PHASE 4: CONSTRUCT FINAL RESPONSE WITH INPUT RESPONSE_ID
        # ========================================================
        # Create the final AgentRunResponse using the provided response_id parameter
        # and all the aggregated data from the various update groups
        return AgentRunResponse(
            messages=final_messages,  # All messages in processing order
            response_id=response_id,  # Use the input parameter, not update response_ids
            created_at=latest_created_at,  # Latest timestamp across all updates
            usage_details=merged_usage,  # Aggregated token usage
            raw_representation=raw_representations if raw_representations else None,  # Execution history
            additional_properties=merged_additional_properties,  # Merged properties
        )
