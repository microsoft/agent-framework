# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated, cast

from agent_framework import (
    AgentResponse,
    Message,
    WorkflowEvent,
    WorkflowRunState,
    tool,
)
from agent_framework.azure import AzureAIProjectAgentProvider
from agent_framework.orchestrations import (
    HandoffAgentUserRequest,
    HandoffBuilder,
    create_handoff_tools,
)
from azure.identity.aio import AzureCliCredential

"""Sample: Handoff Workflow with Azure AI Agent Service using Pre-Registered Tools.

Azure AI Agent Service requires tools to be registered at agent creation time, not
dynamically at request time. This sample demonstrates how to use create_handoff_tools()
to pre-create handoff tools and pass them to provider.create_agent(), enabling the
handoff workflow pattern with Azure AI agents.

Prerequisites:
    - Azure AI Agent Service configured with required environment variables
      (AZURE_AI_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME)
    - `az login` (Azure CLI authentication)

Key Concepts:
    - create_handoff_tools(): Creates handoff tools upfront for agent creation
    - Pre-registration pattern: Tools passed to provider.create_agent(tools=...)
    - Duplicate handling: HandoffBuilder gracefully skips pre-registered tools
      instead of raising ValueError
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# See:
# samples/getting_started/tools/function_tool_with_approval.py
# samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def process_refund(order_number: Annotated[str, "Order number to process refund for"]) -> str:
    """Simulated function to process a refund for a given order number."""
    return f"Refund processed successfully for order {order_number}."


@tool(approval_mode="never_require")
def check_order_status(order_number: Annotated[str, "Order number to check status for"]) -> str:
    """Simulated function to check the status of a given order number."""
    return f"Order {order_number} is currently being processed and will ship in 2 business days."


def _handle_events(events: list[WorkflowEvent]) -> list[WorkflowEvent[HandoffAgentUserRequest]]:
    """Process workflow events and extract any pending user input requests.

    Args:
        events: List of WorkflowEvent to process

    Returns:
        List of WorkflowEvent[HandoffAgentUserRequest] representing pending user input requests
    """
    requests: list[WorkflowEvent[HandoffAgentUserRequest]] = []

    for event in events:
        if event.type == "handoff_sent":
            print(f"\n[Handoff from {event.data.source} to {event.data.target} initiated.]")
        elif event.type == "status" and event.state in {
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        }:
            print(f"\n[Workflow Status] {event.state}")
        elif event.type == "output":
            data = event.data
            if isinstance(data, AgentResponse):
                for message in data.messages:
                    if not message.text:
                        continue
                    speaker = message.author_name or message.role
                    print(f"- {speaker}: {message.text}")
            elif isinstance(data, list):
                conversation = cast(list[Message], data)
                print("\n=== Final Conversation Snapshot ===")
                for message in conversation:
                    speaker = message.author_name or message.role
                    print(f"- {speaker}: {message.text or [content.type for content in message.contents]}")
                print("===================================")
        elif event.type == "request_info" and isinstance(event.data, HandoffAgentUserRequest):
            _print_handoff_agent_user_request(event.data.agent_response)
            requests.append(cast(WorkflowEvent[HandoffAgentUserRequest], event))

    return requests


def _print_handoff_agent_user_request(response: AgentResponse) -> None:
    """Display the agent's response messages when requesting user input."""
    if not response.messages:
        raise RuntimeError("Cannot print agent responses: response has no messages.")

    print("\n[Agent is requesting your input...]")
    for message in response.messages:
        if not message.text:
            continue
        speaker = message.author_name or message.role
        print(f"- {speaker}: {message.text}")


