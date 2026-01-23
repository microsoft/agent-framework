# Copyright (c) Microsoft. All rights reserved.

"""Thread types for AG-UI integration."""

from typing import Any

from agent_framework import AgentThread, ChatMessageStoreProtocol, ContextProvider


class AGUIThread(AgentThread):
    """Agent thread with AG-UI metadata storage."""

    def __init__(
        self,
        *,
        service_thread_id: str | None = None,
        message_store: ChatMessageStoreProtocol | None = None,
        context_provider: ContextProvider | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            service_thread_id=service_thread_id,
            message_store=message_store,
            context_provider=context_provider,
        )
        self.metadata: dict[str, Any] = dict(metadata or {})
