# Copyright (c) Microsoft. All rights reserved.

import logging
import uuid
from collections.abc import AsyncIterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict, cast

from pydantic import Field

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    FunctionCallContent,
    FunctionResultContent,
    Role,
    TextContent,
    UsageDetails,
)

from .._pydantic import AFBaseModel
from ..exceptions import AgentExecutionException
from ._events import (
    AgentRunUpdateEvent,
    RequestInfoEvent,
    WorkflowEvent,
)

if TYPE_CHECKING:
    from ._workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowAgent(BaseAgent):
    """An `Agent` subclass that wraps a workflow and exposes it as an agent."""

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
            **kwargs: Additional keyword arguments passed to BaseAgent.
        """
        if id is None:
            id = f"WorkflowAgent_{uuid.uuid4().hex[:8]}"
        # Initialize with standard BaseAgent parameters first
        kwargs["workflow"] = workflow

        # Validate the workflow's start executor can handle agent-facing message inputs
        try:
            start_executor = workflow.get_start_executor()
        except KeyError as exc:  # Defensive: workflow lacks a configured entry point
            raise ValueError("Workflow's start executor is not defined.") from exc

        if list[ChatMessage] not in start_executor.input_types:
            raise ValueError("Workflow's start executor cannot handle list[ChatMessage]")

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

        async for update in self._run_stream_impl(input_messages, response_id):
            response_updates.append(update)

        # Convert updates to final response.
        response = self.merge_updates(response_updates, response_id)

        # Notify thread of new messages (both input and response messages)
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

        return response

    async def run_stream(
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

        async for update in self._run_stream_impl(input_messages, response_id):
            response_updates.append(update)
            yield update

        # Convert updates to final response.
        response = self.merge_updates(response_updates, response_id)

        # Notify thread of new messages (both input and response messages)
        await self._notify_thread_of_new_messages(thread, input_messages)
        await self._notify_thread_of_new_messages(thread, response.messages)

    async def _run_stream_impl(
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
            event_stream = self.workflow.run_stream(input_messages)

        # Process events from the stream
        async for event in event_stream:
            # Convert workflow event to agent update
            update = self._convert_workflow_event_to_agent_update(response_id, event)
            if update:
                yield update

    def _normalize_messages(
        self,
        messages: str | ChatMessage | Sequence[str] | Sequence[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        """Normalize input messages to a list of ChatMessage objects."""
        if messages is None:
            return []

        if isinstance(messages, str):
            return [ChatMessage(role=Role.USER, contents=[TextContent(text=messages)])]

        if isinstance(messages, ChatMessage):
            return [messages]

        normalized: list[ChatMessage] = []
        for msg in messages:
            if isinstance(msg, str):
                normalized.append(ChatMessage(role=Role.USER, contents=[TextContent(text=msg)]))
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
                # TODO(ekzhu): update this to FunctionApprovalRequestContent
                # monitor: https://github.com/microsoft/agent-framework/issues/285
                function_call = FunctionCallContent(
                    call_id=request_id,
                    name=self.REQUEST_INFO_FUNCTION_NAME,
                    arguments=self.RequestInfoFunctionArgs(request_id=request_id, data=event.data).model_dump(),
                )
                return AgentRunResponseUpdate(
                    contents=[function_call],
                    role=Role.ASSISTANT,
                    author_name=self.name,
                    response_id=response_id,
                    message_id=str(uuid.uuid4()),
                    created_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                )
            case _:
                # Ignore non-agent workflow events
                pass
        # We only care about the above two events and discard the rest.
        return None

    def _extract_function_responses(self, input_messages: list[ChatMessage]) -> dict[str, Any]:
        """Extract function responses from input messages."""
        function_responses: dict[str, Any] = {}
        for message in input_messages:
            for content in message.contents:
                # TODO(ekzhu): update this to FunctionApprovalResponseContent
                # monitor: https://github.com/microsoft/agent-framework/issues/285
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
        - Group updates by response_id; within each response_id, group by message_id and keep a dangling bucket for
          updates without message_id.
        - Convert each group (per message and dangling) into an intermediate AgentRunResponse via
          AgentRunResponse.from_agent_run_response_updates, then sort by created_at and merge.
        - Append messages from updates without any response_id at the end (global dangling), while aggregating metadata.

        Args:
            updates: The list of AgentRunResponseUpdate objects to merge.
            response_id: The response identifier to set on the returned AgentRunResponse.

        Returns:
            An AgentRunResponse with messages in processing order and aggregated metadata.
        """
        # PHASE 1: GROUP UPDATES BY RESPONSE_ID AND MESSAGE_ID
        states: dict[str, WorkflowAgent._ResponseState] = {}
        global_dangling: list[AgentRunResponseUpdate] = []

        for u in updates:
            if u.response_id:
                state = states.setdefault(u.response_id, {"by_msg": {}, "dangling": []})
                by_msg = state["by_msg"]
                dangling = state["dangling"]
                if u.message_id:
                    by_msg.setdefault(u.message_id, []).append(u)
                else:
                    dangling.append(u)
            else:
                global_dangling.append(u)

        # HELPER FUNCTIONS
        def _parse_dt(value: str | None) -> tuple[int, datetime | str | None]:
            if not value:
                return (1, None)
            v = value
            if v.endswith("Z"):
                v = v[:-1] + "+00:00"
            try:
                return (0, datetime.fromisoformat(v))
            except Exception:
                return (0, v)

        def _sum_usage(a: UsageDetails | None, b: UsageDetails | None) -> UsageDetails | None:
            if a is None:
                return b
            if b is None:
                return a
            return a + b

        def _merge_responses(current: AgentRunResponse | None, incoming: AgentRunResponse) -> AgentRunResponse:
            if current is None:
                return incoming
            raw_list: list[object] = []

            def _add_raw(value: object) -> None:
                if isinstance(value, list):
                    raw_list.extend(cast(list[object], value))
                else:
                    raw_list.append(value)

            if current.raw_representation is not None:
                _add_raw(current.raw_representation)
            if incoming.raw_representation is not None:
                _add_raw(incoming.raw_representation)
            return AgentRunResponse(
                messages=(current.messages or []) + (incoming.messages or []),
                response_id=current.response_id or incoming.response_id,
                created_at=incoming.created_at or current.created_at,
                usage_details=_sum_usage(current.usage_details, incoming.usage_details),
                raw_representation=raw_list if raw_list else None,
                additional_properties=incoming.additional_properties or current.additional_properties,
            )

        # PHASE 2: CONVERT GROUPED UPDATES TO RESPONSES AND MERGE
        final_messages: list[ChatMessage] = []
        merged_usage: UsageDetails | None = None
        latest_created_at: str | None = None
        merged_additional_properties: dict[str, Any] | None = None
        raw_representations: list[object] = []

        for grouped_response_id in states:
            state = states[grouped_response_id]
            by_msg = state["by_msg"]
            dangling = state["dangling"]

            per_message_responses: list[AgentRunResponse] = []
            for _, msg_updates in by_msg.items():
                if msg_updates:
                    per_message_responses.append(AgentRunResponse.from_agent_run_response_updates(msg_updates))
            if dangling:
                per_message_responses.append(AgentRunResponse.from_agent_run_response_updates(dangling))

            per_message_responses.sort(key=lambda r: _parse_dt(r.created_at))

            aggregated: AgentRunResponse | None = None
            for resp in per_message_responses:
                if resp.response_id and grouped_response_id and resp.response_id != grouped_response_id:
                    resp.response_id = grouped_response_id
                aggregated = _merge_responses(aggregated, resp)

            if aggregated:
                final_messages.extend(aggregated.messages)
                if aggregated.usage_details:
                    merged_usage = _sum_usage(merged_usage, aggregated.usage_details)
                if aggregated.created_at and (
                    not latest_created_at or _parse_dt(aggregated.created_at) > _parse_dt(latest_created_at)
                ):
                    latest_created_at = aggregated.created_at
                if aggregated.additional_properties:
                    if merged_additional_properties is None:
                        merged_additional_properties = {}
                    merged_additional_properties.update(aggregated.additional_properties)
                raw_value = aggregated.raw_representation
                if raw_value:
                    cast_value = cast(object | list[object], raw_value)
                    if isinstance(cast_value, list):
                        raw_representations.extend(cast(list[object], cast_value))
                    else:
                        raw_representations.append(cast_value)

        # PHASE 3: HANDLE GLOBAL DANGLING UPDATES (NO RESPONSE_ID)
        if global_dangling:
            flattened = AgentRunResponse.from_agent_run_response_updates(global_dangling)
            final_messages.extend(flattened.messages)
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
            flat_raw = flattened.raw_representation
            if flat_raw:
                cast_flat = cast(object | list[object], flat_raw)
                if isinstance(cast_flat, list):
                    raw_representations.extend(cast(list[object], cast_flat))
                else:
                    raw_representations.append(cast_flat)

        # PHASE 4: CONSTRUCT FINAL RESPONSE WITH INPUT RESPONSE_ID
        return AgentRunResponse(
            messages=final_messages,
            response_id=response_id,
            created_at=latest_created_at,
            usage_details=merged_usage,
            raw_representation=raw_representations if raw_representations else None,
            additional_properties=merged_additional_properties,
        )
