# Copyright (c) Microsoft. All rights reserved.

import base64
import json
import re
import uuid
from collections.abc import AsyncIterable, Sequence
from typing import Any

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    DataPart,
    FilePart,
    FileWithBytes,
    FileWithUri,
    MessageSendParams,
    SendMessageRequest,
    SendMessageSuccessResponse,
    SendStreamingMessageRequest,
    SendStreamingMessageSuccessResponse,
    TextPart,
)
from a2a.types import Message as A2AMessage
from a2a.types import Part as A2APart
from a2a.types import Role as A2ARole
from a2a.types import Task as A2ATask

from ._agents import AgentBase
from ._threads import AgentThread
from ._types import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AIContents,
    ChatMessage,
    ChatRole,
    DataContent,
    ErrorContent,
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


class A2AAgent(AgentBase):
    """A2A Agent."""

    # TODO(peterychang): A2AClient was deprecated recently, but none of the tutorials have been updated yet.
    # Change this to BaseClient at some point
    _client: A2AClient

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        description: str | None = None,
        agent_card: AgentCard | None = None,
        url: str | None = None,
        client: A2AClient | None = None,
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

        self._client = client or A2AClient(
            httpx_client=httpx.AsyncClient(),
            agent_card=agent_card,
            url=url,
        )

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

        Note: For streaming responses, use the run_streaming method, which returns
        intermediate steps and the final result as a stream of AgentRunResponseUpdate
        objects. Streaming only the final result is not feasible because the timing of
        the final result's availability is unknown, and blocking the caller until then
        is undesirable in streaming scenarios.

        Args:
            messages: The message(s) to send to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Returns:
            An agent response item.
        """
        messages = self._normalize_messages(messages)
        a2a_message = self._chat_message_to_a2a_message(messages[-1])
        message_request = SendMessageRequest(id=a2a_message.message_id, params=MessageSendParams(message=a2a_message))
        a2a_response = await self._client.send_message(message_request)
        inner_response = a2a_response.root
        if isinstance(inner_response, SendMessageSuccessResponse):
            result = inner_response.result
            match result:
                case A2AMessage():
                    chat_messages = [
                        ChatMessage(
                            role="user" if result.role == "user" else "assistant",
                            contents=self._a2a_parts_to_contents(result.parts),
                            raw_representation=result,
                        )
                    ]
                case A2ATask():
                    match result.status.state:
                        case "completed":
                            chat_messages = [
                                ChatMessage(
                                    role="assistant",
                                    contents=self._a2a_parts_to_contents(artifact.parts),
                                    raw_representation=result,
                                )
                                for artifact in result.artifacts or []
                            ]
                        case "canceled" | "failed" | "rejected":
                            contents: list[AIContents] = []
                            if result.status.message:
                                contents = self._a2a_parts_to_contents(result.status.message.parts)
                            else:
                                contents = [
                                    ErrorContent(
                                        message=f"A2A Task failed with state {result.status.state}",
                                        raw_representation=result,
                                    )
                                ]
                            chat_messages = [
                                ChatMessage(role="assistant", contents=contents, raw_representation=result)
                            ]
                        case "submitted" | "working":
                            # TODO(peterychang): Long running task. How to handle this?
                            raise ValueError("Long running tasks not supported")
                        case _:
                            # input_required, auth_required, unknown
                            raise ValueError(f"Unhandled Task status {result.status.state}")
                case _:
                    raise ValueError(f"Unknown response type {result}")
            return AgentRunResponse(
                messages=chat_messages,
                response_id=str(inner_response.id) if isinstance(inner_response.id, int) else inner_response.id,
                raw_representation=inner_response,
            )
        # error returned
        error_content = ErrorContent(
            message=inner_response.error.message,
            error_code=str(inner_response.error.code) if inner_response.error.code else None,
            raw_representation=inner_response,
        )
        chat_message = ChatMessage(
            role="assistant",
            contents=[error_content],
        )
        return AgentRunResponse(
            messages=chat_message,
            response_id=str(inner_response.id) if isinstance(inner_response.id, int) else inner_response.id,
            raw_representation=inner_response,
        )

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

        Note: An AgentRunResponseUpdate object contains a chunk of a message.

        Args:
            messages: The message(s) to send to the agent.
            thread: The conversation thread associated with the message(s).
            kwargs: Additional keyword arguments.

        Yields:
            An agent response item.
        """
        messages = self._normalize_messages(messages)
        a2a_message = self._chat_message_to_a2a_message(messages[-1])
        message_request = SendStreamingMessageRequest(
            id=a2a_message.message_id, params=MessageSendParams(message=a2a_message)
        )
        a2a_responses = self._client.send_message_streaming(message_request)
        async for response in a2a_responses:
            contents: list[AIContents] = []
            inner_response = response.root
            if isinstance(inner_response, SendStreamingMessageSuccessResponse):
                result = inner_response.result
                match result:
                    case A2AMessage():
                        contents = self._a2a_parts_to_contents(result.parts)
                    case A2ATask():
                        match result.status.state:
                            case "completed":
                                for artifact in result.artifacts or []:
                                    contents.extend(self._a2a_parts_to_contents(artifact.parts))
                            case "canceled" | "failed" | "rejected":
                                contents: list[AIContents] = []
                                if result.status.message:
                                    contents = self._a2a_parts_to_contents(result.status.message.parts)
                                else:
                                    contents = [
                                        ErrorContent(
                                            message=f"A2A Task failed with state {result.status.state}",
                                            raw_representation=result,
                                        )
                                    ]
                            case "submitted" | "working":
                                # TODO(peterychang): Long running task. How to handle this?
                                raise ValueError("Long running tasks not supported")
                            case _:
                                # input_required, auth_required, unknown
                                raise ValueError(f"Unhandled Task status {result.status.state}")
                    case _:
                        raise ValueError(f"Unhandled response type {result}")
            else:
                # error returned
                contents = [
                    ErrorContent(
                        message=inner_response.error.message,
                        error_code=str(inner_response.error.code) if inner_response.error.code else None,
                        raw_representation=inner_response,
                    )
                ]
            yield AgentRunResponseUpdate(
                contents=contents,
                response_id=str(inner_response.id) if isinstance(inner_response.id, int) else inner_response.id,
                raw_representation=inner_response,
            )

    def _normalize_messages(
        self,
        messages: str | ChatMessage | Sequence[str] | Sequence[ChatMessage] | None = None,
    ) -> list[ChatMessage]:
        if messages is None:
            return []

        if isinstance(messages, str):
            return [ChatMessage(role=ChatRole.USER, text=messages)]

        if isinstance(messages, ChatMessage):
            return [messages]

        return [ChatMessage(role=ChatRole.USER, text=msg) if isinstance(msg, str) else msg for msg in messages]

    def _chat_message_to_a2a_message(self, message: ChatMessage) -> A2AMessage:
        """Convert a ChatMessage to a Message."""
        parts: list[A2APart] = []
        # TODO(peterychang): Handle other content types
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
            case "function_call" | "function_result":
                # TODO(peterychang): Need to handle this?
                pass
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
                # TODO(peterychang): What do we do here?
                raise ValueError(f"Unknown content type: {type(content)}")

        return A2AMessage(
            role=A2ARole("user"),
            parts=parts,
            message_id=message.message_id or uuid.uuid4().hex,
            metadata=message.additional_properties,
        )

    def _a2a_parts_to_contents(self, parts: Sequence[A2APart]) -> list[AIContents]:
        contents: list[AIContents] = []
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
