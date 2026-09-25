# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Union, cast

from agent_framework import (
    AgentContext,
    AgentMiddleware,
    AgentResponse,
    AgentResponseUpdate,
    ChatContext,
    ChatMiddleware,
    ChatResponse,
    ChatResponseUpdate,
    Message,
    MiddlewareTermination,
    ResponseStream,
)
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from ._cache import CacheProvider
from ._client import PurviewClient
from ._exceptions import PurviewPaymentRequiredError
from ._models import Activity
from ._processor import ScopedContentProcessor
from ._settings import PurviewSettings

AzureCredentialTypes = Union[TokenCredential, AsyncTokenCredential]
AzureTokenProvider = Callable[[], Union[str, Awaitable[str]]]

logger = logging.getLogger("agent_framework.purview")


async def _should_block_response(
    processor: ScopedContentProcessor,
    settings: PurviewSettings,
    result: Any,
    session_id: str | None,
    user_id: str | None,
) -> bool:
    """Evaluate the messages of an assembled response, honouring the configured error tolerances.

    Returns ``True`` when policy requires the response to be replaced. Errors are
    re-raised unless the corresponding ``ignore_*`` setting is enabled.
    """
    try:
        messages: Sequence[Message] = result.messages
        if not messages:
            return False
        should_block, _ = await processor.process_messages(
            messages,
            Activity.DOWNLOAD_TEXT,
            session_id=session_id,
            user_id=user_id,
        )
        return should_block
    except PurviewPaymentRequiredError as ex:
        logger.error(f"Purview payment required error in policy post-check: {ex}")
        if not settings.get("ignore_payment_required", False):
            raise
    except Exception as ex:
        logger.error(f"Error in Purview policy post-check: {ex}")
        if not settings.get("ignore_exceptions", False):
            raise
    return False


