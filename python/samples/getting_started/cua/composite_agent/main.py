# Copyright (c) Microsoft. All rights reserved.

"""Example of using composite agents (grounding + planning models)."""

import asyncio
import logging

from agent_framework import ChatAgent
from computer import Computer

from agent_framework_cua import CuaAgentMiddleware, CuaChatClient

logger = logging.getLogger(__name__)


async def main():
    """Run a composite agent example combining UI-Tars for grounding and GPT-4o for planning."""
    # Use Docker (cross-platform), or change to:
    # - Computer(os_type="macos", provider_type="lume") for macOS
    # - Computer(os_type="windows", provider_type="winsandbox") for Windows
    async with Computer(
        os_type="linux",
        provider_type="docker",
        image="trycua/cua-xfce:latest",
    ) as computer:
        # Create Cua chat client with composite model
        chat_client = CuaChatClient(
            model="huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B+openai/gpt-4o",
        )

        # Create middleware
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            require_approval=False,  # Disable approval for demo
        )

        # Create agent
        agent = ChatAgent(
            chat_client=chat_client,
            middleware=[cua_middleware],
        )

        logger.info("🤖 Starting composite agent...")
        response = await agent.run("Open the Calculator app and compute 15 * 23")

        logger.info("📥 Response: %s", response)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
