# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from agent_framework import (
    Agent,
    Content,
    FileCheckpointStorage,
    Workflow,
    WorkflowEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import HandoffAgentUserRequest, HandoffBuilder
from azure.identity import AzureCliCredential

"""
Sample: Handoff Workflow with Tool Approvals + Checkpoint Resume

Demonstrates resuming a handoff workflow from a checkpoint while handling both
HandoffAgentUserRequest prompts and function approval request Content for tool calls
(e.g., submit_refund).

Scenario:
1. User starts a conversation with the workflow.
2. Agents may emit user input requests or tool approval requests.
3. Workflow writes a checkpoint capturing pending requests and pauses.
4. Process can exit/restart.
5. On resume: Restore checkpoint, inspect pending requests, then provide responses.
6. Workflow continues from the saved state.

Pattern:
- workflow.run(checkpoint_id=..., stream=True) to restore checkpoint and discover pending requests.
- workflow.run(stream=True, responses=responses) to supply human replies and approvals.
  (Two steps are needed here because the sample must inspect request types before building responses.
  When response payloads are already known, use the single-call form:
  workflow.run(stream=True, checkpoint_id=..., responses=responses).)

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Azure CLI authentication (az login).
- Environment variables configured for AzureOpenAIResponsesClient.
"""

CHECKPOINT_DIR = Path(__file__).parent / "tmp" / "handoff_checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


@tool(approval_mode="always_require")
def submit_refund(refund_description: str, amount: str, order_id: str) -> str:
    """Capture a refund request for manual review before processing."""
    return f"refund recorded for order {order_id} (amount: {amount}) with details: {refund_description}"


def create_agents(client: AzureOpenAIResponsesClient) -> tuple[Agent, Agent, Agent]:
    """Create a simple handoff scenario: triage, refund, and order specialists."""

    triage = client.as_agent(
        name="triage_agent",
        instructions=(
            "You are a customer service triage agent. Listen to customer issues and determine "
            "if they need refund help or order tracking. Use handoff_to_refund_agent or "
            "handoff_to_order_agent to transfer them."
        ),
    )

    refund = client.as_agent(
        name="refund_agent",
        instructions=(
            "You are a refund specialist. Help customers with refund requests. "
            "Be empathetic and ask for order numbers if not provided. "
            "When the user confirms they want a refund and supplies order details, call submit_refund "
            "to record the request before continuing."
        ),
        tools=[submit_refund],
    )

    order = client.as_agent(
        name="order_agent",
        instructions=(
            "You are an order tracking specialist. Help customers track their orders. "
            "Ask for order numbers and provide shipping updates."
        ),
    )

    return triage, refund, order


def create_workflow(checkpoint_storage: FileCheckpointStorage) -> Workflow:
    """Build the handoff workflow with checkpointing enabled."""

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )
    triage, refund, order = create_agents(client)

    # checkpoint_storage: Enable checkpointing for resume
    # termination_condition: Terminate after 5 user messages for this demo
    return (
        HandoffBuilder(
            name="checkpoint_handoff_demo",
            participants=[triage, refund, order],
            checkpoint_storage=checkpoint_storage,
            termination_condition=lambda conv: sum(1 for msg in conv if msg.role == "user") >= 5,
        )
        .with_start_agent(triage)
        .build()
    )


def print_handoff_agent_user_request(request: HandoffAgentUserRequest, request_id: str) -> None:
    """Log pending handoff request details for debugging."""
    print(f"\n{'=' * 60}")
    print("User input needed")
    print(f"Request ID: {request_id}")

    response = request.agent_response
    if not response.messages:
        print("(No agent messages)")
        return

    for message in response.messages:
        if not message.text:
            continue
        speaker = message.author_name or message.role
        print(f"{speaker}: {message.text}")

    print(f"{'=' * 60}\n")


