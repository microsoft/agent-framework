# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, AgentSession, TodoItem, TodoProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Todo List — Track work items across turns with TodoProvider

This sample shows how to use the ``TodoProvider``, a ``ContextProvider`` that gives an agent a set
of tools for managing a todo list (``todos_add``, ``todos_complete``, ``todos_remove``,
``todos_get_remaining``, ``todos_get_all``) along with instructions on how to use them. The todo
list is stored in the session state and persists across turns, so the agent can plan multi-step
work, track progress, and adjust the list as the conversation evolves.

This is a scripted, non-interactive walkthrough: it sends a sequence of messages to the agent and,
after each turn, prints the agent's reply followed by the current todo list (read directly from the
provider's store). This lets you watch the todo state evolve as the agent adds, completes, and
removes items.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Microsoft Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""


async def print_todo_list(todo_provider: TodoProvider, session: AgentSession) -> None:
    """Read the current todo list straight from the provider's store and print it."""
    # The provider persists todos in its store keyed by ``source_id``; loading them lets the sample
    # display the state without going through the model.
    items: list[TodoItem] = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)

    print("--- Current todo list ---")
    if not items:
        print("  (empty)")
        return

    for item in items:
        mark = "x" if item.is_complete else " "
        line = f"  [{mark}] {item.id}. {item.title}"
        if item.description:
            line += f" — {item.description}"
        print(line)


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # <create_todo_provider>
    # Create the TodoProvider and attach it to the agent as a context provider. The provider
    # contributes the todo-management tools and instructions to every agent invocation.
    todo_provider = TodoProvider()

    agent = Agent(
        client=client,
        name="PlanningAssistant",
        instructions="You are a helpful planning assistant. Use your todo list to plan and track multi-step work.",
        context_providers=[todo_provider],
    )
    # </create_todo_provider>

    # Reuse a single session so the todo state persists across turns.
    session = agent.create_session()

    # A scripted set of turns that exercises the provider end-to-end: the agent should add todos for
    # a multi-step request, mark items complete as progress is reported, and adjust the list on a
    # change of plan.
    user_messages = [
        "I'm organizing a small team offsite. Can you help me plan it? Break the work into a todo list.",
        "I've booked the venue and sent out the invites. Please update the list.",
        "Actually, let's skip catering and instead plan a group hike. Update the plan accordingly.",
    ]

    for user_message in user_messages:
        print(f"User: {user_message}")
        print(f"Agent: {await agent.run(user_message, session=session)}")

        # Print the current todo list so the evolving state is visible after each turn.
        await print_todo_list(todo_provider, session)
        print()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (abridged; exact text varies by model):

User: I'm organizing a small team offsite. Can you help me plan it? Break the work into a todo list.
Agent: Great — I've broken this into a starter plan. Let me know if you'd like to adjust anything.
--- Current todo list ---
  [ ] 1. Pick a date and confirm attendees
  [ ] 2. Book a venue
  [ ] 3. Arrange catering
  [ ] 4. Send out invites

User: I've booked the venue and sent out the invites. Please update the list.
Agent: Nice work! I've marked the venue and invites as done.
--- Current todo list ---
  [ ] 1. Pick a date and confirm attendees
  [x] 2. Book a venue
  [ ] 3. Arrange catering
  [x] 4. Send out invites

User: Actually, let's skip catering and instead plan a group hike. Update the plan accordingly.
Agent: Done — I removed catering and added a group hike to the plan.
--- Current todo list ---
  [ ] 1. Pick a date and confirm attendees
  [x] 2. Book a venue
  [x] 4. Send out invites
  [ ] 5. Plan a group hike
"""
