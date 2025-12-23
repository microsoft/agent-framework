# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Awaitable, Callable

from agent_framework import AgentMiddleware, AgentRunContext, ChatContext, ChatMiddleware
from agent_framework._logging import get_logger
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from ._cache import CacheProvider
from ._client import PurviewClient
from ._exceptions import PurviewPaymentRequiredError
from ._models import Activity
from ._processor import ScopedContentProcessor
from ._settings import PurviewSettings

logger = get_logger("agent_framework.purview")


class PurviewPolicyMiddleware(AgentMiddleware):
    """Agent middleware that enforces Purview policies on prompt and response.

    Accepts either a synchronous TokenCredential or an AsyncTokenCredential.

    Usage:

    .. code-block:: python
        from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
        from agent_framework import ChatAgent

        credential = ...  # TokenCredential or AsyncTokenCredential
        settings = PurviewSettings(app_name="My App")
        agent = ChatAgent(
            chat_client=client, instructions="...", middleware=[PurviewPolicyMiddleware(credential, settings)]
        )
    """

    def __init__(
        self,
        credential: TokenCredential | AsyncTokenCredential,
        settings: PurviewSettings,
        cache_provider: CacheProvider | None = None,
    ) -> None:
        self._client = PurviewClient(credential, settings)
        self._processor = ScopedContentProcessor(self._client, settings, cache_provider)
        self._settings = settings

    async def process(
        self,
        context: AgentRunContext,
        next: Callable[[AgentRunContext], Awaitable[None]],
    ) -> None:  # type: ignore[override]
        resolved_user_id: str | None = None
        try:
            # Pre (prompt) check
            should_block_prompt, resolved_user_id = await self._processor.process_messages(
                context.messages, Activity.UPLOAD_TEXT
            )
            if should_block_prompt:
                from agent_framework import AgentRunResponse, ChatMessage, Role

                context.result = AgentRunResponse(
                    messages=[ChatMessage(role=Role.SYSTEM, text=self._settings.blocked_prompt_message)]
                )
                context.terminate = True
                return
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy pre-check: {ex}")
            if not self._settings.ignore_payment_required:
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy pre-check: {ex}")
            if not self._settings.ignore_exceptions:
                raise

        await next(context)

        try:
            # Post (response) check only if we have a normal AgentRunResponse
            # Use the same user_id from the request for the response evaluation
            if context.result and not context.is_streaming:
                should_block_response, _ = await self._processor.process_messages(
                    context.result.messages,  # type: ignore[union-attr]
                    Activity.UPLOAD_TEXT,
                    user_id=resolved_user_id,
                )
                if should_block_response:
                    from agent_framework import AgentRunResponse, ChatMessage, Role

                    context.result = AgentRunResponse(
                        messages=[ChatMessage(role=Role.SYSTEM, text=self._settings.blocked_response_message)]
                    )
            else:
                # Streaming responses are not supported for post-checks
                logger.debug("Streaming responses are not supported for Purview policy post-checks")
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy post-check: {ex}")
            if not self._settings.ignore_payment_required:
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy post-check: {ex}")
            if not self._settings.ignore_exceptions:
                raise


class PurviewChatPolicyMiddleware(ChatMiddleware):
    """Chat middleware variant for Purview policy evaluation.

    This allows users to attach Purview enforcement directly to a chat client

    Behavior:
      * Pre-chat: evaluates outgoing (user + context) messages as an upload activity
        and can terminate execution if blocked.
      * Post-chat: evaluates the received response messages (streaming is not presently supported)
        and can replace them with a blocked message. Uses the same user_id from the request
        to ensure consistent user identity throughout the evaluation.

    Usage:

    .. code-block:: python
        from agent_framework.microsoft import PurviewChatPolicyMiddleware, PurviewSettings
        from agent_framework import ChatClient

        credential = ...  # TokenCredential or AsyncTokenCredential
        settings = PurviewSettings(app_name="My App")
        client = ChatClient(..., middleware=[PurviewChatPolicyMiddleware(credential, settings)])
    """

    def __init__(
        self,
        credential: TokenCredential | AsyncTokenCredential,
        settings: PurviewSettings,
        cache_provider: CacheProvider | None = None,
    ) -> None:
        self._client = PurviewClient(credential, settings)
        self._processor = ScopedContentProcessor(self._client, settings, cache_provider)
        self._settings = settings

    async def process(
        self,
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],
    ) -> None:  # type: ignore[override]
        resolved_user_id: str | None = None
        try:
            should_block_prompt, resolved_user_id = await self._processor.process_messages(
                context.messages, Activity.UPLOAD_TEXT
            )
            if should_block_prompt:
                from agent_framework import ChatMessage, ChatResponse

                blocked_message = ChatMessage(role="system", text=self._settings.blocked_prompt_message)
                context.result = ChatResponse(messages=[blocked_message])
                context.terminate = True
                return
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy pre-check: {ex}")
            if not self._settings.ignore_payment_required:
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy pre-check: {ex}")
            if not self._settings.ignore_exceptions:
                raise

        await next(context)

        try:
            # Post (response) evaluation only if non-streaming and we have messages result shape
            # Use the same user_id from the request for the response evaluation
            if context.result and not context.is_streaming:
                result_obj = context.result
                messages = getattr(result_obj, "messages", None)
                if messages:
                    should_block_response, _ = await self._processor.process_messages(
                        messages, Activity.UPLOAD_TEXT, user_id=resolved_user_id
                    )
                    if should_block_response:
                        from agent_framework import ChatMessage, ChatResponse

                        blocked_message = ChatMessage(role="system", text=self._settings.blocked_response_message)
                        context.result = ChatResponse(messages=[blocked_message])
            else:
                logger.debug("Streaming responses are not supported for Purview policy post-checks")
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy post-check: {ex}")
            if not self._settings.ignore_payment_required:
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy post-check: {ex}")
            if not self._settings.ignore_exceptions:
                raise
