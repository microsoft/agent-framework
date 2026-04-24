# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import json
import re
import uuid
from collections.abc import AsyncIterable, Awaitable, Mapping, Sequence
from typing import Any, Final, Literal, TypeAlias, overload

import httpx
from a2a.client import Client, ClientConfig, ClientFactory, minimal_agent_card
from a2a.client.auth.interceptor import AuthInterceptor
from a2a.types import (
    AgentCard,
    Artifact,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Task,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskQueryParams,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
    TransportProtocol,
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

__all__ = ["A2AAgent", "A2AContinuationToken"]

URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$")


class A2AContinuationToken(ContinuationToken):
    """Continuation token for A2A protocol long-running tasks."""

    task_id: str
    """A2A protocol task ID."""
    context_id: str
    """A2A protocol context ID."""


TERMINAL_TASK_STATES = [
    TaskState.completed,
    TaskState.failed,
    TaskState.canceled,
    TaskState.rejected,
]
IN_PROGRESS_TASK_STATES = [
    TaskState.submitted,
    TaskState.working,
    TaskState.input_required,
    TaskState.auth_required,
]

A2AClientEvent: TypeAlias = tuple[Task, TaskStatusUpdateEvent | TaskArtifactUpdateEvent | None]
A2AStreamItem: TypeAlias = A2AMessage | A2AClientEvent


def _get_uri_data(uri: str) -> str:
    match = URI_PATTERN.match(uri)
    if not match:
        raise ValueError(f"Invalid data URI format: {uri}")

    return match.group("base64_data")


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
        if client is not None:
            self.client = client
            self._close_http_client = True
            return
        if agent_card is None:
            if url is None:
                raise ValueError("Either agent_card or url must be provided")
            # Create minimal agent card from URL
            agent_card = minimal_agent_card(url, [TransportProtocol.jsonrpc])

        # Create or use provided httpx client
        if http_client is None:
            headers = prepend_agent_framework_to_user_agent()
            http_client = httpx.AsyncClient(timeout=self._timeout_config, headers=headers)
            self._http_client = http_client  # Store for cleanup
            self._close_http_client = True

        # Create A2A client using factory
        config = ClientConfig(
            httpx_client=http_client,
            supported_transports=[TransportProtocol.jsonrpc],
        )
        factory = ClientFactory(config)
        interceptors = [auth_interceptor] if auth_interceptor is not None else None

        # Attempt transport negotiation with the provided agent card
        try:
            self.client = factory.create(agent_card, interceptors=interceptors)  # type: ignore
        except Exception as transport_error:
            # Transport negotiation failed - fall back to minimal agent card with JSONRPC
            fallback_card = minimal_agent_card(agent_card.url, [TransportProtocol.jsonrpc])
            try:
                self.client = factory.create(fallback_card, interceptors=interceptors)  # type: ignore
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

        if continuation_token is not None:
            a2a_stream: AsyncIterable[A2AStreamItem] = self.client.resubscribe(
                TaskIdParams(id=continuation_token["task_id"])
            )
        else:
            if not normalized_messages:
                raise ValueError("At least one message is required when starting a new task (no continuation_token).")
            a2a_message = self._prepare_message_for_a2a(
                normalized_messages[-1],
                context_id=session.service_session_id if session else None,
            )
            a2a_stream = self.client.send_message(a2a_message)

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
        async for item in a2a_stream:
            if isinstance(item, A2AMessage):
                # Process A2A Message
                contents = self._parse_contents_from_a2a(item.parts)
                update = AgentResponseUpdate(
                    contents=contents,
                    role="assistant" if item.role == A2ARole.agent else "user",
                    response_id=str(getattr(item, "message_id", uuid.uuid4())),
                    additional_properties={"a2a_metadata": item.metadata} if item.metadata else None,
                    raw_representation=item,
                )
                all_updates.append(update)
                yield update
            elif isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], Task):
                task, update_event = item
                updates = self._updates_from_task(
                    task,
                    update_event=update_event,
                    background=background,
                    emit_intermediate=emit_intermediate,
                    streamed_artifact_ids=streamed_artifact_ids_by_task.get(task.id),
                )
                if isinstance(update_event, TaskArtifactUpdateEvent) and any(
                    update.raw_representation is update_event for update in updates
                ):
                    streamed_artifact_ids_by_task.setdefault(task.id, set()).add(update_event.artifact.artifact_id)
                if task.status.state in TERMINAL_TASK_STATES:
                    streamed_artifact_ids_by_task.pop(task.id, None)
                for update in updates:
                    all_updates.append(update)
                    yield update
            else:
                raise NotImplementedError("Only Message and Task responses are supported")

        # Set the response on the context for after_run providers
        if all_updates:
            session_context._response = AgentResponse.from_updates(all_updates)  # type: ignore[assignment]

        await self._run_after_providers(session=session, context=session_context)

    # ------------------------------------------------------------------
    # Task helpers
    # ------------------------------------------------------------------

    def _updates_from_task(
        self,
        task: Task,
        *,
        update_event: TaskStatusUpdateEvent | TaskArtifactUpdateEvent | None = None,
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

        if (
            emit_intermediate
            and update_event is not None
            and (event_updates := self._updates_from_task_update_event(update_event))
        ):
            return event_updates

        if status.state in TERMINAL_TASK_STATES:
            task_messages = self._parse_messages_from_task(task)
            if task.artifacts is not None and streamed_artifact_ids:
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
                        if (merged := {**message.additional_properties, **(task.metadata or {})})
                        else None,
                        raw_representation=task,
                    )
                    for message in task_messages
                ]
            if task.artifacts is not None:
                return []
            return [
                AgentResponseUpdate(
                    contents=[],
                    role="assistant",
                    response_id=task.id,
                    additional_properties={"a2a_metadata": task.metadata} if task.metadata else None,
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
                    additional_properties={"a2a_metadata": task.metadata} if task.metadata else None,
                    raw_representation=task,
                )
            ]

        # Surface message content from in-progress status updates (e.g. working state)
        # Only emitted when the caller opts in (streaming), so non-streaming
        # consumers keep receiving only terminal task outputs.
        if (
            emit_intermediate
            and status.state in IN_PROGRESS_TASK_STATES
            and status.message is not None
            and status.message.parts
        ):
            contents = self._parse_contents_from_a2a(status.message.parts)
            if contents:
                return [
                    AgentResponseUpdate(
                        contents=contents,
                        role="assistant" if status.message.role == A2ARole.agent else "user",
                        response_id=task.id,
                        additional_properties={"a2a_metadata": task.metadata} if task.metadata else None,
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
            merged_metadata = {
                **(update_event.artifact.metadata or {}),
                **(update_event.metadata or {}),
            } or None
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

        message = update_event.status.message
        if message is None or not message.parts:
            return []

        contents = self._parse_contents_from_a2a(message.parts)
        if not contents:
            return []

        merged_metadata = {
            **(message.metadata or {}),
            **(update_event.metadata or {}),
        } or None
        return [
            AgentResponseUpdate(
                contents=contents,
                role="assistant" if message.role == A2ARole.agent else "user",
                response_id=update_event.task_id,
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
        task = await self.client.get_task(TaskQueryParams(id=task_id))
        updates = self._updates_from_task(task, background=True)
        if updates:
            return AgentResponse.from_updates(updates)
        return AgentResponse(messages=[], response_id=task.id, raw_representation=task)

    def _prepare_message_for_a2a(self, message: Message, *, context_id: str | None = None) -> A2AMessage:
        """Prepare a Message for the A2A protocol.

        Transforms Agent Framework Message objects into A2A protocol Messages by:
        - Converting all message contents to appropriate A2A Part types
        - Mapping text content to TextPart objects
        - Converting file references (URI/data/hosted_file) to FilePart objects
        - Preserving metadata and additional properties from the original message
        - Setting the role to 'user' as framework messages are treated as user input

        Args:
            message: The framework Message to convert.
            context_id: Optional fallback context identifier (e.g. derived from
                ``AgentSession.service_session_id``). When the *message* already
                carries a ``context_id`` in its ``additional_properties`` that
                value takes precedence; otherwise this fallback is used.
        """
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
                            root=TextPart(
                                text=content.text,
                                metadata=content.additional_properties,
                            )
                        )
                    )
                case "error":
                    parts.append(
                        A2APart(
                            root=TextPart(
                                text=content.message or "An error occurred.",
                                metadata=content.additional_properties,
                            )
                        )
                    )
                case "uri":
                    if content.uri is None:
                        raise ValueError("URI content requires a non-null uri value")
                    parts.append(
                        A2APart(
                            root=FilePart(
                                file=FileWithUri(
                                    uri=content.uri,
                                    mime_type=content.media_type,
                                ),
                                metadata=content.additional_properties,
                            )
                        )
                    )
                case "data":
                    if content.uri is None:
                        raise ValueError("Data content requires a non-null uri value")
                    parts.append(
                        A2APart(
                            root=FilePart(
                                file=FileWithBytes(
                                    bytes=_get_uri_data(content.uri),
                                    mime_type=content.media_type,
                                ),
                                metadata=content.additional_properties,
                            )
                        )
                    )
                case "hosted_file":
                    if content.file_id is None:
                        raise ValueError("Hosted file content requires a non-null file_id value")
                    parts.append(
                        A2APart(
                            root=FilePart(
                                file=FileWithUri(
                                    uri=content.file_id,
                                    mime_type=None,  # HostedFileContent doesn't specify media_type
                                ),
                                metadata=content.additional_properties,
                            )
                        )
                    )
                case _:
                    raise ValueError(f"Unknown content type: {content.type}")

        metadata = message.additional_properties.get("a2a_metadata")

        return A2AMessage(
            role=A2ARole("user"),
            parts=parts,
            message_id=message.message_id or uuid.uuid4().hex,
            context_id=message.additional_properties.get("context_id") or context_id,
            metadata=metadata,
        )

    def _parse_contents_from_a2a(self, parts: Sequence[A2APart]) -> list[Content]:
        """Parse A2A Parts into Agent Framework Content.

        Transforms A2A protocol Parts into framework-native Content objects,
        handling text, file (URI/bytes), and data parts with metadata preservation.
        """
        contents: list[Content] = []
        for part in parts:
            inner_part = part.root
            match inner_part.kind:
                case "text":
                    contents.append(
                        Content.from_text(
                            text=inner_part.text,
                            additional_properties=inner_part.metadata,
                            raw_representation=inner_part,
                        )
                    )
                case "file":
                    if isinstance(inner_part.file, FileWithUri):
                        contents.append(
                            Content.from_uri(
                                uri=inner_part.file.uri,
                                media_type=inner_part.file.mime_type or "",
                                additional_properties=inner_part.metadata,
                                raw_representation=inner_part,
                            )
                        )
                    elif isinstance(inner_part.file, FileWithBytes):
                        contents.append(
                            Content.from_data(
                                data=base64.b64decode(inner_part.file.bytes),
                                media_type=inner_part.file.mime_type or "",
                                additional_properties=inner_part.metadata,
                                raw_representation=inner_part,
                            )
                        )
                case "data":
                    contents.append(
                        Content.from_text(
                            text=json.dumps(inner_part.data),
                            additional_properties=inner_part.metadata,
                            raw_representation=inner_part,
                        )
                    )
                case _:
                    raise ValueError(f"Unknown Part kind: {inner_part.kind}")
        return contents

    def _parse_messages_from_task(self, task: Task) -> list[Message]:
        """Parse A2A Task artifacts into Messages with ASSISTANT role."""
        messages: list[Message] = []

        if task.artifacts is not None:
            for artifact in task.artifacts:
                messages.append(self._parse_message_from_artifact(artifact))
        elif task.history is not None and len(task.history) > 0:
            # Include the last history item as the agent response
            history_item = task.history[-1]
            contents = self._parse_contents_from_a2a(history_item.parts)
            messages.append(
                Message(
                    role="assistant" if history_item.role == A2ARole.agent else "user",
                    contents=contents,
                    additional_properties=history_item.metadata,
                    raw_representation=history_item,
                )
            )

        return messages

    def _parse_message_from_artifact(self, artifact: Artifact) -> Message:
        """Parse A2A Artifact into Message using part contents."""
        contents = self._parse_contents_from_a2a(artifact.parts)
        return Message(
            role="assistant",
            contents=contents,
            additional_properties=artifact.metadata,
            raw_representation=artifact,
        )
