# Copyright (c) Microsoft. All rights reserved.

import base64
import json
import re
import uuid

from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import DataPart, FilePart, FileWithBytes, FileWithUri, TextPart
from a2a.types import (
    Message as A2AMessage,
)
from a2a.types import (
    Part as A2APart,
)
from a2a.types import Role as A2ARole

from ._agents import AIAgent
from ._types import (
    AgentRunResponse,
    AIContents,
    ChatMessage,
    DataContent,
    TextContent,
    UriContent,
)

__all__ = ["A2AAgentExecutor"]

URI_PATTERN = re.compile(r"^data:(?P<media_type>[^;]+);base64,(?P<base64_data>[A-Za-z0-9+/=]+)$")


def _get_uri_data(uri: str) -> str:
    match = URI_PATTERN.match(uri)
    if not match:
        raise ValueError(f"Invalid data URI format: {uri}")

    return match.group("base64_data")


class A2AAgentExecutor(AgentExecutor):
    """A2A Agent Executor."""

    _agent: AIAgent

    def __init__(self, agent: AIAgent) -> None:
        self._agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # TODO(peterychang): Add AgentThread logic
        if context.message is not None:
            response = await self._agent.run(self._message_to_chat_message(context.message))
            await event_queue.enqueue_event(self._chat_message_to_a2a_message(context.message, response))
        # TODO(peterychang): Handle case where context.message is None

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass

    def _message_to_chat_message(self, message: A2AMessage) -> ChatMessage:
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
                    if isinstance(part, FileWithUri):
                        contents.append(
                            UriContent(
                                uri=part.uri,
                                media_type=part.mime_type or "",
                                additional_properties=part.metadata,
                                raw_representation=part,
                            )
                        )
                    elif isinstance(part, FileWithBytes):
                        contents.append(
                            DataContent(
                                data=base64.b64decode(part.bytes),
                                media_type=part.mime_type or "",
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

    def _chat_message_to_a2a_message(self, input: A2AMessage, response: AgentRunResponse) -> A2AMessage:
        """Convert a ChatMessage to a Message."""
        parts: list[A2APart] = []
        # TODO(peterychang): Handle other content types
        for message in response.messages:
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
            message_id=response.response_id or uuid.uuid4().hex,
            task_id=input.task_id,
            context_id=input.context_id,
            metadata=response.additional_properties,
        )