class PurviewPolicyMiddleware(AgentMiddleware):
    """Agent middleware that enforces Purview policies on prompt and response.

    Accepts a TokenCredential, AsyncTokenCredential, or callable token provider.

    Evaluation covers the caller's input messages on the prompt side and the agent's
    final response on the response side. Streamed runs are buffered in full and
    evaluated before any update is released, so a streamed run receives the same
    evaluation as a non-streaming one; content is therefore not delivered
    incrementally while this middleware is attached.

    This middleware evaluates the run boundary. It does not see content added inside
    the run, such as context-provider output or a model's tool call before the tool
    executes. Use :class:`PurviewChatPolicyMiddleware` where those must be evaluated.

    Usage:

    .. code-block:: python
        from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
        from agent_framework import Agent

        credential = ...  # TokenCredential, AsyncTokenCredential, or callable
        settings = PurviewSettings(app_name="My App")
        agent = Agent(client=client, instructions="...", middleware=[PurviewPolicyMiddleware(credential, settings)])
    """

    def __init__(
        self,
        credential: AzureCredentialTypes | AzureTokenProvider,
        settings: PurviewSettings,
        cache_provider: CacheProvider | None = None,
    ) -> None:
        self._client = PurviewClient(credential, settings)
        self._processor = ScopedContentProcessor(self._client, settings, cache_provider)
        self._settings = settings

    @staticmethod
    def _get_agent_session_id(context: AgentContext) -> str | None:
        """Resolve a session/conversation id from the agent run context.

        Resolution order:
          1. session.service_session_id
          2. First message whose additional_properties contains 'conversation_id'
          3. None: the downstream processor will generate a new UUID
        """
        if context.session:
            service_session_id = context.session.service_session_id
            if isinstance(service_session_id, str) and service_session_id:
                return service_session_id

        for message in context.messages:
            conversation_id = message.additional_properties.get("conversation_id")
            if conversation_id is not None:
                return str(conversation_id)

        return None

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        resolved_user_id: str | None = None
        session_id: str | None = None
        try:
            # Pre (prompt) check
            session_id = self._get_agent_session_id(context)
            should_block_prompt, resolved_user_id = await self._processor.process_messages(
                context.messages, Activity.UPLOAD_TEXT, session_id=session_id
            )
            if should_block_prompt:
                msg = self._settings.get("blocked_prompt_message", None) or "Prompt blocked by policy"

                context.result = AgentResponse(
                    messages=[
                        Message(
                            role="system",
                            contents=[msg],
                        )
                    ]
                )
                raise MiddlewareTermination
        except MiddlewareTermination:
            raise
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy pre-check: {ex}")
            if not self._settings.get("ignore_payment_required", False):
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy pre-check: {ex}")
            if not self._settings.get("ignore_exceptions", False):
                raise

        await call_next()

        # Post (response) check. The user id resolved during the prompt check is reused
        # so the response is evaluated against the same identity as the request.
        session_id_response = self._get_agent_session_id(context)
        if session_id_response is None:
            session_id_response = session_id

        if isinstance(context.result, ResponseStream):
            context.result = self._gate_stream(
                cast("ResponseStream[AgentResponseUpdate, AgentResponse[Any]]", context.result),
                session_id_response,
                resolved_user_id,
            )
        elif context.result is not None:
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                context.result,
                session_id_response,
                resolved_user_id,
            )
            if should_block_response:
                context.result = self._blocked_response()

    def _blocked_response(self) -> "AgentResponse[Any]":
        """Build the replacement response returned when policy blocks the content."""
        msg = self._settings.get("blocked_response_message", None) or "Response blocked by policy"
        return AgentResponse(messages=[Message(role="system", contents=[msg])])

    def _gate_stream(
        self,
        inner: "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]",
        session_id: str | None,
        user_id: str | None,
    ) -> "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]":
        """Buffer a streamed run and evaluate its complete content before anything is released.

        The stream is drained in full, the assembled response is evaluated exactly as a
        non-streaming response is, and only then are updates released. A blocked response
        is replaced. The released updates are always re-derived from the response that was
        evaluated, so what the caller receives cannot diverge from what policy saw even when
        the inner stream's finalizer returns something other than the assembly of its own
        updates.
        """

        async def _consume() -> tuple[Sequence[AgentResponseUpdate], "AgentResponse[Any]"]:
            try:
                final = await inner.get_final_response()
            finally:
                # Cancellation or failure part-way through the drain still has to release
                # the inner stream, which the cleanup hook below would never reach.
                await inner.close()
            return list(inner.updates), final

        async def _gate(
            _updates: list[AgentResponseUpdate], final: "AgentResponse[Any]"
        ) -> tuple["AgentResponse[Any]", bool]:
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                final,
                session_id,
                user_id,
            )
            if should_block_response:
                return self._blocked_response(), True
            # Reported as transformed even when the content is allowed through unchanged, so
            # the released updates are re-derived from the evaluated response rather than
            # replayed from the buffer.
            return final, True

        gated = cast(
            "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]",
            cast(Any, ResponseStream).buffered_and_gated(
                consume=_consume,
                gate=_gate,
                rederive=AgentResponse.to_updates,
            ),
        )
        # Closing the gated stream before it is ever pulled never reaches ``_consume``, so
        # the inner stream is released through a cleanup hook rather than from inside it.
        return gated.with_cleanup_hook(inner.close)


