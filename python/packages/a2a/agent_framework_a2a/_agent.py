# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import base64
import json
import re
import uuid
from collections.abc import AsyncIterable, Awaitable, Sequence
from typing import Any, Final, Literal, overload

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
    TaskIdParams,
    TaskQueryParams,
    TaskState,
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
    Message,
    ResponseStream,
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
            name: The name of the agent.
            id: The unique identifier for the agent, will be created automatically if not provided.
            description: A brief description of the agent's purpose.
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
        continuation_token: A2AContinuationToken | None = None,
        background: bool = False,
        **kwargs: Any,
    ) -> ResponseStream[AgentResponseUpdate, AgentResponse[Any]]: ...

    def run(
        self,
        messages: AgentRunInputs | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
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
            continuation_token: Optional token to resume a long-running task
                instead of starting a new one.
            background: When True, in-progress task updates surface continuation
                tokens so the caller can poll or resubscribe later. When False
                (default), the agent internally waits for the task to complete.
            kwargs: Additional keyword arguments.

        Returns:
            When stream=False: An Awaitable[AgentResponse].
            When stream=True: A ResponseStream of AgentResponseUpdate items.
        """
        if continuation_token is not None:
            a2a_stream: AsyncIterable[Any] = self.client.resubscribe(TaskIdParams(id=continuation_token["task_id"]))
        else:
            normalized_messages = normalize_messages(messages)
            a2a_message = self._prepare_message_for_a2a(normalized_messages[-1])
            a2a_stream = self.client.send_message(a2a_message)

        response = ResponseStream(
            self._map_a2a_stream(a2a_stream, background=background),
            finalizer=AgentResponse.from_updates,
        )
        if stream:
            return response
        return response.get_final_response()

    async def _map_a2a_stream(
        self,
        a2a_stream: AsyncIterable[Any],
        *,
        background: bool = False,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Map raw A2A protocol items to AgentResponseUpdates.

        Args:
            a2a_stream: The raw A2A event stream.

        Keyword Args:
            background: When False, in-progress task updates are silently
                consumed (the stream keeps iterating until a terminal state).
                When True, they are yielded with a continuation token.
        """
        async for item in a2a_stream:
            if isinstance(item, A2AMessage):
                # Process A2A Message
                contents = self._parse_contents_from_a2a(item.parts)
                yield AgentResponseUpdate(
                    contents=contents,
                    role="assistant" if item.role == A2ARole.agent else "user",
                    response_id=str(getattr(item, "message_id", uuid.uuid4())),
                    raw_representation=item,
                )
            elif isinstance(item, tuple) and len(item) == 2:  # ClientEvent = (Task, UpdateEvent)
                task, _update_event = item
                if isinstance(task, Task):
                    for update in self._updates_from_task(task, background=background):
                        yield update
            else:
                msg = f"Only Message and Task responses are supported from A2A agents. Received: {type(item)}"
                raise NotImplementedError(msg)

    # ------------------------------------------------------------------
    # Task helpers
    # ------------------------------------------------------------------

    def _updates_from_task(self, task: Task, *, background: bool = False) -> list[AgentResponseUpdate]:
        """Convert an A2A Task into AgentResponseUpdate(s).

        Terminal tasks produce updates from their artifacts/history.
        In-progress tasks produce a continuation token update only when
        ``background=True``; otherwise they are silently skipped so the
        caller keeps consuming the stream until completion.
        """
        if task.status.state in TERMINAL_TASK_STATES:
            task_messages = self._parse_messages_from_task(task)
            if task_messages:
                return [
                    AgentResponseUpdate(
                        contents=message.contents,
                        role=message.role,
                        response_id=task.id,
                        message_id=getattr(message.raw_representation, "artifact_id", None),
                        raw_representation=task,
                    )
                    for message in task_messages
                ]
            return [AgentResponseUpdate(contents=[], role="assistant", response_id=task.id, raw_representation=task)]

        if background and task.status.state in IN_PROGRESS_TASK_STATES:
            token = self._build_continuation_token(task)
            return [
                AgentResponseUpdate(
                    contents=[],
                    role="assistant",
                    response_id=task.id,
                    continuation_token=token,
                    raw_representation=task,
                )
            ]

        return []

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

    def _prepare_message_for_a2a(self, message: Message) -> A2AMessage:
        """Prepare a Message for the A2A protocol.

        Transforms Agent Framework Message objects into A2A protocol Messages by:
        - Converting all message contents to appropriate A2A Part types
        - Mapping text content to TextPart objects
        - Converting file references (URI/data/hosted_file) to FilePart objects
        - Preserving metadata and additional properties from the original message
        - Setting the role to 'user' as framework messages are treated as user input
        """
        parts: list[A2APart] = []
        if not message.contents:
            raise ValueError("Message.contents is empty; cannot convert to A2AMessage.")

        # Process ALL contents
        for content in message.contents:
            match content.type:
                case "text":
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
                    parts.append(
                        A2APart(
                            root=FilePart(
                                file=FileWithBytes(
                                    bytes=_get_uri_data(content.uri),  # type: ignore[arg-type]
                                    mime_type=content.media_type,
                                ),
                                metadata=content.additional_properties,
                            )
                        )
                    )
                case "hosted_file":
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

        # Exclude framework-internal keys (e.g. attribution) from wire metadata
        internal_keys = {"_attribution"}
        metadata = {k: v for k, v in message.additional_properties.items() if k not in internal_keys} or None

        return A2AMessage(
            role=A2ARole("user"),
            parts=parts,
            message_id=message.message_id or uuid.uuid4().hex,
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
            raw_representation=artifact,
        )
