# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import sys
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, cast

from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Content,
    Role,
    UsageDetails,
)

from .._types import add_usage_details
from ..exceptions import AgentExecutionException
from ._agent_executor import AgentExecutor
from ._checkpoint import CheckpointStorage
from ._events import (
    AgentRunUpdateEvent,
    RequestInfoEvent,
    WorkflowEvent,
    WorkflowOutputEvent,
)
from ._message_utils import normalize_messages_input
from ._typing_utils import is_type_compatible

if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover

if TYPE_CHECKING:
    from ._workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowAgent(BaseAgent):
    """An `Agent` subclass that wraps a workflow and exposes it as an agent."""

    # Class variable for the request info function name
    REQUEST_INFO_FUNCTION_NAME: ClassVar[str] = "request_info"

    @dataclass
    class RequestInfoFunctionArgs:
        request_id: str
        data: Any

        def to_dict(self) -> dict[str, Any]:
            return {"request_id": self.request_id, "data": self.data}

        def to_json(self) -> str:
            return json.dumps(self.to_dict())

        @classmethod
        def from_dict(cls, payload: dict[str, Any]) -> "WorkflowAgent.RequestInfoFunctionArgs":
            return cls(request_id=payload.get("request_id", ""), data=payload.get("data"))

        @classmethod
        def from_json(cls, raw: str) -> "WorkflowAgent.RequestInfoFunctionArgs":
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"RequestInfoFunctionArgs JSON payload is malformed: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError("RequestInfoFunctionArgs JSON payload must decode to a mapping")
            return cls.from_dict(cast(dict[str, Any], parsed))

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

        Keyword Args:
            id: Unique identifier for the agent. If None, will be generated.
            name: Optional name for the agent.
            description: Optional description of the agent.
            **kwargs: Additional keyword arguments passed to BaseAgent.
        """
        if id is None:
            id = f"WorkflowAgent_{uuid.uuid4().hex[:8]}"
        # Initialize with standard BaseAgent parameters first
        # Validate the workflow's start executor can handle agent-facing message inputs
        try:
            start_executor = workflow.get_start_executor()
        except KeyError as exc:  # Defensive: workflow lacks a configured entry point
            raise ValueError("Workflow's start executor is not defined.") from exc

        if not any(is_type_compatible(list[ChatMessage], input_type) for input_type in start_executor.input_types):
            raise ValueError("Workflow's start executor cannot handle list[ChatMessage]")

        super().__init__(id=id, name=name, description=description, **kwargs)
        self._workflow: "Workflow" = workflow
        self._pending_requests: dict[str, RequestInfoEvent] = {}

    @property
    def workflow(self) -> "Workflow":
        return self._workflow

    @property
    def pending_requests(self) -> dict[str, RequestInfoEvent]:
        return self._pending_requests

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Get a response from the workflow agent (non-streaming).

        This method collects all streaming updates and merges them into a single response.

        Args:
            messages: The message(s) to send to the workflow. Required for new runs,
                should be None when resuming from checkpoint.

        Keyword Args:
            thread: The conversation thread. If None, a new thread will be created.
            checkpoint_id: ID of checkpoint to restore from. If provided, the workflow
                resumes from this checkpoint instead of starting fresh.
            checkpoint_storage: Runtime checkpoint storage. When provided with checkpoint_id,
                used to load and restore the checkpoint. When provided without checkpoint_id,
                enables checkpointing for this run.
            **kwargs: Additional keyword arguments passed through to underlying workflow
                and tool functions.

        Returns:
            The final workflow response as an AgentResponse.
        """
        # Collect all streaming updates
        response_updates: list[AgentResponseUpdate] = []
        input_messages = normalize_messages_input(messages)
        thread = thread or self.get_new_thread()
        response_id = str(uuid.uuid4())

        async for update in self._run_stream_impl(
            input_messages, response_id, thread, checkpoint_id, checkpoint_storage, **kwargs
        ):
            response_updates.append(update)

        # Convert updates to final response.
        response = self.merge_updates(response_updates, response_id)

        # Notify thread of new messages (both input and response messages)
        await self._notify_thread_of_new_messages(thread, input_messages, response.messages)

        return response

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Stream response updates from the workflow agent.

        Args:
            messages: The message(s) to send to the workflow. Required for new runs,
                should be None when resuming from checkpoint.

        Keyword Args:
            thread: The conversation thread. If None, a new thread will be created.
            checkpoint_id: ID of checkpoint to restore from. If provided, the workflow
                resumes from this checkpoint instead of starting fresh.
            checkpoint_storage: Runtime checkpoint storage. When provided with checkpoint_id,
                used to load and restore the checkpoint. When provided without checkpoint_id,
                enables checkpointing for this run.
            **kwargs: Additional keyword arguments passed through to underlying workflow
                and tool functions.

        Yields:
            AgentResponseUpdate objects representing the workflow execution progress.
        """
        input_messages = normalize_messages_input(messages)
        thread = thread or self.get_new_thread()
        response_updates: list[AgentResponseUpdate] = []
        response_id = str(uuid.uuid4())

        async for update in self._run_stream_impl(
            input_messages, response_id, thread, checkpoint_id, checkpoint_storage, **kwargs
        ):
            response_updates.append(update)
            yield update

        # Convert updates to final response.
        response = self.merge_updates(response_updates, response_id)

        # Notify thread of new messages (both input and response messages)
        await self._notify_thread_of_new_messages(thread, input_messages, response.messages)

    async def _run_stream_impl(
        self,
        input_messages: list[ChatMessage],
        response_id: str,
        thread: AgentThread,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Internal implementation of streaming execution.

        Args:
            input_messages: Normalized input messages to process.
            response_id: The unique response ID for this workflow execution.
            thread: The conversation thread containing message history.
            checkpoint_id: ID of checkpoint to restore from.
            checkpoint_storage: Runtime checkpoint storage.
            **kwargs: Additional keyword arguments passed through to the underlying
                workflow and tool functions.

        Yields:
            AgentResponseUpdate objects representing the workflow execution progress.
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
        elif checkpoint_id is not None:
            # Resume from checkpoint - don't prepend thread history since workflow state
            # is being restored from the checkpoint
            event_stream = self.workflow.run_stream(
                message=None,
                checkpoint_id=checkpoint_id,
                checkpoint_storage=checkpoint_storage,
                **kwargs,
            )
        else:
            # Execute workflow with streaming (initial run or no function responses)
            # Build the complete conversation by prepending thread history to input messages
            conversation_messages: list[ChatMessage] = []
            if thread.message_store:
                history = await thread.message_store.list_messages()
                if history:
                    conversation_messages.extend(history)
            conversation_messages.extend(input_messages)
            event_stream = self.workflow.run_stream(
                message=conversation_messages,
                checkpoint_storage=checkpoint_storage,
                **kwargs,
            )

        # Process events from the stream
        async for event in event_stream:
            # Convert workflow event to agent update
            update = self._convert_workflow_event_to_agent_update(response_id, event)
            if update:
                yield update

    def _convert_workflow_event_to_agent_update(
        self,
        response_id: str,
        event: WorkflowEvent,
    ) -> AgentResponseUpdate | None:
        """Convert a workflow event to an AgentResponseUpdate.

        AgentRunUpdateEvent, RequestInfoEvent, and WorkflowOutputEvent are processed.
        Other workflow events are ignored as they are workflow-internal.

        For AgentRunUpdateEvent from AgentExecutor instances, only events from executors
        with output_response=True are converted to agent updates. This prevents agent
        responses from executors that were not explicitly marked to surface their output.
        Non-AgentExecutor executors that emit AgentRunUpdateEvent directly are allowed
        through since they explicitly chose to emit the event.
        """
        match event:
            case AgentRunUpdateEvent(data=update, executor_id=executor_id):
                # For AgentExecutor instances, only pass through if output_response=True.
                # Non-AgentExecutor executors that emit AgentRunUpdateEvent are allowed through.
                executor = self.workflow.executors.get(executor_id)
                if isinstance(executor, AgentExecutor) and not executor.output_response:
                    return None
                if update:
                    # Enrich with executor identity if author_name is not already set
                    if not update.author_name:
                        update.author_name = executor_id
                    return update
                return None

            case WorkflowOutputEvent(data=data, executor_id=executor_id):
                # Convert workflow output to an agent response update.
                # Handle different data types appropriately.

                # Skip AgentResponse from AgentExecutor with output_response=True
                # since streaming events already surfaced the content.
                if isinstance(data, AgentResponse):
                    executor = self.workflow.executors.get(executor_id)
                    if isinstance(executor, AgentExecutor) and executor.output_response:
                        return None

                if isinstance(data, AgentResponseUpdate):
                    return data
                if isinstance(data, ChatMessage):
                    return AgentResponseUpdate(
                        contents=list(data.contents),
                        role=data.role,
                        author_name=data.author_name or executor_id,
                        response_id=response_id,
                        message_id=str(uuid.uuid4()),
                        created_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        raw_representation=data,
                    )
                contents = self._extract_contents(data)
                if not contents:
                    return None
                return AgentResponseUpdate(
                    contents=contents,
                    role=Role.ASSISTANT,
                    author_name=executor_id,
                    response_id=response_id,
                    message_id=str(uuid.uuid4()),
                    created_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    raw_representation=data,
                )

            case RequestInfoEvent(request_id=request_id):
                # Store the pending request for later correlation
                self.pending_requests[request_id] = event

                args = self.RequestInfoFunctionArgs(request_id=request_id, data=event.data).to_dict()

                function_call = Content.from_function_call(
                    call_id=request_id,
                    name=self.REQUEST_INFO_FUNCTION_NAME,
                    arguments=args,
                )
                approval_request = Content.from_function_approval_request(
                    id=request_id,
                    function_call=function_call,
                    additional_properties={"request_id": request_id},
                )
                return AgentResponseUpdate(
                    contents=[function_call, approval_request],
                    role=Role.ASSISTANT,
                    author_name=self.name,
                    response_id=response_id,
                    message_id=str(uuid.uuid4()),
                    created_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                )
            case _:
                # Ignore workflow-internal events
                pass
        return None

    def _extract_function_responses(self, input_messages: list[ChatMessage]) -> dict[str, Any]:
        """Extract function responses from input messages."""
        function_responses: dict[str, Any] = {}
        for message in input_messages:
            for content in message.contents:
                if content.type == "function_approval_response":
                    # Parse the function arguments to recover request payload
                    arguments_payload = content.function_call.arguments  # type: ignore[attr-defined, union-attr]
                    if isinstance(arguments_payload, str):
                        try:
                            parsed_args = self.RequestInfoFunctionArgs.from_json(arguments_payload)
                        except ValueError as exc:
                            raise AgentExecutionException(
                                "FunctionApprovalResponseContent arguments must decode to a mapping."
                            ) from exc
                    elif isinstance(arguments_payload, dict):
                        parsed_args = self.RequestInfoFunctionArgs.from_dict(arguments_payload)
                    else:
                        raise AgentExecutionException(
                            "FunctionApprovalResponseContent arguments must be a mapping or JSON string."
                        )

                    request_id = parsed_args.request_id or content.id  # type: ignore[attr-defined]
                    if not content.approved:  # type: ignore[attr-defined]
                        raise AgentExecutionException(f"Request '{request_id}' was not approved by the caller.")

                    if request_id in self.pending_requests:
                        function_responses[request_id] = parsed_args.data
                    elif bool(self.pending_requests):
                        raise AgentExecutionException(
                            "Only responses for pending requests are allowed when there are outstanding approvals."
                        )
                elif content.type == "function_result":
                    request_id = content.call_id  # type: ignore[attr-defined]
                    if request_id in self.pending_requests:
                        response_data = content.result if hasattr(content, "result") else str(content)  # type: ignore[attr-defined]
                        function_responses[request_id] = response_data
                    elif bool(self.pending_requests):
                        raise AgentExecutionException(
                            "Only function responses for pending requests are allowed while requests are outstanding."
                        )
                else:
                    if bool(self.pending_requests):
                        raise AgentExecutionException("Unexpected content type while awaiting request info responses.")
        return function_responses

    def _extract_contents(self, data: Any) -> list[Content]:
        """Recursively extract Content from workflow output data."""
        if isinstance(data, ChatMessage):
            return list(data.contents)
        if isinstance(data, list):
            return [c for item in data for c in self._extract_contents(item)]
        if isinstance(data, Content):
            return [data]  # type: ignore[redundant-cast]
        if isinstance(data, str):
            return [Content.from_text(text=data)]
        return [Content.from_text(text=str(data))]

    class _ResponseState(TypedDict):
        """State for grouping response updates by message_id."""

        by_msg: dict[str, list[AgentResponseUpdate]]
        dangling: list[AgentResponseUpdate]

    @staticmethod
    def merge_updates(updates: list[AgentResponseUpdate], response_id: str) -> AgentResponse:
        """Merge streaming updates into a single AgentResponse.

        Behavior:
        - Group updates by response_id; within each response_id, group by message_id and keep a dangling bucket for
          updates without message_id.
        - Convert each group (per message and dangling) into an intermediate AgentResponse via
          AgentResponse.from_agent_run_response_updates, then sort by created_at and merge.
        - Append messages from updates without any response_id at the end (global dangling), while aggregating metadata.

        Args:
            updates: The list of AgentResponseUpdate objects to merge.
            response_id: The response identifier to set on the returned AgentResponse.

        Returns:
            An AgentResponse with messages in processing order and aggregated metadata.
        """
        # PHASE 1: GROUP UPDATES BY RESPONSE_ID AND MESSAGE_ID
        # First pass: build call_id -> response_id map from FunctionCallContent updates
        call_id_to_response_id: dict[str, str] = {}
        for u in updates:
            if u.response_id:
                for content in u.contents:
                    if content.type == "function_call" and content.call_id:
                        call_id_to_response_id[content.call_id] = u.response_id

        # Second pass: group updates, associating FunctionResultContent with their calls
        states: dict[str, WorkflowAgent._ResponseState] = {}
        global_dangling: list[AgentResponseUpdate] = []

        for u in updates:
            effective_response_id = u.response_id
            # If no response_id, check if this is a FunctionResultContent that matches a call
            if not effective_response_id:
                for content in u.contents:
                    if content.type == "function_result" and content.call_id:
                        effective_response_id = call_id_to_response_id.get(content.call_id)
                        if effective_response_id:
                            break

            if effective_response_id:
                state = states.setdefault(effective_response_id, {"by_msg": {}, "dangling": []})
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

        def _merge_responses(current: AgentResponse | None, incoming: AgentResponse) -> AgentResponse:
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
            return AgentResponse(
                messages=(current.messages or []) + (incoming.messages or []),
                response_id=current.response_id or incoming.response_id,
                created_at=incoming.created_at or current.created_at,
                usage_details=add_usage_details(current.usage_details, incoming.usage_details),  # type: ignore[arg-type]
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

            per_message_responses: list[AgentResponse] = []
            for _, msg_updates in by_msg.items():
                if msg_updates:
                    per_message_responses.append(AgentResponse.from_agent_run_response_updates(msg_updates))
            if dangling:
                per_message_responses.append(AgentResponse.from_agent_run_response_updates(dangling))

            per_message_responses.sort(key=lambda r: _parse_dt(r.created_at))

            aggregated: AgentResponse | None = None
            for resp in per_message_responses:
                if resp.response_id and grouped_response_id and resp.response_id != grouped_response_id:
                    resp.response_id = grouped_response_id
                aggregated = _merge_responses(aggregated, resp)

            if aggregated:
                final_messages.extend(aggregated.messages)
                if aggregated.usage_details:
                    merged_usage = add_usage_details(merged_usage, aggregated.usage_details)  # type: ignore[arg-type]
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
        # These are updates that couldn't be associated with any response_id
        # (e.g., orphan FunctionResultContent with no matching FunctionCallContent)
        if global_dangling:
            flattened = AgentResponse.from_agent_run_response_updates(global_dangling)
            final_messages.extend(flattened.messages)
            if flattened.usage_details:
                merged_usage = add_usage_details(merged_usage, flattened.usage_details)  # type: ignore[arg-type]
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
        return AgentResponse(
            messages=final_messages,
            response_id=response_id,
            created_at=latest_created_at,
            usage_details=merged_usage,
            raw_representation=raw_representations if raw_representations else None,
            additional_properties=merged_additional_properties,
        )
