# Copyright (c) Microsoft. All rights reserved.

"""Basic example of using CuaAgentMiddleware with Agent Framework."""

import asyncio
import logging

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from computer import Computer

from agent_framework_cua import CuaAgentMiddleware

logger = logging.getLogger(__name__)


async def main():
    """Run a basic computer use example with Claude."""
    # Initialize Cua computer (Linux Docker container)
    async with Computer(os_type="linux", provider_type="docker") as computer:
        # Create middleware with Anthropic Claude
        # Note: The middleware delegates to Cua's agent, so the model is specified here
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            model="anthropic/claude-sonnet-4-5-20250929",
            require_approval=True,
            approval_interval=5,
        )

        # Create Agent Framework agent with Cua middleware
        # Note: chat_client is required by ChatAgent but won't be used because
        # CuaAgentMiddleware terminates execution and delegates everything to Cua
        # Pass a dummy API key since it won't be called
        dummy_client = OpenAIChatClient(model_id="gpt-4o-mini", api_key="dummy-not-used")
        agent = ChatAgent(
            chat_client=dummy_client,
            middleware=[cua_middleware],
            instructions="You are a desktop automation assistant. Be precise and careful.",
        )

        # Run agent
        logger.info("🤖 Starting agent...")
        response = await agent.run("Open Firefox and search for 'Python tutorials'")

        logger.info("📥 Response: %s", response)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
