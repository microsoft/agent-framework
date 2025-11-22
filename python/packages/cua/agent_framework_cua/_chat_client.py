# Copyright (c) Microsoft. All rights reserved.

"""Cua chat client for Agent Framework."""

from collections.abc import AsyncGenerator
from typing import Any

from agent_framework import BaseChatClient, ChatMessage, ChatResponse
from agent_framework._middleware import use_chat_middleware

from ._types import CuaModelId


@use_chat_middleware
class CuaChatClient(BaseChatClient):
    """Chat client for Cua integration.

    This client is designed to work with CuaAgentMiddleware. It stores model
    and instruction configuration that the middleware extracts during execution.

    The actual chat completion is handled by CuaAgentMiddleware which delegates
    to Cua's ComputerAgent, so this client's response methods are never called.

    Args:
        model: Cua model identifier (e.g., "anthropic/claude-sonnet-4-5-20250929")
        instructions: Optional system instructions for the agent

    Examples:
        .. code-block:: python

            from agent_framework import ChatAgent
            from agent_framework_cua import CuaChatClient, CuaAgentMiddleware
            from computer import Computer

            async with Computer(os_type="linux", provider_type="docker") as computer:
                # Create Cua chat client with model and instructions
                chat_client = CuaChatClient(
                    model="anthropic/claude-sonnet-4-5-20250929",
                    instructions="You are a desktop automation assistant.",
                )

                # Create middleware
                middleware = CuaAgentMiddleware(computer=computer)

                # Create agent
                agent = ChatAgent(
                    chat_client=chat_client,
                    middleware=[middleware],
                )

                response = await agent.run("Open Firefox")
    """

    def __init__(
        self,
        *,
        model: CuaModelId = "anthropic/claude-sonnet-4-5-20250929",
        instructions: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize CuaChatClient.

        Args:
            model: Cua model identifier
            instructions: Optional system instructions for the agent
            **kwargs: Additional arguments passed to BaseChatClient
        """
        super().__init__(**kwargs)
        self.model = model
        self.instructions = instructions

    async def _inner_get_response(
        self,
        *,
        messages: list[ChatMessage],
        chat_options: dict[str, Any],
        **kwargs: Any,
    ) -> ChatResponse:
        """Get chat response.

        Note: This method should never be called when used with CuaAgentMiddleware,
        as the middleware terminates execution before reaching the chat client.

        This implementation is provided to satisfy BaseChatClient's abstract interface.
        """
        raise RuntimeError(
            "CuaChatClient._inner_get_response should not be called. "
            "Ensure you're using CuaAgentMiddleware which handles execution."
        )

    async def _inner_get_streaming_response(
        self,
        *,
        messages: list[ChatMessage],
        chat_options: dict[str, Any],
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        """Get streaming chat response.

        Note: This method should never be called when used with CuaAgentMiddleware,
        as the middleware terminates execution before reaching the chat client.

        This implementation is provided to satisfy BaseChatClient's abstract interface.
        """
        raise RuntimeError(
            "CuaChatClient._inner_get_streaming_response should not be called. "
            "Ensure you're using CuaAgentMiddleware which handles execution."
        )
        # Make this a generator to satisfy type checker
        yield  # pragma: no cover
