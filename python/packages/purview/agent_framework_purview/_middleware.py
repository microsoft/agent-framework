# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

from collections.abc import Awaitable, Callable

from agent_framework import AgentMiddleware, AgentRunContext, ChatMiddleware, ChatContext
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from ._client import PurviewClient
from ._models import Activity
from ._processor import ScopedContentProcessor
from ._settings import PurviewSettings


class PurviewPolicyMiddleware(AgentMiddleware):
    """Agent middleware that enforces Purview policies on prompt and response.

    Accepts either a synchronous TokenCredential or an AsyncTokenCredential.

    Usage:

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


class PurviewChatPolicyMiddleware(ChatMiddleware):
    """Chat middleware variant for Purview policy evaluation.

    This allows users to attach Purview enforcement directly to a chat client
    (e.g., when using a simple chat agent or invoking chat APIs without full
    agent orchestration). It mirrors the logic of ``PurviewPolicyMiddleware``
    but operates at the chat middleware layer.

    Behavior:
      * Pre-chat: evaluates outgoing (user + context) messages as an upload activity
        and can terminate execution if blocked.
      * Post-chat: evaluates the received response messages (non-streaming only currently)
        and can replace them with a blocked message.

    Notes:
      * Streaming responses are passed through without a second-phase evaluation
        for now (could be enhanced to accumulate and evaluate partials).
      * Uses the same ``ScopedContentProcessor`` for consistency.
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
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],
    ) -> None:  # type: ignore[override]
        # Pre (prompt) evaluation
        should_block_prompt = await self._processor.process_messages(context.messages, Activity.UPLOAD_TEXT)
        if should_block_prompt:
            from agent_framework import ChatMessage

            context.result = [
                ChatMessage(role="system", text="Prompt blocked by policy")  # type: ignore[list-item]
            ]
            context.terminate = True
            return

        await next(context)

        # Post (response) evaluation only if non-streaming and we have messages result shape
        if context.result and not context.is_streaming:
            # We attempt to treat context.result as a ChatResponse-like object
            result_obj = context.result
            messages = getattr(result_obj, "messages", None)
            if messages:
                should_block_response = await self._processor.process_messages(messages, Activity.UPLOAD_TEXT)
                if should_block_response:
                    from agent_framework import ChatMessage

                    # Replace messages attribute if possible; otherwise overwrite result
                    try:
                        result_obj.messages = [  # type: ignore[attr-defined]
                            ChatMessage(role="system", text="Response blocked by policy")
                        ]
                    except Exception:
                        context.result = [
                            ChatMessage(role="system", text="Response blocked by policy")  # type: ignore[list-item]
                        ]
