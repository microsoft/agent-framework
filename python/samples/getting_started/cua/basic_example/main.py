# Copyright (c) Microsoft. All rights reserved.

"""Basic example of using CuaAgentMiddleware with Agent Framework."""

import asyncio
import logging

from agent_framework import ChatAgent
from computer import Computer

from agent_framework_cua import CuaAgentMiddleware, CuaChatClient

logger = logging.getLogger(__name__)


async def main():
    """Run a basic computer use example with Claude."""
    # Initialize Cua computer (Linux Docker container)
    async with Computer(
        os_type="linux",
        provider_type="docker",
        image="trycua/cua-xfce:latest",
    ) as computer:
        # Create Cua chat client with model configuration
        chat_client = CuaChatClient(
            model="anthropic/claude-sonnet-4-5-20250929",
        )

        # Create middleware
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            require_approval=True,
            approval_interval=5,
        )

        # Create Agent Framework agent
        agent = ChatAgent(
            chat_client=chat_client,
            middleware=[cua_middleware],
        )

        # Run agent
        logger.info("🤖 Starting agent...")

        response = await agent.run("Open Firefox and open the website 'cua.ai'")

        logger.info("📥 Response: %s", response)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
