# Copyright (c) Microsoft. All rights reserved.
"""Shared pytest fixtures for Purview tests."""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any

import pytest
from agent_framework import (
    Agent,
    AgentSession,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    HistoryProvider,
    Message,
    ResponseStream,
)

from agent_framework_purview._models import (
    Activity,
    ActivityMetadata,
    ContentToProcess,
    DeviceMetadata,
    IntegratedAppMetadata,
    OperatingSystemSpecifications,
    PolicyLocation,
    ProcessContentRequest,
    ProcessConversationMetadata,
    ProtectedAppMetadata,
    PurviewTextContent,
)


class StubChatClient(ChatMiddlewareLayer[Any], BaseChatClient[Any]):
    """Chat client that answers with one fixed assistant message, streamed or not."""

    def __init__(self, text: str = "model reply", **kwargs: Any) -> None:
        super().__init__(middleware=[], **kwargs)
        self.text = text

    def _inner_get_response(  # type: ignore[override]
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> "Awaitable[ChatResponse[Any]] | ResponseStream[ChatResponseUpdate, ChatResponse[Any]]":
        if stream:

            async def _updates() -> AsyncIterator[ChatResponseUpdate]:
                yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(text=self.text)])

            return ResponseStream(_updates(), finalizer=ChatResponse.from_updates)

        async def _response() -> "ChatResponse[Any]":
            return ChatResponse(messages=[Message(role="assistant", contents=[self.text])])

        return _response()


@pytest.fixture
def stub_chat_client() -> type[StubChatClient]:
    """Factory for a chat client that answers with a fixed assistant message."""
    return StubChatClient


@pytest.fixture
def stored_texts() -> Callable[[AgentSession, HistoryProvider], list[str]]:
    """Read back the message texts a history provider made durable for a session."""

    def _read(session: AgentSession, provider: HistoryProvider) -> list[str]:
        stored = session.state.get(provider.source_id, {}).get("messages", [])
        texts: list[str] = []
        for message in stored:
            text = message.get("text") if isinstance(message, dict) else getattr(message, "text", None)
            texts.append(text if text is not None else str(message))
        return texts

    return _read


@pytest.fixture
def run_agent() -> Callable[..., Awaitable[str]]:
    """Run an agent through either path and return the text the caller received."""

    async def _run(agent: Agent, prompt: str, session: AgentSession, *, stream: bool) -> str:
        if stream:
            text = ""
            async for update in agent.run(prompt, session=session, stream=True):
                text += update.text
            return text
        return (await agent.run(prompt, session=session)).text

    return _run


@pytest.fixture
def content_to_process_factory():
    """Factory fixture to create ContentToProcess objects with test data."""

    def _create_content(text: str = "Test") -> ContentToProcess:
        text_content = PurviewTextContent(data=text)
        metadata = ProcessConversationMetadata(
            identifier="msg-1",
            content=text_content,
            name="Test",
            is_truncated=False,
        )
        activity_meta = ActivityMetadata(activity=Activity.UPLOAD_TEXT)
        device_meta = DeviceMetadata(
            operating_system_specifications=OperatingSystemSpecifications(
                operating_system_platform="Windows", operating_system_version="10"
            )
        )
        integrated_app = IntegratedAppMetadata(name="App", version="1.0")
        location = PolicyLocation(data_type="microsoft.graph.policyLocationApplication", value="app-id")
        protected_app = ProtectedAppMetadata(name="Protected", version="1.0", application_location=location)

        return ContentToProcess(
            content_entry=metadata,
            activity_metadata=activity_meta,
            device_metadata=device_meta,
            integrated_app_metadata=integrated_app,
            protected_app_metadata=protected_app,
        )

    return _create_content


@pytest.fixture
def process_content_request_factory(content_to_process_factory):
    """Factory fixture to create ProcessContentRequest objects with test data."""

    def _create_request(
        text: str = "Test", user_id: str = "user-123", tenant_id: str = "tenant-456"
    ) -> ProcessContentRequest:
        content = content_to_process_factory(text)
        return ProcessContentRequest(
            content_to_process=content,
            user_id=user_id,
            tenant_id=tenant_id,
        )

    return _create_request


async def run_agent_middleware(
    middleware: Any,
    context: Any,
    set_result: Callable[[], Awaitable[None]],
) -> Any:
    """Run one agent middleware through the real pipeline and return the finished result.

    Middleware declares the stream processing it needs on the context; the pipeline is what
    applies that declaration to the stream once the chain unwinds. Calling ``process``
    directly would therefore leave a streamed result unguarded, so tests go through the
    pipeline to exercise the same wiring production uses.
    """
    from agent_framework._middleware import AgentMiddlewarePipeline  # pyright: ignore[reportPrivateUsage]

    items = tuple(middleware) if isinstance(middleware, (list, tuple)) else (middleware,)

    async def final_handler(ctx: Any) -> Any:
        await set_result()
        return ctx.result

    return await AgentMiddlewarePipeline(*items).execute(context, final_handler)


async def run_chat_middleware(
    middleware: Any,
    context: Any,
    set_result: Callable[[], Awaitable[None]],
) -> Any:
    """Run one chat middleware through the real pipeline and return the finished result.

    See :func:`run_agent_middleware` for why the pipeline is used instead of calling
    ``process`` directly.
    """
    from agent_framework._middleware import ChatMiddlewarePipeline  # pyright: ignore[reportPrivateUsage]

    items = tuple(middleware) if isinstance(middleware, (list, tuple)) else (middleware,)

    async def final_handler(ctx: Any) -> Any:
        await set_result()
        return ctx.result

    return await ChatMiddlewarePipeline(*items).execute(context, final_handler)
