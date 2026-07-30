# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import Agent, AgentSession, MessageInjectionMiddleware, enqueue_messages, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
This sample demonstrates MessageInjectionMiddleware with a real FoundryChatClient.

The sample starts an agent run that is expected to call a long-running async tool. While that tool is waiting on
``asyncio.sleep()``, the application regains control and enqueues a new user message into the same AgentSession.
After the tool completes, MessageInjectionMiddleware drains that queued message into the next model call so the model
can include it in the final answer without starting a separate agent run.
"""


load_dotenv()


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
async def slow_inventory_lookup(
    item: Annotated[str, "The item to check inventory for."],
) -> str:
    """Look up inventory for an item, intentionally taking long enough to inject a follow-up message."""
    print(f"Tool: checking inventory for {item!r}...")
    await asyncio.sleep(8)
    print("Tool: inventory lookup finished.")
    return f"{item} is in stock, with curbside pickup available today."


async def main() -> None:
    """Run the message injection middleware sample."""
    print("=== Message Injection Middleware Example ===")

    # 1. Create the message injection middleware and the session that owns its pending-message queue.
    message_injection = MessageInjectionMiddleware()
    session = AgentSession()

    # 2. Create a regular FoundryChatClient-backed agent.
    # For authentication, run `az login` or replace AzureCliCredential with your preferred authentication option.
    agent = Agent(
        client=FoundryChatClient(credential=AzureCliCredential()),
        name="InventoryAgent",
        instructions=(
            "You help with store inventory questions. Always call slow_inventory_lookup before answering inventory "
            "questions. If another user message arrives before your final answer, account for it in that final answer."
        ),
        middleware=[message_injection],
        tools=slow_inventory_lookup,
    )

    # 3. Start the run. The model should call slow_inventory_lookup, which awaits asyncio.sleep().
    question = "Can I pick up a red travel mug today? Check inventory before answering."
    print(f"User:> {question}")
    run_task = asyncio.ensure_future(agent.run(question, session=session))

    # 4. While the tool is sleeping, enqueue a new message into the same session.
    await asyncio.sleep(2)
    follow_up = "Please also mention that I can only pick it up after 5 PM."
    print(f"User (injected while tool is running):> {follow_up}")
    enqueue_messages(session, follow_up)

    # 5. Await the original run. The final model call sees both the tool result and the injected message.
    response = await run_task
    print(f"Assistant:> {response.text}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Message Injection Middleware Example ===
User:> Can I pick up a red travel mug today? Check inventory before answering.
Tool: checking inventory for 'red travel mug'...
User (injected while tool is running):> Please also mention that I can only pick it up after 5 PM.
Tool: inventory lookup finished.
Assistant:> Yes, the red travel mug is in stock and curbside pickup is available today. Since you can only pick it up
after 5 PM, choose an evening pickup window when placing the order.
"""
