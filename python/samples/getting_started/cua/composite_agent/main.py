# Copyright (c) Microsoft. All rights reserved.

"""Example of using composite agents (grounding + planning models)."""

import asyncio
import logging

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from computer import Computer

from agent_framework_cua import CuaAgentMiddleware

logger = logging.getLogger(__name__)


async def main():
    """Run a composite agent example combining UI-Tars for grounding and GPT-4o for planning."""
    # Use Docker (cross-platform), or change to:
    # - Computer(os_type="macos", provider_type="lume") for macOS
    # - Computer(os_type="windows", provider_type="winsandbox") for Windows
    async with Computer(os_type="linux", provider_type="docker") as computer:
        # Create middleware with composite agent
        # Note: Instructions are passed to Cua's ComputerAgent through the middleware
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            model="huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B+openai/gpt-4o",
            instructions=(
                "You are a desktop automation assistant. "
                "Use UI-Tars for precise UI element detection and GPT-4o for planning."
            ),
            require_approval=False,  # Disable approval for demo
        )

        # Note: chat_client is required by ChatAgent but won't be used.
        # CuaAgentMiddleware terminates execution and delegates everything to Cua's ComputerAgent.
        dummy_client = OpenAIChatClient(model_id="gpt-4o-mini", api_key="dummy-not-used")
        agent = ChatAgent(
            chat_client=dummy_client,
            middleware=[cua_middleware],
        )

        logger.info("🤖 Starting composite agent...")
        response = await agent.run("Open the Calculator app and compute 15 * 23")

        logger.info("📥 Response: %s", response)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
