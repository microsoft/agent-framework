# Copyright (c) Microsoft. All rights reserved.
"""Cognee session isolation example"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    import cognee
    from cognee.api.v1.config import config

    from agent_framework import ChatAgent
    from agent_framework.cognee import get_cognee_tools
    from agent_framework.openai import OpenAIChatClient

    # Setup cognee directories
    config.data_root_directory(os.path.join(os.path.dirname(__file__), ".cognee/data"))
    config.system_root_directory(os.path.join(os.path.dirname(__file__), ".cognee/system"))
    await cognee.prune.prune_data()
    await cognee.prune.prune_system(metadata=True)

    client = OpenAIChatClient(model_id="gpt-5")

    # === SESSION 1 ===
    print("\n" + "=" * 60)
    print("BACKEND SESSION (Full Stack Developer)")
    print("=" * 60)
    backend_add, backend_search = get_cognee_tools("session-backend")
    backend = ChatAgent(
        client,
        instructions="You MUST use the cognee_add tool to store any important information the user tells you. You MUST use the cognee_search tool to answer any questions - search first, then answer.",
        tools=[backend_add, backend_search],
    )
    await backend.run("Working on Python FastAPI server. Got error: ConnectionRefusedError on port 8000.")

    # === SESSION 2 ===
    print("\n" + "=" * 60)
    print("FRONTEND SESSION (Full Stack Developer)")
    print("=" * 60)
    frontend_add, frontend_search = get_cognee_tools("session-frontend")
    frontend = ChatAgent(
        client,
        instructions="You MUST use the cognee_add tool to store any important information the user tells you. You MUST use the cognee_search tool to answer any questions - search first, then answer.",
        tools=[frontend_add, frontend_search],
    )
    await frontend.run("Working on React TypeScript app. Got error: TypeError: Cannot read property 'map' of undefined.")

    # === SEARCHING FROM EACH SESSION ===
    print("\n" + "=" * 60)
    print("SEARCHING: 'What error did I get?'")
    print("=" * 60)

    print("\n>>> Backend session searching...")
    backend_result = await backend.run("What error did I get?")
    print(f"\n[BACKEND]: {backend_result}")

    print("\n>>> Frontend session searching...")
    frontend_result = await frontend.run("What error did I get?")
    print(f"\n[FRONTEND]: {frontend_result}")

    # Visualize graph
    print("\n>>> Generating graph visualization...")
    await cognee.visualize_graph()


if __name__ == "__main__":
    asyncio.run(main())
