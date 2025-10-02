# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

from collections.abc import Awaitable, Callable

from agent_framework import AgentMiddleware, AgentRunContext
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from ._client import PurviewClient
from ._models import Activity
from ._processor import ScopedContentProcessor
from ._settings import PurviewSettings


class PurviewPolicyMiddleware(AgentMiddleware):
    """Agent middleware that enforces Purview policies on prompt and response.

    Accepts either a synchronous TokenCredential or an AsyncTokenCredential.

    Usage (recommended direct injection - simpler than the previous decorator):

        from agent_framework_purview import PurviewPolicyMiddleware, PurviewSettings
        from agent_framework import ChatAgent

        credential = ...  # TokenCredential or AsyncTokenCredential
        settings = PurviewSettings(app_name="My App")
        agent = ChatAgent(chat_client=client, instructions="...", middleware=[
            PurviewPolicyMiddleware(credential, settings)
        ])
    """

    def __init__(
        self,
        credential: TokenCredential | AsyncTokenCredential,
        settings: PurviewSettings,
    ) -> None:
        self._client = PurviewClient(credential, settings)
        self._processor = ScopedContentProcessor(self._client, settings)

    async def process(
        self,
        context: AgentRunContext,
        next: Callable[[AgentRunContext], Awaitable[None]],
    ) -> None:  # type: ignore[override]
        # Pre (prompt) check
        should_block_prompt = await self._processor.process_messages(context.messages, Activity.UPLOAD_TEXT)
        if should_block_prompt:
            from agent_framework import AgentRunResponse, ChatMessage, Role

            context.result = AgentRunResponse(messages=[ChatMessage(role=Role.SYSTEM, text="Prompt blocked by policy")])
            context.terminate = True
            return

        await next(context)

        # Post (response) check only if we have a normal AgentRunResponse
        if context.result and hasattr(context.result, "messages"):
            should_block_response = await self._processor.process_messages(
                context.result.messages,  # type: ignore[attr-defined]
                Activity.UPLOAD_TEXT,
            )
            if should_block_response:
                from agent_framework import AgentRunResponse, ChatMessage, Role

                context.result = AgentRunResponse(
                    messages=[ChatMessage(role=Role.SYSTEM, text="Response blocked by policy")]
                )
