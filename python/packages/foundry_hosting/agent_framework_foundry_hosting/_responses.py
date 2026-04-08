# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable

from agent_framework import Agent, HistoryProvider, Message
from azure.ai.agentserver.core import AgentHost
from azure.ai.agentserver.responses import ResponseContext, ResponseEventStream
from azure.ai.agentserver.responses.hosting import ResponseHandler
from azure.ai.agentserver.responses.models import CreateResponse, get_input_text
from typing_extensions import Any, Sequence

from ._shared import extract_chat_options, to_messages


class ResponsesHostContextProvider(HistoryProvider):
    def __init__(self, context: ResponseContext):
        super().__init__("responses-host", load_messages=True)
        self.context = context

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        history = await self.context.get_history_async()
        return to_messages(history)

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        pass


class ResponsesHost(AgentHost):
    def __init__(self, agent: Agent, **kwargs: Any) -> None:
        application_insights_connection_string = kwargs.pop("application_insights_connection_string", None)
        graceful_shutdown_timeout = kwargs.pop("graceful_shutdown_timeout", None)
        log_level = kwargs.pop("log_level", None)
        super().__init__(
            application_insights_connection_string=application_insights_connection_string,
            graceful_shutdown_timeout=graceful_shutdown_timeout,
            log_level=log_level,
        )

        self.agent = agent
        self.response_handler = ResponseHandler(self)
        self.response_handler.create_handler(self._handle_create)  # type: ignore

    async def _handle_create(
        self,
        request: CreateResponse,
        context: ResponseContext,
        cancellation_signal: asyncio.Event,
    ) -> AsyncIterable[dict[str, Any]]:
        # Replace or add a history provider that has `load_messages=True`
        history_provider_idx: list[int] = []
        for i, provider in enumerate(self.agent.context_providers):
            if isinstance(provider, HistoryProvider) and provider.load_messages:
                history_provider_idx.append(i)

        if not history_provider_idx:
            self.agent.context_providers.append(ResponsesHostContextProvider(context))
        elif len(history_provider_idx) > 1:
            # There shouldn't be more than one history provider with `load_messages=True`
            raise RuntimeError("There shouldn't be more than one history provider with `load_messages=True`")
        else:
            self.agent.context_providers[history_provider_idx[0]] = ResponsesHostContextProvider(context)

        stream = ResponseEventStream(
            response_id=context.response_id,
            model=getattr(request, "model", None),
        )

        yield stream.emit_created()
        yield stream.emit_in_progress()

        input_items = get_input_text(request)

        # Start the response
        message_item = stream.add_output_item_message()
        yield message_item.emit_added()
        text_content = message_item.add_text_content()
        yield text_content.emit_added()

        # Invoke the MAF agent
        chat_options = extract_chat_options(request)
        full_text = ""
        async for update in self.agent.run(
            input_items,
            options=chat_options,
            stream=True,
        ):
            full_text += update.text
            yield text_content.emit_delta(update.text)

        # Complete the message
        yield text_content.emit_done(full_text)
        yield message_item.emit_content_done(text_content)
        yield message_item.emit_done()

        yield stream.emit_completed()