def print_function_approval_request(request: Content, request_id: str) -> None:
    """Log pending tool approval details for debugging."""
    args = request.function_call.parse_arguments() or {}  # type: ignore
    print(f"\n{'=' * 60}")
    print("Tool approval required")
    print(f"Request ID: {request_id}")
    print(f"Function: {request.function_call.name}")  # type: ignore
    print(f"Arguments:\n{json.dumps(args, indent=2)}")
    print(f"{'=' * 60}\n")


async def main() -> None:
    """
    Demonstrate the checkpoint-based pause/resume pattern for handoff workflows.

    This sample shows:
    1. Starting a workflow and getting a HandoffAgentUserRequest
    2. Pausing (checkpoint is saved automatically)
    3. Resuming from checkpoint with a user response or tool approval
    4. Continuing the conversation until completion
    """
    # Clean up old checkpoints
    for file in CHECKPOINT_DIR.glob("*.json"):
        file.unlink()
    for file in CHECKPOINT_DIR.glob("*.json.tmp"):
        file.unlink()

    storage = FileCheckpointStorage(storage_path=CHECKPOINT_DIR)
    workflow = create_workflow(checkpoint_storage=storage)

    # Scripted human input for demo purposes
    handoff_responses = [
        (
            "The headphones in order 12345 arrived cracked. "
            "Please submit the refund for $89.99 and send a replacement to my original address."
        ),
        "Yes, that covers the damage and refund request.",
        "That's everything I needed for the refund.",
        "Thanks for handling the refund.",
    ]

    print("=" * 60)
    print("HANDOFF WORKFLOW CHECKPOINT DEMO")
    print("=" * 60)

    # Scenario: User needs help with a damaged order
    initial_request = "Hi, my order 12345 arrived damaged. I need a refund."

    # Phase 1: Initial run - workflow will pause when it needs user input
    print("Running initial workflow...")
    results = await workflow.run(message=initial_request, stream=True)

    # Iterate through streamed events and collect request_info events
    request_events: list[WorkflowEvent] = []
    async for event in results:
        event: WorkflowEvent
        if event.type == "request_info":
            request_events.append(event)

    if not request_events:
        print("Workflow completed without needing user input")
        return

    print("=" * 60)
    print("WORKFLOW PAUSED with pending requests")
    print("=" * 60)

    # Phase 2: Running until no more user input is needed
    # This creates a new workflow instance to simulate a fresh process start,
    # but points it to the same checkpoint storage
    while request_events:
        print("\n" + "=" * 60)
        print("Simulating process restart...")
        print("=" * 60)

        workflow = create_workflow(checkpoint_storage=storage)

        responses: dict[str, Any] = {}
        for request_event in request_events:
            print(f"Pending request ID: {request_event.request_id}, Type: {type(request_event.data)}")
            if isinstance(request_event.data, HandoffAgentUserRequest):
                print_handoff_agent_user_request(request_event.data, request_event.request_id)
                response = handoff_responses.pop(0)
                print(f"Responding with: {response}")
                responses[request_event.request_id] = HandoffAgentUserRequest.create_response(response)
            elif isinstance(request_event.data, Content) and request_event.data.type == "function_approval_request":
                print_function_approval_request(request_event.data, request_event.request_id)
                print("Approving tool call...")
                responses[request_event.request_id] = request_event.data.to_function_approval_response(approved=True)
            else:
                # This sample only expects HandoffAgentUserRequest and function approval requests
                raise ValueError(f"Unsupported request type: {type(request_event.data)}")

        checkpoint = await storage.get_latest(workflow_name=workflow.name)
        if not checkpoint:
            raise RuntimeError("No checkpoints found.")
        checkpoint_id = checkpoint.checkpoint_id

        print("Resuming workflow from checkpoint...")
        results = await workflow.run(responses=responses, checkpoint_id=checkpoint_id, stream=True)

        # Iterate through streamed events and collect request_info events
        request_events: list[WorkflowEvent] = []
        async for event in results:
            if event.type == "request_info":
                request_events.append(event)

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
