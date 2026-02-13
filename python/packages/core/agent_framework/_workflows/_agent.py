# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
import logging
import sys
import uuid
from collections.abc import AsyncIterable, Awaitable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast, overload

from .._agents import BaseAgent
from .._sessions import (
    AgentSession,
    BaseContextProvider,
    BaseHistoryProvider,
    InMemoryHistoryProvider,
    SessionContext,
)
from .._types import (
    AgentResponse,
    AgentResponseUpdate,
    Content,
    Message,
    ResponseStream,
    UsageDetails,
    add_usage_details,
)
from ..exceptions import AgentExecutionException
from ._checkpoint import CheckpointStorage
from ._events import (
    WorkflowEvent,
)
from ._message_utils import normalize_messages_input
from ._typing_utils import is_instance_of, is_type_compatible

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
        def from_dict(cls, payload: dict[str, Any]) -> WorkflowAgent.RequestInfoFunctionArgs:
            return cls(request_id=payload.get("request_id", ""), data=payload.get("data"))

        @classmethod
        def from_json(cls, raw: str) -> WorkflowAgent.RequestInfoFunctionArgs:
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"RequestInfoFunctionArgs JSON payload is malformed: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError("RequestInfoFunctionArgs JSON payload must decode to a mapping")
            return cls.from_dict(cast(dict[str, Any], parsed))

    def __init__(
        self,
        workflow: Workflow,
        *,
        id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        context_providers: Sequence[BaseContextProvider] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the WorkflowAgent.

        Args:
            workflow: The workflow to wrap as an agent.

        Keyword Args:
            id: Unique identifier for the agent. If None, will be generated.
            name: Optional name for the agent.
            description: Optional description of the agent.
            context_providers: Optional sequence of context providers for the agent.
            **kwargs: Additional keyword arguments passed to BaseAgent.

        Note:
            Only output events (type='output') and request_info events (type='request_info') from
            the workflow are considered and converted to agent responses of the WorkflowAgent.
            Other workflow events are ignored. Use `with_output_from` in WorkflowBuilder to control
            which executors' outputs are surfaced as agent responses.
        """
        if id is None:
            id = f"WorkflowAgent_{uuid.uuid4().hex[:8]}"
        # Initialize with standard BaseAgent parameters first
        # Validate the workflow's start executor can handle agent-facing message inputs
        try:
            start_executor = workflow.get_start_executor()
        except KeyError as exc:  # Defensive: workflow lacks a configured entry point
            raise ValueError("Workflow's start executor is not defined.") from exc

        if not any(is_type_compatible(list[Message], input_type) for input_type in start_executor.input_types):
            raise ValueError("Workflow's start executor cannot handle list[Message]")

        resolved_context_providers = list(context_providers) if context_providers is not None else []
        if not resolved_context_providers:
            resolved_context_providers.append(InMemoryHistoryProvider("memory"))

        super().__init__(
            id=id,
            name=name,
            description=description,
            context_providers=resolved_context_providers,
            **kwargs,
        )
        self._workflow: Workflow = workflow
        self._pending_requests: dict[str, WorkflowEvent[Any]] = {}

    @property
    def workflow(self) -> Workflow:
        return self._workflow

    @property
    def pending_requests(self) -> dict[str, WorkflowEvent[Any]]:
        return self._pending_requests

    # region Run Methods

    @overload
    def run(
        self,
        messages: str | Message | Sequence[str | Message] | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse]: ...

    @overload
    async def run(
        self,
        messages: str | Message | Sequence[str | Message] | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> AgentResponse: ...

    def run(
        self,
        messages: str | Message | Sequence[str | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse] | Awaitable[AgentResponse]:
        """Get a response from the workflow agent.

        Args:
            messages: The message(s) to send to the workflow. Required for new runs,
                should be None when resuming from checkpoint.

        Keyword Args:
            stream: If True, returns an async iterable of updates. If False (default),
                returns an awaitable AgentResponse.
            session: The agent session for conversation context.
            checkpoint_id: ID of checkpoint to restore from. If provided, the workflow
                resumes from this checkpoint instead of starting fresh.
            checkpoint_storage: Runtime checkpoint storage. When provided with checkpoint_id,
                used to load and restore the checkpoint. When provided without checkpoint_id,
                enables checkpointing for this run.
            **kwargs: Additional keyword arguments passed through to underlying workflow
                and tool functions.

        Returns:
            When stream=True: An AsyncIterable[AgentResponseUpdate] for streaming updates.
            When stream=False: An Awaitable[AgentResponse] with the complete response.

            Output events (type='output') from the workflow will be converted to ChatMessages
            or AgentResponseUpdate objects. Request info events (type='request_info') will be
            converted to function call and approval request contents.
        """
        if messages is None:
            messages = []
        response_id = str(uuid.uuid4())
        if stream:
            return ResponseStream(
                self._run_stream_impl(messages, response_id, session, checkpoint_id, checkpoint_storage, **kwargs),
                finalizer=AgentResponse.from_updates,
            )
        return self._run_impl(messages, response_id, session, checkpoint_id, checkpoint_storage, **kwargs)

    async def _run_impl(
        self,
        messages: str | Message | Sequence[str | Message],
        response_id: str,
        session: AgentSession | None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Internal implementation of non-streaming execution.

        Args:
            messages: Normalized input messages to process.
            response_id: The unique response ID for this workflow execution.
            session: The agent session for conversation context.
            checkpoint_id: ID of checkpoint to restore from.
            checkpoint_storage: Runtime checkpoint storage.
            **kwargs: Additional keyword arguments passed through to the underlying
                workflow and tool functions.

        Returns:
            An AgentResponse representing the workflow execution results.
        """
        input_messages = normalize_messages_input(messages)

        # run the context providers with the session
        session_context = SessionContext(
            session_id=session.session_id if session else None,
            service_session_id=session.service_session_id if session else None,
            input_messages=input_messages or [],
            options={},
        )
        state = session.state if session else {}
        for provider in self.context_providers:
            if isinstance(provider, BaseHistoryProvider) and not provider.load_messages:
                continue
            await provider.before_run(
                agent=self,  # type: ignore[arg-type]
                session=session,  # type: ignore[arg-type]
                context=session_context,
                state=state,
            )
        # combine the messages
        session_messages: list[Message] = session_context.get_messages(include_input=True)

        output_events: list[WorkflowEvent[Any]] = []
        async for event in self._run_core(
            session_messages, checkpoint_id, checkpoint_storage, streaming=False, **kwargs
        ):
            if event.type == "output" or event.type == "request_info":
                output_events.append(event)

        result = self._convert_workflow_events_to_agent_response(response_id, output_events)
        await self._run_after_providers(session=session, context=session_context)
        return result

    async def _run_stream_impl(
        self,
        messages: str | Message | Sequence[str | Message],
        response_id: str,
        session: AgentSession | None,
        checkpoint_id: str | None = None,
        checkpoint_storage: CheckpointStorage | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Internal implementation of streaming execution.

        Args:
            messages: Input messages to process.
            response_id: The unique response ID for this workflow execution.
            session: The agent session for conversation context.
            checkpoint_id: ID of checkpoint to restore from.
            checkpoint_storage: Runtime checkpoint storage.
            **kwargs: Additional keyword arguments passed through to the underlying
                workflow and tool functions.

        Yields:
            AgentResponseUpdate objects representing the workflow execution progress.
        """
        input_messages = normalize_messages_input(messages)

        # run the context providers with the session
        session_context = SessionContext(
            session_id=session.session_id if session else None,
            service_session_id=session.service_session_id if session else None,
            input_messages=input_messages or [],
            options={},
        )
        state = session.state if session else {}
        for provider in self.context_providers:
            if isinstance(provider, BaseHistoryProvider) and not provider.load_messages:
                continue
            await provider.before_run(
                agent=self,  # type: ignore[arg-type]
                session=session,  # type: ignore[arg-type]
                context=session_context,
                state=state,
            )
        # combine the messages

        session_messages: list[Message] = session_context.get_messages(include_input=True)
        async for event in self._run_core(
            session_messages, checkpoint_id, checkpoint_storage, streaming=True, **kwargs
        ):
            updates = self._convert_workflow_event_to_agent_response_updates(response_id, event)
            for update in updates:
                yield update
        await self._run_after_providers(session=session, context=session_context)

    async def _run_core(
        self,
        input_messages: Sequence[Message],
        checkpoint_id: str | None,
        checkpoint_storage: CheckpointStorage | None,
        streaming: bool,
        **kwargs: Any,
    ) -> AsyncIterable[WorkflowEvent]:
        """Core implementation that yields workflow events for both streaming and non-streaming modes.

        Args:
            input_messages: Normalized input messages to process.
            checkpoint_id: ID of checkpoint to restore from.
            checkpoint_storage: Runtime checkpoint storage.
            streaming: Whether to use streaming workflow methods.
            **kwargs: Additional keyword arguments passed through to the underlying
                workflow and tool functions.

        Yields:
            WorkflowEvent objects from the workflow execution.
        """
        # Determine the execution mode based on state.
        # The streaming flag controls the workflow's internal streaming mode,
        # which affects executor behavior (e.g. AgentExecutor emits different event
        # types in streaming vs non-streaming mode).
        if bool(self.pending_requests):
            function_responses = self._process_pending_requests(input_messages)
            if streaming:
                async for event in self.workflow.run(responses=function_responses, stream=True, **kwargs):
                    yield event
            else:
                for event in await self.workflow.run(responses=function_responses, **kwargs):
                    yield event

        elif checkpoint_id is not None:
            if streaming:
                async for event in self.workflow.run(
                    stream=True,
                    checkpoint_id=checkpoint_id,
                    checkpoint_storage=checkpoint_storage,
                    **kwargs,
                ):
                    yield event
            else:
                for event in await self.workflow.run(
                    checkpoint_id=checkpoint_id,
                    checkpoint_storage=checkpoint_storage,
                    **kwargs,
                ):
                    yield event

        else:
            if streaming:
                async for event in self.workflow.run(
                    message=input_messages,
                    stream=True,
                    checkpoint_storage=checkpoint_storage,
                    **kwargs,
                ):
                    yield event
            else:
                for event in await self.workflow.run(
                    message=input_messages,
                    checkpoint_storage=checkpoint_storage,
                    **kwargs,
                ):
                    yield event

    # endregion Run Methods

    def _process_pending_requests(self, input_messages: Sequence[Message]) -> dict[str, Any]:
        """Process pending requests by extracting function responses and updating state.

        Args:
            input_messages: Input messages that may contain function responses.

        Returns:
            A dictionary mapping request IDs to their response data.
        """
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
        return function_responses

    def _convert_workflow_events_to_agent_response(
        self,
        response_id: str,
        output_events: list[WorkflowEvent[Any]],
    ) -> AgentResponse:
        """Convert a list of workflow output events to an AgentResponse."""
        messages: list[Message] = []
        raw_representations: list[object] = []
        merged_usage: UsageDetails | None = None
        latest_created_at: str | None = None

        for output_event in output_events:
            if output_event.type == "request_info":
                function_call, approval_request = self._process_request_info_event(output_event)
                messages.append(
                    Message(
                        contents=[function_call, approval_request],
                        role="assistant",
                        author_name=output_event.source_executor_id,
                        message_id=str(uuid.uuid4()),
                        raw_representation=output_event,
                    )
                )
                raw_representations.append(output_event)
            else:
                data = output_event.data
                if isinstance(data, AgentResponseUpdate):
                    # We cannot support AgentResponseUpdate in non-streaming mode. This is because the message
                    # sequence cannot be guaranteed when there are streaming updates in between non-streaming
                    # responses.
                    raise AgentExecutionException(
                        "Output event with AgentResponseUpdate data cannot be emitted in non-streaming mode. "
                        "Please ensure executors emit AgentResponse for non-streaming workflows."
                    )

                if isinstance(data, AgentResponse):
                    messages.extend(data.messages)
                    raw_representations.append(data.raw_representation)
                    merged_usage = add_usage_details(merged_usage, data.usage_details)
                    latest_created_at = (
                        data.created_at
                        if not latest_created_at
                        else max(latest_created_at, data.created_at)
                        if data.created_at
                        else latest_created_at
                    )
                elif isinstance(data, Message):
                    messages.append(data)
                    raw_representations.append(data.raw_representation)
                elif is_instance_of(data, list[Message]):
                    chat_messages = cast(list[Message], data)
                    messages.extend(chat_messages)
                    raw_representations.append(data)
                else:
                    contents = self._extract_contents(data)
                    if not contents:
                        continue

                    messages.append(
                        Message(
                            contents=contents,
                            role="assistant",
                            author_name=output_event.executor_id,
                            message_id=str(uuid.uuid4()),
                            raw_representation=data,
                        )
                    )
                    raw_representations.append(data)

        return AgentResponse(
            messages=messages,
            response_id=response_id,
            created_at=latest_created_at,
            usage_details=merged_usage,
            raw_representation=raw_representations,
        )

    def _process_request_info_event(
        self,
        event: WorkflowEvent[Any],
    ) -> tuple[Content, Content]:
        """Convert a request_info event to FunctionCallContent and FunctionApprovalRequestContent.

        Args:
            event: A WorkflowEvent with type='request_info'.

        Returns:
            A tuple of (FunctionCallContent, FunctionApprovalRequestContent).
        """
        request_id = event.request_id
        if not request_id:
            raise ValueError("request_info event must have a request_id")

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
        return function_call, approval_request

    def _convert_workflow_event_to_agent_response_updates(
        self,
        response_id: str,
        event: WorkflowEvent[Any],
    ) -> list[AgentResponseUpdate]:
        """Convert a workflow event to a list of AgentResponseUpdate objects.

        Events with type='output' and type='request_info' are processed.
        Other workflow events are ignored as they are workflow-internal.

        For 'output' events, AgentExecutor yields AgentResponseUpdate for streaming updates
        via ctx.yield_output(). This method converts those to agent response updates.

        Returns:
            A list of AgentResponseUpdate objects. Empty list if the event is not relevant.
        """
        if event.type == "output":
            # Convert workflow output to agent response updates.
            # Handle different data types appropriately.
            data = event.data
            executor_id = event.executor_id

            if isinstance(data, AgentResponseUpdate):
                # Pass through AgentResponseUpdate directly (streaming from AgentExecutor)
                if not data.author_name:
                    data.author_name = executor_id
                return [data]
            if isinstance(data, AgentResponse):
                # Convert each message in AgentResponse to an AgentResponseUpdate
                updates: list[AgentResponseUpdate] = []
                for msg in data.messages:
                    updates.append(
                        AgentResponseUpdate(
                            contents=list(msg.contents),
                            role=msg.role,
                            author_name=msg.author_name or executor_id,
                            response_id=data.response_id or response_id,
                            message_id=msg.message_id or str(uuid.uuid4()),
                            created_at=data.created_at
                            or datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                            raw_representation=msg,
                        )
                    )
                return updates
            if isinstance(data, Message):
                return [
                    AgentResponseUpdate(
                        contents=list(data.contents),
                        role=data.role,
                        author_name=data.author_name or executor_id,
                        response_id=response_id,
                        message_id=str(uuid.uuid4()),
                        created_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        raw_representation=data,
                    )
                ]
            if is_instance_of(data, list[Message]):
                # Convert each Message to an AgentResponseUpdate
                chat_messages = cast(list[Message], data)
                updates = []
                for msg in chat_messages:
                    updates.append(
                        AgentResponseUpdate(
                            contents=list(msg.contents),
                            role=msg.role,
                            author_name=msg.author_name or executor_id,
                            response_id=response_id,
                            message_id=msg.message_id or str(uuid.uuid4()),
                            created_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                            raw_representation=msg,
                        )
                    )
                return updates
            contents = self._extract_contents(data)
            if not contents:
                return []
            return [
                AgentResponseUpdate(
                    contents=contents,
                    role="assistant",
                    author_name=executor_id,
                    response_id=response_id,
                    message_id=str(uuid.uuid4()),
                    created_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    raw_representation=data,
                )
            ]

        if event.type == "request_info":
            # Store the pending request for later correlation
            request_id = event.request_id
            if not request_id:
                raise ValueError("request_info event must have a request_id")

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
            return [
                AgentResponseUpdate(
                    contents=[function_call, approval_request],
                    role="assistant",
                    author_name=self.name,
                    response_id=response_id,
                    message_id=str(uuid.uuid4()),
                    created_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                )
            ]

        # Ignore workflow-internal events
        return []

    def _extract_function_responses(self, input_messages: Sequence[Message]) -> dict[str, Any]:
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
        if isinstance(data, list):
            return [c for item in data for c in self._extract_contents(item)]  # type: ignore
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
          AgentResponse.from_updates, then sort by created_at and merge.
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
        final_messages: list[Message] = []
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
                    per_message_responses.append(AgentResponse.from_updates(msg_updates))
            if dangling:
                per_message_responses.append(AgentResponse.from_updates(dangling))

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
            flattened = AgentResponse.from_updates(global_dangling)
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
