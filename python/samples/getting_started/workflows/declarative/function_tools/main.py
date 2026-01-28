# Copyright (c) Microsoft. All rights reserved.

"""
Demonstrate a workflow that responds to user input using an agent with
function tools assigned. Exits the loop when the user enters "exit".
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from agent_framework import FileCheckpointStorage, RequestInfoEvent, WorkflowOutputEvent
from agent_framework import tool
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_declarative import ExternalInputRequest, ExternalInputResponse, WorkflowFactory
from azure.identity import AzureCliCredential
from pydantic import Field

TEMP_DIR = Path(__file__).with_suffix("").parent / "tmp" / "checkpoints"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class MenuItem:
    category: str
    name: str
    price: float
    is_special: bool = False


MENU_ITEMS = [
    MenuItem(category="Soup", name="Clam Chowder", price=4.95, is_special=True),
    MenuItem(category="Soup", name="Tomato Soup", price=4.95, is_special=False),
    MenuItem(category="Salad", name="Cobb Salad", price=9.99, is_special=False),
    MenuItem(category="Salad", name="House Salad", price=4.95, is_special=False),
    MenuItem(category="Drink", name="Chai Tea", price=2.95, is_special=True),
    MenuItem(category="Drink", name="Soda", price=1.95, is_special=False),
]

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_menu() -> list[dict[str, Any]]:
    """Get all menu items."""
    return [{"category": i.category, "name": i.name, "price": i.price} for i in MENU_ITEMS]

@tool(approval_mode="never_require")
def get_specials() -> list[dict[str, Any]]:
    """Get today's specials."""
    return [{"category": i.category, "name": i.name, "price": i.price} for i in MENU_ITEMS if i.is_special]

@tool(approval_mode="never_require")
def get_item_price(name: Annotated[str, Field(description="Menu item name")]) -> str:
    """Get price of a menu item."""
    for item in MENU_ITEMS:
        if item.name.lower() == name.lower():
            return f"${item.price:.2f}"
    return f"Item '{name}' not found."


async def main():
    # Create agent with tools
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    menu_agent = chat_client.as_agent(
        name="MenuAgent",
        instructions="Answer questions about menu items, specials, and prices.",
        tools=[get_menu, get_specials, get_item_price],
    )

    # Clean up any existing checkpoints
    for file in TEMP_DIR.glob("*"):
        file.unlink()

    factory = WorkflowFactory(checkpoint_storage=FileCheckpointStorage(TEMP_DIR))
    factory.register_agent("MenuAgent", menu_agent)
    workflow = factory.create_workflow_from_yaml_path(Path(__file__).parent / "workflow.yaml")

    # Get initial input
    print("Restaurant Menu Assistant (type 'exit' to quit)\n")
    user_input = input("You: ").strip()  # noqa: ASYNC250
    if not user_input:
        return

    # Run workflow with external loop handling
    pending_request_id: str | None = None
    first_response = True

    while True:
        if pending_request_id:
            response = ExternalInputResponse(user_input=user_input)
            stream = workflow.send_responses_streaming({pending_request_id: response})
        else:
            stream = workflow.run_stream({"userInput": user_input})

        pending_request_id = None
        first_response = True

        async for event in stream:
            if isinstance(event, WorkflowOutputEvent) and isinstance(event.data, str):
                if first_response:
                    print("MenuAgent: ", end="")
                    first_response = False
                print(event.data, end="", flush=True)
            elif isinstance(event, RequestInfoEvent) and isinstance(event.data, ExternalInputRequest):
                pending_request_id = event.request_id

        print()

        if not pending_request_id:
            break

        user_input = input("\nYou: ").strip()
        if not user_input:
            continue


if __name__ == "__main__":
    asyncio.run(main())
