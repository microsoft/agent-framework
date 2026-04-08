# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable

from agent_framework import BaseAgent, HistoryProvider, Message, SupportsAgentRun
from azure.ai.agentserver.responses import (
    ResponseContext,
    ResponseEventStream,
    ResponseProviderProtocol,
    ResponsesServerOptions,
)
from azure.ai.agentserver.responses.hosting import ResponsesAgentServerHost
from azure.ai.agentserver.responses.models import CreateResponse, get_input_text
from typing_extensions import Any, Sequence

from ._shared import to_messages


class ResponsesHostContextProvider(HistoryProvider):
    """A history provider that retrieves messages from a ResponseContext."""

    def __init__(self, context: ResponseContext):
        """Initialize a ResponsesHostContextProvider.

        Args:
            context: The ResponseContext to retrieve messages from.
        """
        super().__init__("responses-host", load_messages=True)
        self.context = context

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        history = await self.context.get_history()
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


class ResponsesHostServer(ResponsesAgentServerHost):
    """A responses server host for an agent."""

    def __init__(
        self,
        agent: BaseAgent,
        *,
        prefix: str = "",
        options: ResponsesServerOptions | None = None,
        provider: ResponseProviderProtocol | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a ResponsesHostServer.

        Args:
            agent: The agent to handle responses for.
            prefix: The URL prefix for the server.
            options: Optional server options.
            provider: Optional response provider.
            **kwargs: Additional keyword arguments.

        Note:
            If the agent has a history provider with `load_messages=True`, it will be
            replaced with a `ResponsesHostContextProvider` that will retrieve history
            from the hosting infrastructure.
        """
        super().__init__(prefix=prefix, options=options, provider=provider, **kwargs)

        if not isinstance(agent, SupportsAgentRun):
            raise TypeError("Agent must support the SupportsAgentRun interface")

        self.agent = agent
        self.create_handler(self._handle_create)  # pyright: ignore[reportUnknownMemberType]

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

        input_items = get_input_text(request)

        stream = ResponseEventStream(response_id=context.response_id, model=request.model)

        yield stream.emit_created()
        yield stream.emit_in_progress()

        if request.stream is None or request.stream is False:
            # Run the agent in non-streaming mode
            response = await self.agent.run(input_items, stream=False)
            for item in stream.output_item_message(response.text):
                yield item
            yield stream.emit_completed()

        # Start the streaming response
        message_item = stream.add_output_item_message()
        yield message_item.emit_added()
        text_content = message_item.add_text_content()
        yield text_content.emit_added()

        # Invoke the MAF agent
        full_text = ""
        async for update in self.agent.run(input_items, stream=True):
            full_text += update.text
            yield text_content.emit_delta(update.text)

        # Complete the message
        yield text_content.emit_done(full_text)
        yield message_item.emit_content_done(text_content)
        yield message_item.emit_done()

        yield stream.emit_completed()
