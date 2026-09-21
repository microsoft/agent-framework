# Copyright (c) Microsoft. All rights reserved.

"""Compare immediate agent-tool approval policy with durable workflow approval.

Use ``Agent.as_tool()`` when the child can decide approvals immediately through
``ToolApprovalMiddleware.auto_approval_rules``. Use a workflow when a person or
external system may respond later. The workflow models delegation as a call and
return: the coordinator sends one task to the child, the child may pause for
approval, and the result returns to the same coordinator.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
- FOUNDRY_MODEL: Model deployment name.
- Run ``az login`` before starting the sample.
"""

import asyncio
import os
from collections.abc import AsyncIterable
from typing import Any, Literal

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorResponse,
    Content,
    ToolApprovalMiddleware,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    executor,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatOptions
from azure.identity import AzureCliCredential
from pydantic import BaseModel
from typing_extensions import Never


@tool(approval_mode="always_require")
def reserve_inventory(item: str, quantity: int) -> str:
    """Reserve a quantity of an inventory item."""
    return f"Reserved {quantity} unit(s) of {item}."


def approve_small_reservations(function_call: Content) -> bool:
    """Approve only small inventory reservations during the current invocation.

    The middleware evaluates this policy when a request appears, so the same
    approach applies to tools discovered at runtime through MCP or Skills.
    """
    if function_call.name != "reserve_inventory":
        return False
    arguments = function_call.parse_arguments() or {}
    quantity = arguments.get("quantity")
    return isinstance(quantity, int) and 0 < quantity <= 5


def create_client() -> FoundryChatClient:
    """Create the chat client used by both examples."""
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )


async def run_agent_tool_example() -> None:
    """Run an immediate approval policy entirely inside Agent.as_tool()."""
    inventory_agent = Agent(
        client=create_client(),
        name="InventoryAgent",
        instructions="Reserve the requested inventory using the available tool.",
        tools=[reserve_inventory],
        middleware=[
            ToolApprovalMiddleware(
                auto_approval_rules=[approve_small_reservations],
            )
        ],
    )
    coordinator = Agent(
        client=create_client(),
        name="Coordinator",
        instructions="Delegate inventory reservations to InventoryAgent.",
        tools=[inventory_agent.as_tool()],
    )

    result = await coordinator.run("Reserve 2 keyboards.")
    print("Agent.as_tool result:")
    print(result.text)


async def collect_workflow_events(stream: AsyncIterable[WorkflowEvent]) -> dict[str, Content]:
    """Collect approval requests and display completed workflow output."""
    requests: dict[str, Content] = {}
    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, Content):
            requests[event.request_id] = event.data
        elif event.type == "output" and isinstance(event.data, str):
            print("Workflow result:")
            print(event.data)
    return requests


class CoordinatorDecision(BaseModel):
    """Choose whether to delegate a task or complete the caller's response."""

    action: Literal["delegate", "complete"]
    message: str


def chose_action(expected: Literal["delegate", "complete"]):
    """Create an edge condition for a structured coordinator decision."""

    def condition(response: Any) -> bool:
        return (
            isinstance(response, AgentExecutorResponse)
            and isinstance(response.agent_response.value, CoordinatorDecision)
            and response.agent_response.value.action == expected
        )

    return condition


@executor(id="complete_reservation")
async def complete_reservation(
    response: AgentExecutorResponse,
    ctx: WorkflowContext[Never, str],
) -> None:
    """Return the coordinator's completed response."""
    decision = response.agent_response.value
    if not isinstance(decision, CoordinatorDecision):
        raise ValueError("Coordinator response must be a CoordinatorDecision.")
    await ctx.yield_output(decision.message)


async def run_workflow_example() -> None:
    """Delegate to a child and return its result through a durable workflow."""
    coordinator = AgentExecutor(
        Agent(
            client=create_client(),
            name="Coordinator",
            instructions=(
                "You coordinate inventory reservations. For a new request, set action to 'delegate' and message "
                "to a concise task for InventoryAgent. When InventoryAgent returns a result, set action to "
                "'complete' and message to a user-facing summary of that result."
            ),
            default_options=OpenAIChatOptions[Any](response_format=CoordinatorDecision),
        )
    )
    inventory_agent = Agent(
        client=create_client(),
        name="InventoryAgent",
        instructions="Reserve the requested inventory using the available tool.",
        tools=[reserve_inventory],
    )
    inventory = AgentExecutor(inventory_agent)
    workflow = (
        WorkflowBuilder(start_executor=coordinator)
        .add_edge(coordinator, inventory, condition=chose_action("delegate"))
        .add_edge(inventory, coordinator)
        .add_edge(coordinator, complete_reservation, condition=chose_action("complete"))
        .build()
    )

    requests = await collect_workflow_events(workflow.run("Reserve 20 keyboards.", stream=True))
    while requests:
        responses: dict[str, Content] = {}
        for request_id, request in requests.items():
            if request.type != "function_approval_request" or request.function_call is None:
                continue
            print("Workflow paused for approval:")
            print(f"  Tool: {request.function_call.name}")
            print(f"  Arguments: {request.function_call.arguments}")

            # A real application can persist a workflow checkpoint and return much later.
            await asyncio.sleep(1)
            responses[request_id] = request.to_function_approval_response(approved=True)

        requests = await collect_workflow_events(workflow.run(stream=True, responses=responses))


async def main() -> None:
    """Run the immediate and delayed approval approaches in order."""
    print("1. Immediate policy with Agent.as_tool")
    await run_agent_tool_example()

    print("\n2. Delayed approval with a workflow")
    await run_workflow_example()


if __name__ == "__main__":
    asyncio.run(main())
