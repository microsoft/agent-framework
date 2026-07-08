# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent, AgentLoopMiddleware, AgentSession, TodoProvider, todos_remaining
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent Loop Middleware: todo loop (should_continue via a provider helper)

This sample demonstrates ``AgentLoopMiddleware`` driven by a ``should_continue`` predicate built from
a ``TodoProvider``. The ``todos_remaining`` helper keeps the agent running while it still has open
todo items, so the agent plans work on its first turn and completes one item per turn afterwards.
``max_iterations`` bounds the loop as a safety cap, and a single session keeps the todo state across
iterations. After the run the sample prints the todos the agent created.

The loop is run with streaming, so the injected messages between iterations show up as ``user``
updates; the stream is printed as ``<role>: <content>`` lines.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""


async def todo_loop(client: FoundryChatClient) -> None:
    """Loop while a TodoProvider still has open items."""
    print("\n=== Callable criterion (loop while todos remain) ===")

    # 1. A TodoProvider gives the agent tools to plan and track work as todo items.
    todo_provider = TodoProvider()

    # 2. ``todos_remaining`` builds a ``should_continue`` predicate that returns True while any todo
    #    item is still open. ``max_iterations`` guarantees the loop stops even if the agent stalls.
    loop = AgentLoopMiddleware(
        should_continue=todos_remaining(),
        max_iterations=6,
    )

    agent = Agent(
        client=client,
        name="planner",
        instructions=(
            "You are a writing assistant working through a todo list. "
            "On your FIRST turn, break the task into todo items using your todo tools and stop "
            "(do not start writing yet). On EACH SUBSEQUENT turn, complete exactly ONE remaining "
            "todo item, write its content, and mark it done using your tools — never complete more "
            "than one item per turn. When every item is done, give a brief final summary."
        ),
        context_providers=[todo_provider],
        middleware=[loop],
    )

    # 3. Reuse a single session so todo state persists across loop iterations. Each contiguous
    #    ``user`` block marks the boundary into the next iteration, so we count loop iterations by
    #    those boundaries — robust to the function calling this loop relies on (the todo tools issue
    #    several model calls per iteration, but tool calls/results are never ``user`` updates).
    session = AgentSession()
    prompt = "Plan and write a short 3-section blog post about Rayleigh scattering."
    iterations = 1
    in_user_block = False
    assistant_open = False
    async for update in agent.run(prompt, session=session, stream=True):
        if update.role == "user":
            if not in_user_block:
                iterations += 1
                in_user_block = True
            assistant_open = False
            print(f"\nuser: {update.text}", flush=True)
            continue
        in_user_block = False
        if update.text:
            if not assistant_open:
                print("\nassistant: ", end="", flush=True)
                assistant_open = True
            print(update.text, end="", flush=True)
    print(f"\n\nCompleted in {iterations} iteration(s).")

    # 4. Inspect the todos the agent created, loaded from the same store the loop predicate uses.
    items = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)
    print("\nTodos after the run:")
    for item in items:
        mark = "x" if item.is_complete else " "
        print(f"  [{mark}] {item.id}. {item.title}")


async def main() -> None:
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(credential=credential)
        await todo_loop(client)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (abridged; exact text varies by model):

=== Callable criterion (loop while todos remain) ===
assistant: Here is my plan. I'll create todos for each section.
user: Progress so far:
- Here is my plan. I'll create todos for each section.
user: Continue working on the task. If it is complete, say so.
assistant: Section 1 drafted. Marking it done.
user: Progress so far:
- Section 1 drafted. Marking it done.
user: Continue working on the task. If it is complete, say so.
assistant: Section 2 drafted. Marking it done.
user: Progress so far:
- Section 2 drafted. Marking it done.
user: Continue working on the task. If it is complete, say so.
assistant: Section 3 drafted. Marking it done.

Completed in 4 iteration(s).

Todos after the run:
  [x] 1. Draft "What light is" section
  [x] 2. Draft "How Rayleigh scattering works" section
  [x] 3. Draft "Why the sky is blue" section
"""