async def main() -> None:
    """Main entry point for the Azure AI handoff workflow demo.

    This function demonstrates:
    1. Using create_handoff_tools() to pre-create handoff tools for Azure AI Agent Service
    2. Creating agents with pre-registered handoff tools via provider.create_agent()
    3. Building a handoff workflow where HandoffBuilder skips pre-registered tools
    4. Running the workflow with scripted user responses
    """
    async with (
        AzureCliCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # ============================================================
        # KEY PATTERN: Pre-create handoff tools BEFORE creating agents
        # ============================================================
        # Azure AI Agent Service requires tools at agent creation time.
        # create_handoff_tools() generates the same tools that HandoffBuilder
        # would auto-register, but upfront so they can be passed to
        # provider.create_agent().
        # NOTE: Azure AI Agent Service requires agent names to use only
        # alphanumeric characters and hyphens (no underscores).
        specialist_ids = ["refund-agent", "order-agent"]
        triage_handoff_tools = create_handoff_tools(
            specialist_ids,
            descriptions={
                "refund-agent": "Transfer to refund specialist for processing refunds.",
                "order-agent": "Transfer to order specialist for shipping and order inquiries.",
            },
        )

        # Create triage agent with BOTH handoff tools and no domain tools.
        # The handoff tools are pre-registered at creation time.
        triage = await provider.create_agent(
            instructions=(
                "You are frontline support triage. Route customer issues to the appropriate specialist agents "
                "based on the problem described."
            ),
            name="triage-agent",
            tools=triage_handoff_tools,
        )

        # Create specialist agents with their domain-specific tools.
        # Specialists don't need handoff tools pre-registered because they
        # don't route to other agents in this example.
        refund = await provider.create_agent(
            instructions="You process refund requests.",
            name="refund-agent",
            tools=[process_refund],
        )

        order = await provider.create_agent(
            instructions="You handle order and shipping inquiries.",
            name="order-agent",
            tools=[check_order_status],
        )

        # Build the handoff workflow.
        # HandoffBuilder will detect that triage already has handoff tools
        # pre-registered and skip them instead of raising ValueError.
        workflow = (
            HandoffBuilder(
                name="azure_ai_customer_support",
                participants=[triage, refund, order],
                termination_condition=lambda conversation: (
                    len(conversation) > 0 and "welcome" in conversation[-1].text.lower()
                ),
            )
            .with_start_agent(triage)
            .build()
        )

        # Scripted user responses for reproducible demo.
        # In a real application, replace with actual user input collection.
        scripted_responses = [
            "My order 1234 arrived damaged and I'd like a refund.",
            "Thanks for resolving this.",
        ]

        # Start the workflow with the initial user message
        print("[Starting Azure AI handoff workflow with pre-registered tools...]\n")
        initial_message = "Hello, I need assistance with my recent purchase."
        print(f"- User: {initial_message}")
        workflow_result = workflow.run(initial_message, stream=True)
        pending_requests = _handle_events([event async for event in workflow_result])

        # Process the request/response cycle
        while pending_requests:
            if not scripted_responses:
                responses = {req.request_id: HandoffAgentUserRequest.terminate() for req in pending_requests}
            else:
                user_response = scripted_responses.pop(0)
                print(f"\n- User: {user_response}")
                responses = {
                    req.request_id: HandoffAgentUserRequest.create_response(user_response) for req in pending_requests
                }

            events = await workflow.run(responses=responses)
            pending_requests = _handle_events(events)

    """
    Sample Output:

    [Starting Azure AI handoff workflow with pre-registered tools...]

    - User: Hello, I need assistance with my recent purchase.
    - triage-agent: Could you please provide more details about the issue?

    [Workflow Status] IDLE_WITH_PENDING_REQUESTS

    - User: My order 1234 arrived damaged and I'd like a refund.

    [Handoff from triage-agent to refund-agent initiated.]
    - refund-agent: Refund processed successfully for order 1234.

    [Workflow Status] IDLE_WITH_PENDING_REQUESTS

    - User: Thanks for resolving this.

    === Final Conversation Snapshot ===
    - user: Hello, I need assistance with my recent purchase.
    - triage-agent: Could you please provide more details about the issue?
    - user: My order 1234 arrived damaged and I'd like a refund.
    - refund-agent: Refund processed successfully for order 1234.
    - user: Thanks for resolving this.
    - triage-agent: You're welcome! Have a great day!
    ===================================

    [Workflow Status] IDLE
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
