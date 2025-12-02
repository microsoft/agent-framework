# Copyright (c) Microsoft. All rights reserved.

import base64
import json
import re
import uuid
from collections.abc import AsyncIterable, Sequence
from typing import Any, cast

import httpx
from a2a.client import Client, ClientConfig, ClientFactory, minimal_agent_card
from a2a.client.auth.interceptor import AuthInterceptor
from a2a.types import (
    AgentCard,
    Artifact,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Message,
    Task,
    TaskState,
    TextPart,
    TransportProtocol,
)
from a2a.types import Message as A2AMessage
from a2a.types import Part as A2APart
from a2a.types import Role as A2ARole
from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AgentThread,
    BaseAgent,
    ChatMessage,
    Contents,
    DataContent,
    Role,
    TextContent,
    UriContent,
    prepend_agent_framework_to_user_agent,
)

__all__ = ["A2AAgent"]

URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$")
TERMINAL_TASK_STATES = [
    TaskState.completed,
    TaskState.failed,
    TaskState.canceled,
    TaskState.rejected,
]


def _get_uri_data(uri: str) -> str:
    match = URI_PATTERN.match(uri)
    if not match:
        raise ValueError(f"Invalid data URI format: {uri}")

    return match.group("base64_data")


class A2AAgent(BaseAgent):
    """Agent2Agent (A2A) protocol implementation.

    Wraps an A2A Client to connect the Agent Framework with external A2A-compliant agents
    via HTTP/JSON-RPC. Converts framework ChatMessages to A2A Messages on send, and converts
    A2A responses (Messages/Tasks) back to framework types. Inherits BaseAgent capabilities
    while managing the underlying A2A protocol communication.

    Can be initialized with a URL, AgentCard, or existing A2A Client instance.
    """

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
            kwargs: any additional properties, passed to BaseAgent.
        """
        super().__init__(id=id, name=name, description=description, **kwargs)
        self._http_client: httpx.AsyncClient | None = http_client
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
            timeout = httpx.Timeout(
                connect=10.0,  # 10 seconds to establish connection
                read=60.0,  # 60 seconds to read response (A2A operations can take time)
                write=10.0,  # 10 seconds to send request
                pool=5.0,  # 5 seconds to get connection from pool
            )
            headers = prepend_agent_framework_to_user_agent()
            http_client = httpx.AsyncClient(timeout=timeout, headers=headers)
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

    async def __aenter__(self) -> "A2AAgent":
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

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        """Get a response from the agent.

        This method returns the final result of the agent's execution
        as a single AgentRunResponse object. The caller is blocked until
        the final result is available.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        # Collect all updates and use framework to consolidate updates into response
        updates = [update async for update in self.run_stream(messages, thread=thread, **kwargs)]
        return AgentRunResponse.from_agent_run_response_updates(updates)

    async def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        """Run the agent as a stream.

        This method will return the intermediate steps and final results of the
        agent's execution as a stream of AgentRunResponseUpdate objects to the caller.

        Args:
            messages: The message(s) to send to the agent.

        Keyword Args:
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Yields:
            An agent response item.
        """
        messages = self._normalize_messages(messages)
        a2a_message = self._chat_message_to_a2a_message(messages[-1])

        response_stream = self.client.send_message(a2a_message)

        async for item in response_stream:
            if isinstance(item, Message):
                # Process A2A Message
                contents = self._a2a_parts_to_contents(item.parts)
                yield AgentRunResponseUpdate(
                    contents=contents,
                    role=Role.ASSISTANT if item.role == A2ARole.agent else Role.USER,
                    response_id=str(getattr(item, "message_id", uuid.uuid4())),
                    raw_representation=item,
                )
            elif isinstance(item, tuple) and len(item) == 2:  # ClientEvent = (Task, UpdateEvent)
                task, _update_event = item
                if isinstance(task, Task) and task.status.state in TERMINAL_TASK_STATES:
                    # Convert Task artifacts to ChatMessages and yield as separate updates
                    task_messages = self._task_to_chat_messages(task)
                    if task_messages:
                        for message in task_messages:
                            # Use the artifact's ID from raw_representation as message_id for unique identification
                            artifact_id = getattr(message.raw_representation, "artifact_id", None)
                            yield AgentRunResponseUpdate(
                                contents=message.contents,
                                role=message.role,
                                response_id=task.id,
                                message_id=artifact_id,
                                raw_representation=task,
                            )
                    else:
                        # Empty task
                        yield AgentRunResponseUpdate(
                            contents=[],
                            role=Role.ASSISTANT,
                            response_id=task.id,
                            raw_representation=task,
                        )
            else:
                # Unknown response type
                msg = f"Only Message and Task responses are supported from A2A agents. Received: {type(item)}"
                raise NotImplementedError(msg)

    def _chat_message_to_a2a_message(self, message: ChatMessage) -> A2AMessage:
        """Convert a ChatMessage to an A2A Message.

        Transforms Agent Framework ChatMessage objects into A2A protocol Messages by:
        - Converting all message contents to appropriate A2A Part types
        - Mapping text content to TextPart objects
        - Converting file references (URI/data/hosted_file) to FilePart objects
        - Preserving metadata and additional properties from the original message
        - Setting the role to 'user' as framework messages are treated as user input
        """
        parts: list[A2APart] = []
        if not message.contents:
            raise ValueError("ChatMessage.contents is empty; cannot convert to A2AMessage.")

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
                                    bytes=_get_uri_data(content.uri),
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

        return A2AMessage(
            role=A2ARole("user"),
            parts=parts,
            message_id=message.message_id or uuid.uuid4().hex,
            metadata=cast(dict[str, Any], message.additional_properties),
        )

    def _a2a_parts_to_contents(self, parts: Sequence[A2APart]) -> list[Contents]:
        """Convert A2A Parts to Agent Framework Contents.

        Transforms A2A protocol Parts into framework-native Content objects,
        handling text, file (URI/bytes), and data parts with metadata preservation.
        """
        contents: list[Contents] = []
        for part in parts:
            inner_part = part.root
            match inner_part.kind:
                case "text":
                    contents.append(
                        TextContent(
                            text=inner_part.text,
                            additional_properties=inner_part.metadata,
                            raw_representation=inner_part,
                        )
                    )
                case "file":
                    if isinstance(inner_part.file, FileWithUri):
                        contents.append(
                            UriContent(
                                uri=inner_part.file.uri,
                                media_type=inner_part.file.mime_type or "",
                                additional_properties=inner_part.metadata,
                                raw_representation=inner_part,
                            )
                        )
                    elif isinstance(inner_part.file, FileWithBytes):
                        contents.append(
                            DataContent(
                                data=base64.b64decode(inner_part.file.bytes),
                                media_type=inner_part.file.mime_type or "",
                                additional_properties=inner_part.metadata,
                                raw_representation=inner_part,
                            )
                        )
                case "data":
                    contents.append(
                        TextContent(
                            text=json.dumps(inner_part.data),
                            additional_properties=inner_part.metadata,
                            raw_representation=inner_part,
                        )
                    )
                case _:
                    raise ValueError(f"Unknown Part kind: {inner_part.kind}")
        return contents

    def _task_to_chat_messages(self, task: Task) -> list[ChatMessage]:
        """Convert A2A Task artifacts to ChatMessages with ASSISTANT role."""
        messages: list[ChatMessage] = []

        if task.artifacts is not None:
            for artifact in task.artifacts:
                messages.append(self._artifact_to_chat_message(artifact))
        elif task.history is not None and len(task.history) > 0:
            # Include the last history item as the agent response
            history_item = task.history[-1]
            contents = self._a2a_parts_to_contents(history_item.parts)
            messages.append(
                ChatMessage(
                    role=Role.ASSISTANT if history_item.role == A2ARole.agent else Role.USER,
                    contents=contents,
                    raw_representation=history_item,
                )
            )

        return messages

    def _artifact_to_chat_message(self, artifact: Artifact) -> ChatMessage:
        """Convert A2A Artifact to ChatMessage using part contents."""
        contents = self._a2a_parts_to_contents(artifact.parts)
        return ChatMessage(
            role=Role.ASSISTANT,
            contents=contents,
            raw_representation=artifact,
        )
