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
            context.result = self._evaluate_stream(
                context,
                cast("ResponseStream[AgentResponseUpdate, AgentResponse[Any]]", context.result),
                session_id_response,
                resolved_user_id,
            )
            return

        if context.result is not None:
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                context.result,
                session_id_response,
                resolved_user_id,
            )
            if should_block_response:
                context.result = self._blocked_response(context.result)

    def _blocked_response(self, evaluated: "AgentResponse[Any] | None" = None) -> "AgentResponse[Any]":
        """Build the replacement response returned when policy blocks the content.

        When a response was actually produced, its control fields are carried over and only
        the messages are replaced, so the caller can still identify the operation and resume
        it. The structured value and the raw provider payload are deliberately not carried,
        because both hold the content that was blocked.
        """
        msg = self._settings.get("blocked_response_message", None) or "Response blocked by policy"
        blocked = Message(role="system", contents=[msg])
        if evaluated is None:
            return AgentResponse(messages=[blocked])
        return AgentResponse(
            messages=[blocked],
            response_id=evaluated.response_id,
            agent_id=evaluated.agent_id,
            created_at=evaluated.created_at,
            finish_reason=cast("Any", evaluated.finish_reason),
            usage_details=evaluated.usage_details,
            continuation_token=evaluated.continuation_token,
            additional_properties=dict(evaluated.additional_properties) if evaluated.additional_properties else None,
        )

    def _evaluate_stream(
        self,
        context: AgentContext,
        inner: "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]",
        session_id: str | None,
        user_id: str | None,
    ) -> "ResponseStream[AgentResponseUpdate, AgentResponse[Any]]":
        """Buffer a streamed run and evaluate its complete content before anything is released.

        The processing stages are registered on the context rather than applied by wrapping
        the stream, so several middleware can guard the same run and each one's work is
        applied. The pipeline buffers the stream, applies the registered transforms to the
        assembled response, and releases updates re-derived from the result.

        Response transforms run in middleware order, so a middleware placed after this one
        can replace the response after it has been evaluated. Attach this middleware last
        for its evaluation to cover what the caller actually receives; see the package
        README on middleware order.

        This covers what the caller receives. The run writes its messages to conversation
        history as part of the run itself, below this middleware, so that write has already
        happened by the time the response is evaluated here; see the package README on
        blocked content and conversation history.
        """

        async def _transform(final: "AgentResponse[Any]") -> "AgentResponse[Any]":
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                final,
                session_id,
                user_id,
            )
            if should_block_response:
                return self._blocked_response(final)
            # Returning the evaluated response, rather than None, is what makes the
            # released updates be re-derived from it. A finalizer may produce a response
            # that is not the assembly of its own updates, so releasing the buffered
            # updates instead would release content this evaluation never saw.
            return final

        context.stream_result_transforms.append(_transform)
        context.stream_result_to_updates = AgentResponse.to_updates
        context.stream_buffer_updates = True
        return inner


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
            context.result = self._evaluate_stream(
                context,
                cast("ResponseStream[ChatResponseUpdate, ChatResponse[Any]]", context.result),
                session_id_response,
                resolved_user_id,
            )
            return

        if context.result is not None:
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                context.result,
                session_id_response,
                resolved_user_id,
            )
            if should_block_response:
                context.result = self._blocked_response(context.result)

    def _blocked_response(self, evaluated: "ChatResponse[Any] | None" = None) -> "ChatResponse[Any]":
        """Build the replacement response returned when policy blocks the content.

        When a response was actually produced, its control fields are carried over and only
        the messages are replaced, so the caller can still identify the call and resume it.
        The structured value and the raw provider payload are deliberately not carried,
        because both hold the content that was blocked.
        """
        blocked_message = Message(
            role="system",
            contents=[self._settings.get("blocked_response_message", None) or "Response blocked by policy"],
        )
        if evaluated is None:
            return ChatResponse(messages=[blocked_message])
        return ChatResponse(
            messages=[blocked_message],
            response_id=evaluated.response_id,
            conversation_id=evaluated.conversation_id,
            model=evaluated.model,
            created_at=evaluated.created_at,
            finish_reason=cast("Any", evaluated.finish_reason),
            usage_details=evaluated.usage_details,
            continuation_token=evaluated.continuation_token,
            additional_properties=dict(evaluated.additional_properties) if evaluated.additional_properties else None,
        )

    def _evaluate_stream(
        self,
        context: ChatContext,
        inner: "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]",
        session_id: str | None,
        user_id: str | None,
    ) -> "ResponseStream[ChatResponseUpdate, ChatResponse[Any]]":
        """Buffer a streamed response and evaluate its complete content before anything is released.

        The processing stages are registered on the context rather than applied by wrapping
        the stream, so several middleware can guard the same call and each one's work is
        applied. The pipeline buffers the stream, applies the registered transforms to the
        assembled response, and releases updates re-derived from the result.

        Response transforms run in middleware order, so a middleware placed after this one
        can replace the response after it has been evaluated. Attach this middleware last
        for its evaluation to cover what the caller actually receives; see the package
        README on middleware order.

        This covers what the caller receives, and the evaluated response is what an agent
        run above this middleware stores. Per-service-call history writes happen below it
        and are not covered; see the package README on blocked content and conversation
        history.
        """

        async def _transform(final: "ChatResponse[Any]") -> "ChatResponse[Any]":
            should_block_response = await _should_block_response(
                self._processor,
                self._settings,
                final,
                session_id,
                user_id,
            )
            if should_block_response:
                return self._blocked_response(final)
            # Returning the evaluated response, rather than None, is what makes the
            # released updates be re-derived from it. A finalizer may produce a response
            # that is not the assembly of its own updates, so releasing the buffered
            # updates instead would release content this evaluation never saw.
            return final

        context.stream_result_transforms.append(_transform)
        context.stream_result_to_updates = ChatResponse.to_updates
        context.stream_buffer_updates = True
        return inner
