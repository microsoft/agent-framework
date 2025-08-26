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
from pydantic import AnyUrl

from ._agents import AgentBase
from ._threads import AgentThread
from ._types import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AIContents,
    ChatMessage,
    ChatRole,
    DataContent,
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
        description: str | None = None,
        agent_card: AgentCard | None = None,
        url: AnyUrl | None = None,
        executor: A2AClient | None = None,
    ) -> None:
        super().__init__(name=name, description=description)

        self._client = executor or A2AClient(
            httpx_client=httpx.AsyncClient(),
            agent_card=agent_card,
            url=str(url) if url else None,
        )

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        messages = self._normalize_messages(messages)
        a2a_message = self._chat_message_to_a2a_message(messages[-1])
        message_request = SendMessageRequest(id=a2a_message.message_id, params=MessageSendParams(message=a2a_message))
        a2a_response = await self._client.send_message(message_request)
        inner_response = a2a_response.root
        if isinstance(inner_response, SendMessageSuccessResponse):
            if isinstance(inner_response.result, A2AMessage):
                chat_messages = [self._a2a_message_to_chat_message(inner_response.result)]
            else:
                # TODO(peterychang): Handle this later
                raise ValueError("Unhandled type")
            return AgentRunResponse(
                messages=chat_messages,
                response_id=str(inner_response.id) if isinstance(inner_response.id, int) else inner_response.id,
                raw_representation=inner_response,
            )
        raise ValueError(f"Unexpected response type: {type(a2a_response)}")

    async def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        messages = self._normalize_messages(messages)
        a2a_message = self._chat_message_to_a2a_message(messages[-1])
        message_request = SendStreamingMessageRequest(
            id=a2a_message.message_id, params=MessageSendParams(message=a2a_message)
        )
        a2a_responses = self._client.send_message_streaming(message_request)
        async for response in a2a_responses:
            inner_response = response.root
            if isinstance(inner_response, SendStreamingMessageSuccessResponse):
                if isinstance(inner_response.result, A2AMessage):
                    yield AgentRunResponseUpdate(
                        contents=self._a2a_message_to_chat_message(inner_response.result).contents,
                        response_id=str(inner_response.id) if isinstance(inner_response.id, int) else inner_response.id,
                        raw_representation=inner_response,
                    )
            else:
                # TODO(peterychang): Handle this later
                raise ValueError("Unhandled type: ", type(response))

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
        content = message.contents[0]
        if content.type == "text":
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
        elif content.type == "function_call" or content.type == "function_result":
            # TODO(peterychang): Need to handle this?
            pass
        elif content.type == "error":
            parts.append(
                A2APart(
                    root=TextPart(
                        text=content.message or "An error occurred.",
                        metadata=content.additional_properties,
                    )
                )
            )
        elif content.type == "uri":
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
        elif content.type == "data":
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
        else:
            # TODO(peterychang): What do we do here?
            raise ValueError(f"Unknown content type: {type(content)}")

        return A2AMessage(
            role=A2ARole("user"),
            parts=parts,
            message_id=message.message_id or uuid.uuid4().hex,
            metadata=message.additional_properties,
        )

    def _a2a_message_to_chat_message(self, message: A2AMessage) -> ChatMessage:
        """Convert a Message to a ChatMessage."""
        contents: list[AIContents] = []
        if message.kind == "message":
            for part in message.parts:
                part = part.root
                if part.kind == "text":
                    contents.append(
                        TextContent(
                            text=part.text,
                            additional_properties=part.metadata,
                            raw_representation=part,
                        )
                    )
                elif part.kind == "file":
                    if isinstance(part.file, FileWithUri):
                        contents.append(
                            UriContent(
                                uri=part.file.uri,
                                media_type=part.file.mime_type or "",
                                additional_properties=part.metadata,
                                raw_representation=part,
                            )
                        )
                    elif isinstance(part.file, FileWithBytes):
                        contents.append(
                            DataContent(
                                data=base64.b64decode(part.file.bytes),
                                media_type=part.file.mime_type or "",
                                additional_properties=part.metadata,
                                raw_representation=part,
                            )
                        )
                elif part.kind == "data":
                    contents.append(
                        TextContent(
                            text=json.dumps(part.data),
                            additional_properties=part.metadata,
                            raw_representation=part,
                        )
                    )
        return ChatMessage(
            role="user" if message.role == "user" else "assistant",
            contents=contents,
        )
