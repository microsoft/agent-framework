# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import uuid
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, Final, Literal, TypeAlias, overload

import httpx
from a2a.client import Client, ClientConfig, ClientFactory, minimal_agent_card
from a2a.client.auth.interceptor import AuthInterceptor
from a2a.types import (
    AgentCard,
    Artifact,
    GetTaskRequest,
    SendMessageRequest,
    StreamResponse,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from a2a.types import Message as A2AMessage
from a2a.types import Part as A2APart
from a2a.types import Role as A2ARole
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    ContinuationToken,
    HistoryProvider,
    Message,
    ResponseStream,
    SessionContext,
    normalize_messages,
    prepend_agent_framework_to_user_agent,
)
from agent_framework._types import AgentRunInputs
from agent_framework.observability import AgentTelemetryLayer
from google.protobuf.json_format import MessageToDict

__all__ = ["A2AAgent", "A2AAgentSession", "A2AContinuationToken"]

from agent_framework_a2a._utils import get_uri_data


class A2AAgentSession(AgentSession):
    """Session for A2A-based agents.

    Extends AgentSession with A2A protocol-specific state: context_id for
    conversation tracking, task_id for the most recent task, and task_state
    for detecting input-required continuations vs. task refinements.

    Attributes:
        context_id: The A2A conversation context identifier.
        task_id: The most recent task ID returned by the remote agent.
        task_state: The state of the most recent task (e.g., completed, input-required).
    """

    _CONTEXT_ID_KEY = "a2a_context_id"
    _TASK_ID_KEY = "a2a_task_id"
    _TASK_STATE_KEY = "a2a_task_state"

    def __init__(
        self,
        *,
        context_id: str | None = None,
        task_id: str | None = None,
        task_state: TaskState | None = None,
    ) -> None:
        """Initialize the A2A agent session.

        Keyword Args:
            context_id: Optional A2A context ID for conversation tracking.
            task_id: Optional task ID from a previous interaction.
            task_state: Optional state of the most recent task.
        """
        super().__init__(service_session_id=context_id)
        self.context_id: str | None = context_id
        self.task_id: str | None = task_id
        self.task_state: TaskState | None = task_state

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to a plain dict for storage/transfer."""
        data = super().to_dict()
        if self.context_id is not None:
            data[self._CONTEXT_ID_KEY] = self.context_id
        if self.task_id is not None:
            data[self._TASK_ID_KEY] = self.task_id
        if self.task_state is not None:
            data[self._TASK_STATE_KEY] = self.task_state
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> A2AAgentSession:
        """Restore session from a previously serialized dict.

        Args:
            data: Dict from a previous ``to_dict()`` call.

        Returns:
            Restored A2AAgentSession instance.
        """
        data = dict(data)  # defensive copy
        context_id = data.pop(cls._CONTEXT_ID_KEY, None)
        task_id = data.pop(cls._TASK_ID_KEY, None)
        task_state_value = data.pop(cls._TASK_STATE_KEY, None)

        # TaskState is a protobuf enum (int values); store and restore as-is
        task_state: TaskState | None = task_state_value if task_state_value is not None else None

        # Delegate state deserialization to the base class
        base_session = AgentSession.from_dict(data)

        session = cls(
            context_id=context_id or base_session.service_session_id,
            task_id=task_id,
            task_state=task_state,
        )
        session._session_id = base_session.session_id
        session.state.update(base_session.state)
        return session


class A2AContinuationToken(ContinuationToken):
    """Continuation token for A2A protocol long-running tasks."""

    task_id: str
    """A2A protocol task ID."""
    context_id: str
    """A2A protocol context ID."""


TERMINAL_TASK_STATES = [
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
]
IN_PROGRESS_TASK_STATES = [
    TaskState.TASK_STATE_SUBMITTED,
    TaskState.TASK_STATE_WORKING,
    TaskState.TASK_STATE_INPUT_REQUIRED,
    TaskState.TASK_STATE_AUTH_REQUIRED,
]

A2AStreamItem: TypeAlias = StreamResponse


class A2AAgent(AgentTelemetryLayer, BaseAgent):
    """Agent2Agent (A2A) protocol implementation.

    Wraps an A2A Client to connect the Agent Framework with external A2A-compliant agents
    via HTTP/JSON-RPC. Converts framework Messages to A2A Messages on send, and converts
    A2A responses (Messages/Tasks) back to framework types. Inherits BaseAgent capabilities
    while managing the underlying A2A protocol communication.

    Can be initialized with a URL, AgentCard, or existing A2A Client instance.
    """

    AGENT_PROVIDER_NAME: Final[str] = "A2A"

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        description: str | None = None,
        agent_card: AgentCard | None = None,
        url: str | None = None,
        client: Client | None = None,
        http_client: httpx.AsyncClient | None = None,
        auth_interceptor: AuthInterceptor | None = None,
        timeout: float | httpx.Timeout | None = None,
        supported_protocol_bindings: list[Literal["JSONRPC", "GRPC", "HTTP+JSON"] | str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the A2AAgent.

        Keyword Args:
            name: The name of the agent. Defaults to agent_card.name if agent_card is provided.
            id: The unique identifier for the agent, will be created automatically if not provided.
            description: A brief description of the agent's purpose. Defaults to agent_card.description
                if agent_card is provided.
            agent_card: The agent card for the agent.
            url: The URL for the A2A server.
            client: The A2A client for the agent.
            http_client: Optional httpx.AsyncClient to use.
            auth_interceptor: Optional authentication interceptor for secured endpoints.
            timeout: Request timeout configuration. Can be a float (applied to all timeout components),
                httpx.Timeout object (for full control), or None (uses 10.0s connect, 60.0s read,
                10.0s write, 5.0s pool - optimized for A2A operations).
            supported_protocol_bindings: List of protocol bindings to use for transport negotiation.
                Known values: "JSONRPC", "GRPC", "HTTP+JSON". Defaults to ["JSONRPC"].
                The A2A spec treats this as an open-form string, so custom bindings are also accepted.
            kwargs: any additional properties, passed to BaseAgent.
        """
        # Default name/description from agent_card when not explicitly provided
        if agent_card is not None:
            if name is None:
                name = agent_card.name
            if description is None:
                description = agent_card.description

        super().__init__(id=id, name=name, description=description, **kwargs)
        self._http_client: httpx.AsyncClient | None = http_client
        self._timeout_config = self._create_timeout_config(timeout)
        bindings = supported_protocol_bindings if supported_protocol_bindings is not None else ["JSONRPC"]
        if client is not None:
            self.client = client
            self._non_streaming_client: Client | None = None
            self._close_http_client = True
            return
        if agent_card is None:
            if url is None:
                raise ValueError("Either agent_card or url must be provided")
            # Create minimal agent card from URL
            agent_card = minimal_agent_card(url, bindings)

        # Create or use provided httpx client
        if http_client is None:
            headers = prepend_agent_framework_to_user_agent()
            http_client = httpx.AsyncClient(timeout=self._timeout_config, headers=headers)
            self._http_client = http_client  # Store for cleanup
            self._close_http_client = True

        interceptors = [auth_interceptor] if auth_interceptor is not None else None

        # Create streaming client (SSE transport for stream=True)
        streaming_config = ClientConfig(
            httpx_client=http_client,
            streaming=True,
            supported_protocol_bindings=bindings,
        )
        # Create non-streaming client (single request/response for stream=False)
        non_streaming_config = ClientConfig(
            httpx_client=http_client,
            streaming=False,
            supported_protocol_bindings=bindings,
        )
        streaming_factory = ClientFactory(streaming_config)
        non_streaming_factory = ClientFactory(non_streaming_config)

        # Attempt transport negotiation with the provided agent card
        try:
            self.client = streaming_factory.create(agent_card, interceptors=interceptors)  # type: ignore
            self._non_streaming_client = non_streaming_factory.create(
                agent_card,
                interceptors=interceptors,  # type: ignore
            )
        except Exception as transport_error:
            # Transport negotiation failed - fall back to minimal agent card with JSONRPC
            fallback_url = agent_card.supported_interfaces[0].url if agent_card.supported_interfaces else url
            if not fallback_url:
                raise ValueError(
                    "A2A transport negotiation failed and no fallback URL is available. "
                    "Provide a 'url' argument or ensure 'agent_card.supported_interfaces' "
                    "contains at least one interface with a URL."
                ) from transport_error
            fallback_card = minimal_agent_card(fallback_url, bindings)
            try:
                self.client = streaming_factory.create(fallback_card, interceptors=interceptors)  # type: ignore
                self._non_streaming_client = non_streaming_factory.create(
                    fallback_card,
                    interceptors=interceptors,  # type: ignore
                )
            except Exception as fallback_error:
                raise RuntimeError(
                    f"A2A transport negotiation failed. "
                    f"Primary error: {transport_error}. "
                    f"Fallback error: {fallback_error}"
                ) from transport_error

    def _create_timeout_config(self, timeout: float | httpx.Timeout | None) -> httpx.Timeout:
        """Create httpx.Timeout configuration from user input.

        Args:
            timeout: User-provided timeout configuration

        Returns:
            Configured httpx.Timeout object
        """
        if timeout is None:
            # Default timeout configuration (preserving original values)
            return httpx.Timeout(
                connect=10.0,  # 10 seconds to establish connection
                read=60.0,  # 60 seconds to read response (A2A operations can take time)
                write=10.0,  # 10 seconds to send request
                pool=5.0,  # 5 seconds to get connection from pool
            )
        if isinstance(timeout, float):
            # Simple timeout
            return httpx.Timeout(timeout)
        if isinstance(timeout, httpx.Timeout):
            # Full timeout configuration provided by user
            return timeout
        msg = f"Invalid timeout type: {type(timeout)}. Expected float, httpx.Timeout, or None."
        raise TypeError(msg)

    async def __aenter__(self) -> A2AAgent:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit with httpx client cleanup."""
        # Close our httpx client if we created it
        if self._http_client is not None and self._close_http_client:
            await self._http_client.aclose()

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[False] = ...,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        continuation_token: A2AContinuationToken | None = None,
        background: bool = False,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]]: ...

    @overload
    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: Literal[True],
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        continuation_token: A2AContinuationToken | None = None,
        background: bool = False,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
        continuation_token: A2AContinuationToken | None = None,
        background: bool = False,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse[Any]] | ResponseStream[AgentResponseUpdate, AgentResponse[Any]]:
        """Get a response from the agent.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            stream: Whether to stream the response. Defaults to False.
            session: The conversation session associated with the message(s).
            function_invocation_kwargs: Present for compatibility with the shared agent interface.
                A2AAgent does not use these values directly.
            client_kwargs: Present for compatibility with the shared agent interface.
                A2AAgent does not use these values directly.
            kwargs: Additional compatibility keyword arguments.
                A2AAgent does not use these values directly.
            continuation_token: Optional token to resume a long-running task
                instead of starting a new one.
            background: When True, in-progress task updates surface continuation
                tokens so the caller can poll or resubscribe later. When False
                (default), the agent internally waits for the task to complete.

        Returns:
            When stream=False: An Awaitable[AgentResponse].
            When stream=True: A ResponseStream of AgentResponseUpdate items.
        """
        del function_invocation_kwargs, client_kwargs, kwargs
        normalized_messages = normalize_messages(messages)

        # Use non-streaming transport for non-streaming calls when available.
        # This sends a single HTTP request/response instead of opening an SSE
        # connection, matching the protocol's intent for synchronous operations.
        active_client = (
            self._non_streaming_client if (not stream and self._non_streaming_client is not None) else self.client
        )

        if continuation_token is not None:
            a2a_stream: AsyncIterable[A2AStreamItem] = self.client.subscribe(
                SubscribeToTaskRequest(id=continuation_token["task_id"])
            )
        else:
            if not normalized_messages:
                raise ValueError("At least one message is required when starting a new task (no continuation_token).")
            a2a_message = self._prepare_message_for_a2a(normalized_messages[-1], session=session)
            request = SendMessageRequest(message=a2a_message)
            if background and not stream:
                # return_immediately only applies to non-streaming (message/send)
                request.configuration.return_immediately = True
            a2a_stream = active_client.send_message(request)

        provider_session = session
        if provider_session is None and self.context_providers:
            provider_session = AgentSession()

        session_context = SessionContext(
            session_id=provider_session.session_id if provider_session else None,
            service_session_id=provider_session.service_session_id if provider_session else None,
            input_messages=normalized_messages or [],
            options={},
        )

        response = ResponseStream(
            self._map_a2a_stream(
                a2a_stream,
                background=background,
                emit_intermediate=stream,
                session=provider_session,
                session_context=session_context,
            ),
            finalizer=AgentResponse.from_updates,
        )
        if stream:
            return response
        return response.get_final_response()

    async def _map_a2a_stream(
        self,
        a2a_stream: AsyncIterable[A2AStreamItem],
        *,
        background: bool = False,
        emit_intermediate: bool = False,
        session: AgentSession | None = None,
        session_context: SessionContext | None = None,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Map raw A2A protocol items to AgentResponseUpdates.

        Args:
            a2a_stream: The raw A2A event stream.

        Keyword Args:
            background: When False, in-progress task updates are silently
                consumed (the stream keeps iterating until a terminal state).
                When True, they are yielded with a continuation token.
            emit_intermediate: When True, in-progress status updates that
                carry message content are yielded to the caller.  Typically
                set for streaming callers so non-streaming consumers only
                receive terminal task outputs.
            session: The agent session for context providers.
            session_context: The session context for context providers.
        """
        if session_context is None:
            session_context = SessionContext(input_messages=[], options={})

        # Run before_run providers (forward order)
        for provider in self.context_providers:
            if isinstance(provider, HistoryProvider) and not provider.load_messages:
                continue
            if session is None:
                raise RuntimeError("Provider session must be available when context providers are configured.")
            await provider.before_run(
                agent=self,  # type: ignore[arg-type]
                session=session,
                context=session_context,
                state=session.state.setdefault(provider.source_id, {}),
            )

        all_updates: list[AgentResponseUpdate] = []
        streamed_artifact_ids_by_task: dict[str, set[str]] = {}
        last_task_id: str | None = None
        last_context_id: str | None = None
        last_task_state: TaskState | None = None
        # In non-streaming mode, accumulate intermediate status content so it
        # can be surfaced when the terminal event arrives (mirroring v0.3.x
        # behavior where the full Task history was available at completion).
        pending_updates_by_task: dict[str, list[AgentResponseUpdate]] = {}
        async for item in a2a_stream:
            payload_type = item.WhichOneof("payload")
            if payload_type == "message":
                # Process A2A Message
                msg = item.message
                if msg.context_id:
                    last_context_id = msg.context_id
                contents = self._parse_contents_from_a2a(msg.parts)
                metadata = MessageToDict(msg.metadata) if msg.metadata else None
                update = AgentResponseUpdate(
                    contents=contents,
                    role="assistant" if msg.role == A2ARole.ROLE_AGENT else "user",
                    response_id=msg.message_id or str(uuid.uuid4()),
                    message_id=msg.message_id,
                    additional_properties={"a2a_metadata": metadata} if metadata else None,
                    raw_representation=msg,
                )
                all_updates.append(update)
                yield update
            elif payload_type == "task":
                task = item.task
                last_task_id = task.id
                if task.context_id:
                    last_context_id = task.context_id
                last_task_state = task.status.state
                updates = self._updates_from_task(
                    task,
                    background=background,
                    emit_intermediate=emit_intermediate,
                    streamed_artifact_ids=streamed_artifact_ids_by_task.get(task.id),
                )
                if task.status.state in TERMINAL_TASK_STATES:
                    streamed_artifact_ids_by_task.pop(task.id, None)
                    # If the terminal Task has no content, flush accumulated updates
                    if not updates or all(not u.contents for u in updates):
                        pending = pending_updates_by_task.pop(task.id, [])
                        for update in pending:
                            all_updates.append(update)
                            yield update
                    else:
                        pending_updates_by_task.pop(task.id, None)
                for update in updates:
                    all_updates.append(update)
                    yield update
            elif payload_type == "status_update":
                status_event = item.status_update
                last_task_id = status_event.task_id
                if status_event.context_id:
                    last_context_id = status_event.context_id
                last_task_state = status_event.status.state
                updates = self._updates_from_task_update_event(status_event)
                is_terminal = status_event.status.state in TERMINAL_TASK_STATES
                is_input_required = status_event.status.state == TaskState.TASK_STATE_INPUT_REQUIRED
                if emit_intermediate:
                    for update in updates:
                        all_updates.append(update)
                        yield update
                elif is_terminal or is_input_required:
                    if updates:
                        # Terminal/input-required event with content — discard accumulated intermediates
                        pending_updates_by_task.pop(status_event.task_id, None)
                        for update in updates:
                            all_updates.append(update)
                            yield update
                    elif is_terminal:
                        # Terminal event with NO content — flush accumulated updates
                        pending = pending_updates_by_task.pop(status_event.task_id, [])
                        for update in pending:
                            all_updates.append(update)
                            yield update
                else:
                    # Non-streaming intermediate: accumulate for later
                    if updates:
                        pending_updates_by_task.setdefault(status_event.task_id, []).extend(updates)
            elif payload_type == "artifact_update":
                artifact_event = item.artifact_update
                last_task_id = artifact_event.task_id
                if artifact_event.context_id:
                    last_context_id = artifact_event.context_id
                updates = self._updates_from_task_update_event(artifact_event)
                # Always yield artifact updates — they carry actual response
                # content (files, data).  Track IDs so that a subsequent
                # terminal Task doesn't duplicate the same artifacts.
                if updates:
                    streamed_artifact_ids_by_task.setdefault(artifact_event.task_id, set()).add(
                        artifact_event.artifact.artifact_id
                    )
                for update in updates:
                    all_updates.append(update)
                    yield update
            else:
                raise NotImplementedError(f"Unsupported StreamResponse payload: {payload_type}")

        # Set the response on the context for after_run providers
        if all_updates:
            session_context._response = AgentResponse.from_updates(all_updates)  # type: ignore[assignment]

        # Persist A2A protocol state on the session for follow-up message linking.
        if isinstance(session, A2AAgentSession) and (last_task_id or last_context_id):
            # Validate context_id consistency
            if session.context_id is not None and last_context_id and session.context_id != last_context_id:
                raise RuntimeError(
                    f"The context_id returned from the A2A agent ('{last_context_id}') "
                    f"differs from the session's context_id ('{session.context_id}')."
                )
            # Assign server-generated context_id if not already set
            if session.context_id is None and last_context_id:
                session.context_id = last_context_id
                session.service_session_id = last_context_id
            if last_task_id:
                session.task_id = last_task_id
                session.task_state = last_task_state

        await self._run_after_providers(session=session, context=session_context)

    # ------------------------------------------------------------------
    # Task helpers
    # ------------------------------------------------------------------

    def _updates_from_task(
        self,
        task: Task,
        *,
        background: bool = False,
        emit_intermediate: bool = False,
        streamed_artifact_ids: set[str] | None = None,
    ) -> list[AgentResponseUpdate]:
        """Convert an A2A Task into AgentResponseUpdate(s).

        Terminal tasks produce updates from their artifacts/history.
        In-progress tasks produce a continuation token update when
        ``background=True``.  When ``emit_intermediate=True`` (typically
        set for streaming callers), any message content attached to an
        in-progress status update is surfaced; otherwise the update is
        silently skipped so the caller keeps consuming the stream until
        completion.
        """
        status = task.status
        task_metadata = MessageToDict(task.metadata) if task.metadata else None

        if status.state in TERMINAL_TASK_STATES:
            task_messages = self._parse_messages_from_task(task)
            if task.artifacts and streamed_artifact_ids:
                task_messages = [
                    message
                    for message in task_messages
                    if getattr(message.raw_representation, "artifact_id", None) not in streamed_artifact_ids
                ]
            if task_messages:
                return [
                    AgentResponseUpdate(
                        contents=message.contents,
                        role=message.role,
                        response_id=task.id,
                        message_id=getattr(message.raw_representation, "artifact_id", None),
                        additional_properties={"a2a_metadata": merged}
                        if (merged := {**message.additional_properties, **(task_metadata or {})})
                        else None,
                        raw_representation=task,
                    )
                    for message in task_messages
                ]
            if task.artifacts:
                return []
            return [
                AgentResponseUpdate(
                    contents=[],
                    role="assistant",
                    response_id=task.id,
                    additional_properties={"a2a_metadata": task_metadata} if task_metadata else None,
                    raw_representation=task,
                )
            ]

        if background and status.state in IN_PROGRESS_TASK_STATES:
            token = self._build_continuation_token(task)
            return [
                AgentResponseUpdate(
                    contents=[],
                    role="assistant",
                    response_id=task.id,
                    continuation_token=token,
                    additional_properties={"a2a_metadata": task_metadata} if task_metadata else None,
                    raw_representation=task,
                )
            ]

        # Surface message content from in-progress status updates (e.g. working state)
        if (
            emit_intermediate
            and status.state in IN_PROGRESS_TASK_STATES
            and status.HasField("message")
            and status.message.parts
        ):
            contents = self._parse_contents_from_a2a(status.message.parts)
            if contents:
                return [
                    AgentResponseUpdate(
                        contents=contents,
                        role="assistant" if status.message.role == A2ARole.ROLE_AGENT else "user",
                        response_id=task.id,
                        additional_properties={"a2a_metadata": task_metadata} if task_metadata else None,
                        raw_representation=task,
                    )
                ]

        return []

    def _updates_from_task_update_event(
        self, update_event: TaskStatusUpdateEvent | TaskArtifactUpdateEvent
    ) -> list[AgentResponseUpdate]:
        """Convert A2A task update events into streaming AgentResponseUpdates."""
        if isinstance(update_event, TaskArtifactUpdateEvent):
            contents = self._parse_contents_from_a2a(update_event.artifact.parts)
            if not contents:
                return []
            artifact_meta = MessageToDict(update_event.artifact.metadata) if update_event.artifact.metadata else {}
            event_meta = MessageToDict(update_event.metadata) if update_event.metadata else {}
            merged_metadata = {**artifact_meta, **event_meta} or None
            return [
                AgentResponseUpdate(
                    contents=contents,
                    role="assistant",
                    response_id=update_event.task_id,
                    message_id=update_event.artifact.artifact_id,
                    additional_properties={"a2a_metadata": merged_metadata} if merged_metadata else None,
                    raw_representation=update_event,
                )
            ]

        if not isinstance(update_event, TaskStatusUpdateEvent):
            return []

        if not update_event.status.HasField("message") or not update_event.status.message.parts:
            return []

        state = update_event.status.state
        if state not in TERMINAL_TASK_STATES and state != TaskState.TASK_STATE_INPUT_REQUIRED:
            return []

        message = update_event.status.message
        contents = self._parse_contents_from_a2a(message.parts)
        if not contents:
            return []

        msg_meta = MessageToDict(message.metadata) if message.metadata else {}
        event_meta = MessageToDict(update_event.metadata) if update_event.metadata else {}
        merged_metadata = {**msg_meta, **event_meta} or None

        return [
            AgentResponseUpdate(
                contents=contents,
                role="assistant" if message.role == A2ARole.ROLE_AGENT else "user",
                response_id=update_event.task_id,
                message_id=message.message_id,
                additional_properties={"a2a_metadata": merged_metadata} if merged_metadata else None,
                raw_representation=update_event,
            )
        ]

    @staticmethod
    def _build_continuation_token(task: Task) -> A2AContinuationToken | None:
        """Build an A2AContinuationToken from an A2A Task if it is still in progress."""
        if task.status.state in IN_PROGRESS_TASK_STATES:
            return A2AContinuationToken(task_id=task.id, context_id=task.context_id)
        return None

    async def poll_task(self, continuation_token: A2AContinuationToken) -> AgentResponse[Any]:
        """Poll for the current state of a long-running A2A task.

        Unlike ``run(continuation_token=...)``, which resubscribes to the SSE
        stream, this performs a single request to retrieve the task state.

        Args:
            continuation_token: A token previously obtained from a response's
                ``continuation_token`` field.

        Returns:
            An AgentResponse whose ``continuation_token`` is set when the task
            is still in progress, or ``None`` when it has reached a terminal state.
        """
        task_id = continuation_token["task_id"]
        task = await self.client.get_task(GetTaskRequest(id=task_id))
        updates = self._updates_from_task(task, background=True)
        if updates:
            return AgentResponse.from_updates(updates)
        return AgentResponse(messages=[], response_id=task.id, raw_representation=task)

    def _prepare_message_for_a2a(self, message: Message, *, session: AgentSession | None = None) -> A2AMessage:
        """Prepare a Message for the A2A protocol.

        Transforms Agent Framework Message objects into A2A protocol Messages by:
        - Converting all message contents to appropriate A2A Part types
        - Mapping text content to TextPart objects
        - Converting file references (URI/data/hosted_file) to FilePart objects
        - Preserving metadata and additional properties from the original message
        - Setting the role to 'user' as framework messages are treated as user input
        - Linking follow-up messages to previous tasks via reference_task_ids or task_id

        When the session is an ``A2AAgentSession``, the method reads context_id,
        task_id, and task_state directly. If the task is in INPUT_REQUIRED state,
        the outbound message's ``task_id`` is set (continuing the same task);
        otherwise ``reference_task_ids`` is used for task refinement linking.

        Args:
            message: The framework Message to convert.

        Keyword Args:
            session: Optional session to read A2A state from. If an
                ``A2AAgentSession``, context_id/task_id/task_state are used for
                linking. A plain ``AgentSession`` provides service_session_id as
                a fallback context_id.
        """
        # Extract A2A state from the session
        context_id: str | None = None
        previous_task_id: str | None = None
        task_state: TaskState | None = None
        if isinstance(session, A2AAgentSession):
            context_id = session.context_id
            previous_task_id = session.task_id
            task_state = session.task_state
        elif session is not None:
            context_id = session.service_session_id

        parts: list[A2APart] = []
        if not message.contents:
            raise ValueError("Message.contents is empty; cannot convert to A2AMessage.")

        # Process ALL contents
        for content in message.contents:
            match content.type:
                case "text":
                    if content.text is None:
                        raise ValueError("Text content requires a non-null text value")
                    parts.append(
                        A2APart(
                            text=content.text,
                            metadata=content.additional_properties or {},
                        )
                    )
                case "error":
                    parts.append(
                        A2APart(
                            text=content.message or "An error occurred.",
                            metadata=content.additional_properties or {},
                        )
                    )
                case "uri":
                    if content.uri is None:
                        raise ValueError("URI content requires a non-null uri value")
                    parts.append(
                        A2APart(
                            url=content.uri,
                            media_type=content.media_type or "",
                            metadata=content.additional_properties or {},
                        )
                    )
                case "data":
                    if content.uri is None:
                        raise ValueError("Data content requires a non-null uri value")
                    base64_data = get_uri_data(content.uri)
                    parts.append(
                        A2APart(
                            raw=base64.b64decode(base64_data),
                            media_type=content.media_type or "",
                            metadata=content.additional_properties or {},
                        )
                    )
                case "hosted_file":
                    if content.file_id is None:
                        raise ValueError("Hosted file content requires a non-null file_id value")
                    parts.append(
                        A2APart(
                            url=content.file_id,
                            metadata=content.additional_properties or {},
                        )
                    )
                case _:
                    raise ValueError(f"Unknown content type: {content.type}")

        a2a_metadata = message.additional_properties.get("a2a_metadata")

        a2a_message = A2AMessage(
            role=A2ARole.ROLE_USER,
            parts=parts,
            message_id=message.message_id or uuid.uuid4().hex,
            context_id=context_id,
            metadata=a2a_metadata or {},
        )

        if previous_task_id:
            if task_state == TaskState.TASK_STATE_INPUT_REQUIRED:
                # Task is waiting for user input — set task_id to continue the same task
                a2a_message.task_id = previous_task_id
            else:
                # Link as a follow-up (task refinement)
                a2a_message.reference_task_ids.append(previous_task_id)

        return a2a_message

    def _parse_contents_from_a2a(self, parts: Sequence[A2APart]) -> list[Content]:
        """Parse A2A Parts into Agent Framework Content.

        Transforms A2A protocol Parts into framework-native Content objects,
        handling text, url, raw, and data parts with metadata preservation.
        """
        contents: list[Content] = []
        for part in parts:
            part_metadata = MessageToDict(part.metadata) if part.metadata else None
            content_type = part.WhichOneof("content")
            match content_type:
                case "text":
                    contents.append(
                        Content.from_text(
                            text=part.text,
                            additional_properties=part_metadata,
                            raw_representation=part,
                        )
                    )
                case "url":
                    contents.append(
                        Content.from_uri(
                            uri=part.url,
                            media_type=part.media_type or "",
                            additional_properties=part_metadata,
                            raw_representation=part,
                        )
                    )
                case "raw":
                    contents.append(
                        Content.from_data(
                            data=part.raw,
                            media_type=part.media_type or "",
                            additional_properties=part_metadata,
                            raw_representation=part,
                        )
                    )
                case "data":
                    from google.protobuf.json_format import MessageToJson

                    contents.append(
                        Content.from_text(
                            text=MessageToJson(part.data),
                            additional_properties=part_metadata,
                            raw_representation=part,
                        )
                    )
                case _:
                    raise ValueError(f"Unknown Part content type: {content_type}")
        return contents

    def _parse_messages_from_task(self, task: Task) -> list[Message]:
        """Parse A2A Task artifacts into Messages with ASSISTANT role."""
        messages: list[Message] = []

        if task.artifacts:
            for artifact in task.artifacts:
                messages.append(self._parse_message_from_artifact(artifact))
        elif task.history:
            # Include the last history item as the agent response
            history_item = task.history[-1]
            contents = self._parse_contents_from_a2a(history_item.parts)
            history_metadata = MessageToDict(history_item.metadata) if history_item.metadata else None
            messages.append(
                Message(
                    role="assistant" if history_item.role == A2ARole.ROLE_AGENT else "user",
                    contents=contents,
                    additional_properties=history_metadata,
                    raw_representation=history_item,
                )
            )

        return messages

    def _parse_message_from_artifact(self, artifact: Artifact) -> Message:
        """Parse A2A Artifact into Message using part contents."""
        contents = self._parse_contents_from_a2a(artifact.parts)
        artifact_metadata = MessageToDict(artifact.metadata) if artifact.metadata else None
        return Message(
            role="assistant",
            contents=contents,
            additional_properties=artifact_metadata,
            raw_representation=artifact,
        )
