# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import logging
from pathlib import Path
from typing import cast

from agent_framework import (
    AgentResponse,
    ChatAgent,
    ChatMessage,
    Content,
    FileCheckpointStorage,
    Workflow,
    WorkflowEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
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
- Azure CLI authentication (az login).
- Environment variables configured for AzureOpenAIChatClient.
"""

CHECKPOINT_DIR = Path(__file__).parent / "tmp" / "handoff_checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


@tool(approval_mode="always_require")
def submit_refund(refund_description: str, amount: str, order_id: str) -> str:
    """Capture a refund request for manual review before processing."""
    return f"refund recorded for order {order_id} (amount: {amount}) with details: {refund_description}"


def create_agents(client: AzureOpenAIChatClient) -> tuple[ChatAgent, ChatAgent, ChatAgent]:
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


def create_workflow(checkpoint_storage: FileCheckpointStorage) -> tuple[Workflow, ChatAgent, ChatAgent, ChatAgent]:
    """Build the handoff workflow with checkpointing enabled."""

    client = AzureOpenAIChatClient(credential=AzureCliCredential())
    triage, refund, order = create_agents(client)

    # checkpoint_storage: Enable checkpointing for resume
    # termination_condition: Terminate after 5 user messages for this demo
    workflow = (
        HandoffBuilder(
            name="checkpoint_handoff_demo",
            participants=[triage, refund, order],
            checkpoint_storage=checkpoint_storage,
            termination_condition=lambda conv: sum(1 for msg in conv if msg.role == "user") >= 5,
        )
        .with_start_agent(triage)
        .build()
    )

    return workflow, triage, refund, order


def _print_handoff_agent_user_request(response: AgentResponse) -> None:
    """Display the agent's response messages when requesting user input."""
    if not response.messages:
        print("(No agent messages)")
        return

    print("\n[Agent is requesting your input...]")
    for message in response.messages:
        if not message.text:
            continue
        speaker = message.author_name or message.role
        print(f"  {speaker}: {message.text}")


def _print_handoff_request(request: HandoffAgentUserRequest, request_id: str) -> None:
    """Log pending handoff request details for debugging."""
    print(f"\n{'=' * 60}")
    print("WORKFLOW PAUSED - User input needed")
    print(f"Request ID: {request_id}")
    print(f"Awaiting agent: {request.agent_response.agent_id}")

    _print_handoff_agent_user_request(request.agent_response)

    print(f"{'=' * 60}\n")


def _print_function_approval_request(request: Content, request_id: str) -> None:
    """Log pending tool approval details for debugging."""
    args = request.function_call.parse_arguments() or {}  # type: ignore
    print(f"\n{'=' * 60}")
    print("WORKFLOW PAUSED - Tool approval required")
    print(f"Request ID: {request_id}")
    print(f"Function: {request.function_call.name}")  # type: ignore
    print(f"Arguments:\n{json.dumps(args, indent=2)}")
    print(f"{'=' * 60}\n")


def _build_responses_for_requests(
    pending_requests: list[WorkflowEvent],
    *,
    user_response: str | None,
    approve_tools: bool | None,
) -> dict[str, object]:
    """Create response payloads for each pending request."""
    responses: dict[str, object] = {}
    for request in pending_requests:
        if isinstance(request.data, HandoffAgentUserRequest) and request.request_id:
            if user_response is None:
                raise ValueError("User response is required for HandoffAgentUserRequest")
            responses[request.request_id] = user_response
        elif (
            isinstance(request.data, Content)
            and request.data.type == "function_approval_request"
            and request.request_id
        ):
            if approve_tools is None:
                raise ValueError("Approval decision is required for function approval request")
            responses[request.request_id] = request.data.to_function_approval_response(approved=approve_tools)
        else:
            raise ValueError(f"Unsupported request type: {type(request.data)}")
    return responses


async def run_until_user_input_needed(
    workflow: Workflow,
    initial_message: str | None = None,
    checkpoint_id: str | None = None,
) -> tuple[list[WorkflowEvent], str | None]:
    """
    Run the workflow until it needs user input or approval, or completes.

    Returns:
        Tuple of (pending_requests, checkpoint_id_to_use_for_resume)
    """
    pending_requests: list[WorkflowEvent] = []
    latest_checkpoint_id: str | None = checkpoint_id

    if initial_message:
        print(f"\nStarting workflow with: {initial_message}\n")
        event_stream = workflow.run(message=initial_message, stream=True)  # type: ignore[attr-defined]
    elif checkpoint_id:
        print(f"\nResuming workflow from checkpoint: {checkpoint_id}\n")
        event_stream = workflow.run(checkpoint_id=checkpoint_id, stream=True)  # type: ignore[attr-defined]
    else:
        raise ValueError("Must provide either initial_message or checkpoint_id")

    async for event in event_stream:
        if event.type == "status":
            print(f"[Status] {event.state}")

        elif event.type == "request_info":
            pending_requests.append(event)
            if isinstance(event.data, HandoffAgentUserRequest):
                _print_handoff_request(event.data, event.request_id)
            elif isinstance(event.data, Content) and event.data.type == "function_approval_request":
                _print_function_approval_request(event.data, event.request_id)

        elif event.type == "output":
            print("\n[Workflow Completed]")
            if event.data:
                print(f"Final conversation length: {len(event.data)} messages")
            return [], None

    # Workflow paused with pending requests
    # The latest checkpoint was created at the end of the last superstep
    # We'll use the checkpoint storage to find it
    return pending_requests, latest_checkpoint_id


async def resume_with_responses(
    workflow: Workflow,
    checkpoint_storage: FileCheckpointStorage,
    user_response: str | None = None,
    approve_tools: bool | None = None,
) -> tuple[list[WorkflowEvent], str | None]:
    """
    Resume from checkpoint and send responses.

    Step 1: Restore checkpoint to discover pending request types.
    Step 2: Build typed responses and send via workflow.run(responses=...).

    When response payloads are already known, these can be combined into a single
    workflow.run(stream=True, checkpoint_id=..., responses=...) call.
    """
    print(f"\n{'=' * 60}")
    print("RESUMING WORKFLOW WITH HUMAN INPUT")
    if user_response is not None:
        print(f"User says: {user_response}")
    if approve_tools is not None:
        print(f"Approve tools: {approve_tools}")
    print(f"{'=' * 60}\n")

    # Get the latest checkpoint
    checkpoints = await checkpoint_storage.list_checkpoints()
    if not checkpoints:
        raise RuntimeError("No checkpoints found to resume from")

    # Sort by timestamp to get latest
    checkpoints.sort(key=lambda cp: cp.timestamp, reverse=True)
    latest_checkpoint = checkpoints[0]

    print(f"Restoring checkpoint {latest_checkpoint.checkpoint_id}")

    # First, restore checkpoint to discover pending requests
    restored_requests: list[WorkflowEvent] = []
    async for event in workflow.run(checkpoint_id=latest_checkpoint.checkpoint_id, stream=True):  # type: ignore[attr-defined]
        if event.type == "request_info":
            restored_requests.append(event)
            if isinstance(event.data, HandoffAgentUserRequest):
                _print_handoff_request(event.data, event.request_id)
            elif isinstance(event.data, Content) and event.data.type == "function_approval_request":
                _print_function_approval_request(event.data, event.request_id)

    if not restored_requests:
        raise RuntimeError("No pending requests found after checkpoint restoration")

    responses = _build_responses_for_requests(
        restored_requests,
        user_response=user_response,
        approve_tools=approve_tools,
    )
    print(f"Sending responses for {len(responses)} request(s)")

    new_pending_requests: list[WorkflowEvent] = []

    async for event in workflow.run(stream=True, responses=responses):
        if event.type == "status":
            print(f"[Status] {event.state}")

        elif event.type == "output":
            print("\n[Workflow Output Event - Conversation Update]")
            if event.data and isinstance(event.data, list) and all(isinstance(msg, ChatMessage) for msg in event.data):  # type: ignore
                # Now safe to cast event.data to list[ChatMessage]
                conversation = cast(list[ChatMessage], event.data)  # type: ignore
                for msg in conversation[-3:]:  # Show last 3 messages
                    author = msg.author_name or msg.role
                    text = msg.text[:100] + "..." if len(msg.text) > 100 else msg.text
                    print(f"  {author}: {text}")

        elif event.type == "request_info":
            new_pending_requests.append(event)
            if isinstance(event.data, HandoffAgentUserRequest):
                _print_handoff_request(event.data, event.request_id)
            elif isinstance(event.data, Content) and event.data.type == "function_approval_request":
                _print_function_approval_request(event.data, event.request_id)

    return new_pending_requests, latest_checkpoint.checkpoint_id


async def main() -> None:
    """
    Demonstrate the checkpoint-based pause/resume pattern for handoff workflows.

    This sample shows:
    1. Starting a workflow and getting a HandoffAgentUserRequest
    2. Pausing (checkpoint is saved automatically)
    3. Resuming from checkpoint with a user response or tool approval
    4. Continuing the conversation until completion
    """

    # Enable INFO logging to see workflow progress
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
    )

    # Clean up old checkpoints
    for file in CHECKPOINT_DIR.glob("*.json"):
        file.unlink()
    for file in CHECKPOINT_DIR.glob("*.json.tmp"):
        file.unlink()

    storage = FileCheckpointStorage(storage_path=CHECKPOINT_DIR)
    workflow, _, _, _ = create_workflow(checkpoint_storage=storage)

    print("=" * 60)
    print("HANDOFF WORKFLOW CHECKPOINT DEMO")
    print("=" * 60)

    # Scenario: User needs help with a damaged order
    initial_request = "Hi, my order 12345 arrived damaged. I need a refund."

    # Phase 1: Initial run - workflow will pause when it needs user input
    pending_requests, _ = await run_until_user_input_needed(
        workflow,
        initial_message=initial_request,
    )

    if not pending_requests:
        print("Workflow completed without needing user input")
        return

    print("\n>>> Workflow paused. You could exit the process here.")
    print(f">>> Checkpoint was saved. Pending requests: {len(pending_requests)}")

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
    approval_decisions = [True, True, True]
    handoff_index = 0
    approval_index = 0

    while pending_requests:
        print("\n>>> Simulating process restart...\n")
        workflow_step, _, _, _ = create_workflow(checkpoint_storage=storage)

        needs_user_input = any(isinstance(req.data, HandoffAgentUserRequest) for req in pending_requests)
        needs_tool_approval = any(
            isinstance(req.data, Content) and req.data.type == "function_approval_request" for req in pending_requests
        )

        user_response = None
        if needs_user_input:
            if handoff_index < len(handoff_responses):
                user_response = handoff_responses[handoff_index]
                handoff_index += 1
            else:
                user_response = handoff_responses[-1]
            print(f">>> Responding to handoff request with: {user_response}")

        approval_response = None
        if needs_tool_approval:
            if approval_index < len(approval_decisions):
                approval_response = approval_decisions[approval_index]
                approval_index += 1
            else:
                approval_response = approval_decisions[-1]
            print(">>> Approving pending tool calls from the agent.")

        pending_requests, _ = await resume_with_responses(
            workflow_step,
            storage,
            user_response=user_response,
            approve_tools=approval_response,
        )

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