class PurviewChatPolicyMiddleware(ChatMiddleware):
    """Chat middleware variant for Purview policy evaluation.

    This allows users to attach Purview enforcement directly to a chat client

    Behavior:
      * Pre-chat: evaluates outgoing (user + context) messages as an upload activity
        and can terminate execution if blocked.
      * Post-chat: evaluates the received response messages and can replace them with a
        blocked message. Uses the same user_id from the request to ensure consistent user
        identity throughout the evaluation.
      * Streaming: the response is buffered in full and evaluated before any update is
        released, so a streamed response receives the same evaluation as a non-streaming
        one. Content is therefore not delivered incrementally while this middleware is
        attached.

    Usage:

    .. code-block:: python
        from agent_framework.microsoft import PurviewChatPolicyMiddleware, PurviewSettings
        from agent_framework import ChatClient

        credential = ...  # TokenCredential, AsyncTokenCredential, or callable
        settings = PurviewSettings(app_name="My App")
        client = ChatClient(..., middleware=[PurviewChatPolicyMiddleware(credential, settings)])
    """

    def __init__(
        self,
        credential: AzureCredentialTypes | AzureTokenProvider,
        settings: PurviewSettings,
        cache_provider: CacheProvider | None = None,
    ) -> None:
        self._client = PurviewClient(credential, settings)
        self._processor = ScopedContentProcessor(self._client, settings, cache_provider)
        self._settings = settings

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        resolved_user_id: str | None = None
        session_id: str | None = None
        try:
            session_id = context.options.get("conversation_id") if context.options else None
            should_block_prompt, resolved_user_id = await self._processor.process_messages(
                context.messages, Activity.UPLOAD_TEXT, session_id=session_id
            )
            if should_block_prompt:
                blocked_message = Message(
                    role="system",
                    contents=[self._settings.get("blocked_prompt_message", None) or "Prompt blocked by policy"],
                )
                context.result = ChatResponse(messages=[blocked_message])
                raise MiddlewareTermination
        except MiddlewareTermination:
            raise
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy pre-check: {ex}")
            if not self._settings.get("ignore_payment_required", False):
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy pre-check: {ex}")
            if not self._settings.get("ignore_exceptions", False):
                raise

        await call_next()

        # Post (response) evaluation. The user id resolved during the prompt check is
        # reused so the response is evaluated against the same identity as the request.
        session_id_response = context.options.get("conversation_id") if context.options else None
        if session_id_response is None:
            session_id_response = session_id

        if isinstance(context.result, ResponseStream):
            context.result = self._gate_stream(
                cast("ResponseStream[ChatResponseUpdate, ChatResponse[Any]]", context.result),
                session_id_response,
                resolved_user_id,
            )
        elif context.result is not None:
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                context.result,
                session_id_response,
                resolved_user_id,
            )
            if should_block_response:
                context.result = self._blocked_response()

    def _blocked_response(self) -> "ChatResponse[Any]":
        """Build the replacement response returned when policy blocks the content."""
        blocked_message = Message(
            role="system",
            contents=[self._settings.get("blocked_response_message", None) or "Response blocked by policy"],
        )
        return ChatResponse(messages=[blocked_message])

    def _gate_stream(
        self,
        inner: "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]",
        session_id: str | None,
        user_id: str | None,
    ) -> "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]":
        """Buffer a streamed response and evaluate its complete content before anything is released.

        The stream is drained in full, the assembled response is evaluated exactly as a
        non-streaming response is, and only then are updates released. A blocked response
        is replaced. The released updates are always re-derived from the response that was
        evaluated, so what the caller receives cannot diverge from what policy saw even when
        the inner stream's finalizer returns something other than the assembly of its own
        updates.
        """

        async def _consume() -> tuple[Sequence[ChatResponseUpdate], "ChatResponse[Any]"]:
            try:
                final = await inner.get_final_response()
            finally:
                # Cancellation or failure part-way through the drain still has to release
                # the inner stream, which the cleanup hook below would never reach.
                await inner.close()
            return list(inner.updates), final

        async def _gate(
            _updates: list[ChatResponseUpdate], final: "ChatResponse[Any]"
        ) -> tuple["ChatResponse[Any]", bool]:
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                final,
                session_id,
                user_id,
            )
            if should_block_response:
                return self._blocked_response(), True
            # Reported as transformed even when the content is allowed through unchanged, so
            # the released updates are re-derived from the evaluated response rather than
            # replayed from the buffer.
            return final, True

        gated = cast(
            "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]",
            cast(Any, ResponseStream).buffered_and_gated(
                consume=_consume,
                gate=_gate,
                rederive=ChatResponse.to_updates,
            ),
        )
        # Closing the gated stream before it is ever pulled never reaches ``_consume``, so
        # the inner stream is released through a cleanup hook rather than from inside it.
        return gated.with_cleanup_hook(inner.close)
