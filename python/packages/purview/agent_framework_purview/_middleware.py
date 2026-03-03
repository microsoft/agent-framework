# Copyright (c) Microsoft. All rights reserved.

import logging
from collections.abc import Awaitable, Callable

from agent_framework import AgentContext, AgentMiddleware, ChatContext, ChatMiddleware, MiddlewareTermination
from agent_framework.azure._entra_id_authentication import AzureCredentialTypes, AzureTokenProvider

from ._cache import CacheProvider
from ._client import PurviewClient
from ._exceptions import PurviewPaymentRequiredError
from ._models import Activity
from ._processor import ScopedContentProcessor
from ._settings import PurviewSettings

logger = logging.getLogger("agent_framework.purview")


class PurviewPolicyMiddleware(AgentMiddleware):
    """Agent middleware that enforces Purview policies on prompt and response.

    Accepts a TokenCredential, AsyncTokenCredential, or callable token provider.

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
        if context.session and context.session.service_session_id:
            return context.session.service_session_id

        for message in context.messages:
            conversation_id = message.additional_properties.get("conversation_id")
            if conversation_id is not None:
                return str(conversation_id)

        return None

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:  # type: ignore[override]
        resolved_user_id: str | None = None
        try:
            # Pre (prompt) check
            session_id = self._get_agent_session_id(context)
            should_block_prompt, resolved_user_id = await self._processor.process_messages(
                context.messages, Activity.UPLOAD_TEXT, session_id=session_id
            )
            if should_block_prompt:
                from agent_framework import AgentResponse, Message

                context.result = AgentResponse(
                    messages=[
                        Message(
                            role="system", text=self._settings.get("blocked_prompt_message", "Prompt blocked by policy")
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

        try:
            # Post (response) check only if we have a normal AgentResponse
            # Use the same user_id from the request for the response evaluation
            session_id_response = self._get_agent_session_id(context)
            if session_id_response is None:
                session_id_response = session_id
            if context.result and not context.stream:
                should_block_response, _ = await self._processor.process_messages(
                    context.result.messages,  # type: ignore[union-attr]
                    Activity.DOWNLOAD_TEXT,
                    session_id=session_id,
                    user_id=resolved_user_id,
                )
                if should_block_response:
                    from agent_framework import AgentResponse, Message

                    context.result = AgentResponse(
                        messages=[
                            Message(
                                role="system",
                                text=self._settings.get("blocked_response_message", "Response blocked by policy"),
                            )
                        ]
                    )
            else:
                # Streaming responses are not supported for post-checks
                logger.debug("Streaming responses are not supported for Purview policy post-checks")
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy post-check: {ex}")
            if not self._settings.get("ignore_payment_required", False):
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy post-check: {ex}")
            if not self._settings.get("ignore_exceptions", False):
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
    ) -> None:  # type: ignore[override]
        resolved_user_id: str | None = None
        try:
            session_id = context.options.get("conversation_id") if context.options else None
            should_block_prompt, resolved_user_id = await self._processor.process_messages(
                context.messages, Activity.UPLOAD_TEXT, session_id=session_id
            )
            if should_block_prompt:
                from agent_framework import ChatResponse, Message

                blocked_message = Message(
                    role="system", text=self._settings.get("blocked_prompt_message", "Prompt blocked by policy")
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

        try:
            # Post (response) evaluation only if non-streaming and we have messages result shape
            # Use the same user_id from the request for the response evaluation
            session_id_response = context.options.get("conversation_id") if context.options else None
            if session_id_response is None:
                session_id_response = session_id
            if context.result and not context.stream:
                result_obj = context.result
                messages = getattr(result_obj, "messages", None)
                if messages:
                    should_block_response, _ = await self._processor.process_messages(
                        messages, Activity.DOWNLOAD_TEXT, session_id=session_id_response, user_id=resolved_user_id
                    )
                    if should_block_response:
                        from agent_framework import ChatResponse, Message

                        blocked_message = Message(
                            role="system",
                            text=self._settings.get("blocked_response_message", "Response blocked by policy"),
                        )
                        context.result = ChatResponse(messages=[blocked_message])
            else:
                logger.debug("Streaming responses are not supported for Purview policy post-checks")
        except PurviewPaymentRequiredError as ex:
            logger.error(f"Purview payment required error in policy post-check: {ex}")
            if not self._settings.get("ignore_payment_required", False):
                raise
        except Exception as ex:
            logger.error(f"Error in Purview policy post-check: {ex}")
            if not self._settings.get("ignore_exceptions", False):
                raise
