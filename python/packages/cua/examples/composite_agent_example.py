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
    async with Computer(os_type="macos", provider_type="lume") as computer:
        # Create middleware with composite agent
        cua_middleware = CuaAgentMiddleware(
            computer=computer,
            model="huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B+openai/gpt-4o",
            require_approval=False,  # Disable approval for demo
        )

        # Note: chat_client and instructions are required by ChatAgent but won't be used.
        # CuaAgentMiddleware terminates execution and delegates everything to Cua's ComputerAgent.
        dummy_client = OpenAIChatClient(model_id="gpt-4o-mini", api_key="dummy-not-used")
        agent = ChatAgent(
            chat_client=dummy_client,
            middleware=[cua_middleware],
            instructions=(
                "You are a desktop automation assistant. "
                "Use UI-Tars for precise UI element detection and GPT-4o for planning."
            ),
        )

        logger.info("🤖 Starting composite agent...")
        response = await agent.run("Open the Calculator app and compute 15 * 23")

        logger.info("📥 Response: %s", response)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
