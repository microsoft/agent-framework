# Copyright (c) Microsoft. All rights reserved.

import base64
import json
import re
import uuid
from collections.abc import AsyncIterable, Sequence
from typing import Any

import httpx
from a2a.client import Client, ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    Artifact,
    DataPart,
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

from ._agents import BaseAgent
from ._threads import AgentThread
from ._types import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    Contents,
    DataContent,
    Role,
    TextContent,
    UriContent,
)

__all__ = ["A2AAgent"]

URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$")


def _get_uri_data(uri: str) -> str:
    match = URI_PATTERN.match(uri)
    if not match:
        raise ValueError(f"Invalid data URI format: {uri}")

    return match.group("base64_data")


class A2AAgent(BaseAgent):
    """A2A Agent."""

    _client: Client

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        description: str | None = None,
        agent_card: AgentCard | None = None,
        url: str | None = None,
        client: Client | None = None,
    ) -> None:
        """Initialize the A2AAgent.

        Args:
            name: The name of the agent.
            id: The unique identifier for the agent, will be created automatically if not provided.
            description: A brief description of the agent's purpose.
            agent_card: The agent card for the agent.
            url: The URL for the A2A server.
            client: The A2A client for the agent.
        """
        args: dict[str, Any] = {}
        if name:
            args["name"] = name
        if id:
            args["id"] = id
        if description:
            args["description"] = description
        super().__init__(**args)

        if client is None:
            if agent_card is None:
                if url is None:
                    raise ValueError("Either agent_card or url must be provided")
                # Create minimal agent card from URL
                from a2a.client import minimal_agent_card

                agent_card = minimal_agent_card(url, [TransportProtocol.jsonrpc])

            # Create client using factory
            config = ClientConfig(httpx_client=httpx.AsyncClient(), supported_transports=[TransportProtocol.jsonrpc])
            factory = ClientFactory(config)
            client = factory.create(agent_card)

        self._client = client

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
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        messages = self._normalize_messages(messages)
        a2a_message = self._chat_message_to_a2a_message(messages[-1])

        response_stream = self._client.send_message(a2a_message)

        # Collect the final response (Message OR Task)
        final_response = None
        async for item in response_stream:
            if isinstance(item, Message):
                final_response = item
                break
            if isinstance(item, tuple) and len(item) == 2:  # ClientEvent = (Task, UpdateEvent)
                task, _update_event = item
                if isinstance(task, Task):
                    final_response = task
                    # Wait for terminal states
                    terminal_states = [TaskState.completed, TaskState.failed, TaskState.canceled, TaskState.rejected]
                    if task.status.state in terminal_states:
                        break

        # Handle the two supported response types
        if isinstance(final_response, Message):
            from a2a.types import Role as A2ARole

            chat_message = ChatMessage(
                role=Role.ASSISTANT if final_response.role == A2ARole.agent else Role.USER,
                contents=self._a2a_parts_to_contents(final_response.parts),
                raw_representation=final_response,
            )
            return AgentRunResponse(
                messages=[chat_message],
                response_id=str(getattr(final_response, "message_id", uuid.uuid4())),
                raw_representation=final_response,
            )
        if isinstance(final_response, Task):
            return AgentRunResponse(
                messages=self._task_to_chat_messages(final_response),
                response_id=final_response.id,
                raw_representation=final_response,
            )

        msg = f"Only Message and Task responses are supported from A2A agents. Received: {type(final_response)}"
        raise NotImplementedError(msg)

    async def run_streaming(
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
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Yields:
            An agent response item.
        """
        messages = self._normalize_messages(messages)
        a2a_message = self._chat_message_to_a2a_message(messages[-1])

        response_stream = self._client.send_message(a2a_message)

        async for item in response_stream:
            if isinstance(item, Message):
                # Process A2A Message
                contents = self._a2a_parts_to_contents(item.parts)
                yield AgentRunResponseUpdate(
                    contents=contents,
                    role=Role.ASSISTANT if str(item.role) == "agent" else Role.USER,
                    response_id=str(getattr(item, "id", uuid.uuid4())),
                    raw_representation=item,
                )

    def _normalize_messages(
        self,
        messages: str | ChatMessage | Sequence[str] | Sequence[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        if messages is None:
            return []

        if isinstance(messages, str):
            return [ChatMessage(role=Role.USER, text=messages)]

        if isinstance(messages, ChatMessage):
            return [messages]

        return [ChatMessage(role=Role.USER, text=msg) if isinstance(msg, str) else msg for msg in messages]

    def _chat_message_to_a2a_message(self, message: ChatMessage) -> A2AMessage:
        """Convert a ChatMessage to a Message."""
        parts: list[A2APart] = []
        if not message.contents:
            raise ValueError("ChatMessage.contents is empty; cannot convert to A2AMessage.")
        content = message.contents[0]
        match content.type:
            case "text":
                try:
                    text_json = json.loads(content.text)
                    parts.append(
                        A2APart(
                            root=DataPart(
                                data=text_json,
                                metadata=content.additional_properties,
                            )
                        )
                    )
                except json.JSONDecodeError:
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
            case _:
                raise ValueError(f"Unknown content type: {type(content)}")

        return A2AMessage(
            role=A2ARole("user"),
            parts=parts,
            message_id=message.message_id or uuid.uuid4().hex,
            metadata=message.additional_properties,
        )

    def _a2a_parts_to_contents(self, parts: Sequence[A2APart]) -> list[Contents]:
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
        """Convert A2A Task to ChatMessages - equivalent to .NET's AgentTask.ToChatMessages()."""
        messages: list[ChatMessage] = []

        if task.artifacts is not None:
            for artifact in task.artifacts:
                messages.append(self._artifact_to_chat_message(artifact))

        return messages

    def _artifact_to_chat_message(self, artifact: Artifact) -> ChatMessage:
        """Convert A2A Artifact to ChatMessage - equivalent to .NET's artifact.ToChatMessage()."""
        contents = self._a2a_parts_to_contents(artifact.parts)
        return ChatMessage(
            role=Role.ASSISTANT,
            contents=contents,
            raw_representation=artifact,
        )
