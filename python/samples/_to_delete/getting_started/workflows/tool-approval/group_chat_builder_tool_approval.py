# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import Annotated, cast

from agent_framework import (
    ChatMessage,
    Content,
    WorkflowEvent,
    tool,
)
from agent_framework.openai import OpenAIChatClient
from agent_framework.orchestrations import GroupChatBuilder, GroupChatState

"""
Sample: Group Chat Workflow with Tool Approval Requests

This sample demonstrates how to use GroupChatBuilder with tools that require human
approval before execution. A group of specialized agents collaborate on a task, and
sensitive tool calls trigger human-in-the-loop approval.

This sample works as follows:
1. A GroupChatBuilder workflow is created with multiple specialized agents.
2. A selector function determines which agent speaks next based on conversation state.
3. Agents collaborate on a software deployment task.
4. When the deployment agent tries to deploy to production, it triggers an approval request.
5. The sample simulates human approval and the workflow completes.

Purpose:
Show how tool call approvals integrate with multi-agent group chat workflows where
different agents have different levels of tool access.

Demonstrate:
- Using set_select_speakers_func with agents that have approval-required tools.
- Handling request_info events (type='request_info') in group chat scenarios.
- Multi-round group chat with tool approval interruption and resumption.

Prerequisites:
- OpenAI or Azure OpenAI configured with the required environment variables.
- Basic familiarity with GroupChatBuilder and streaming workflow events.
"""


# 1. Define tools for different agents
# NOTE: approval_mode="never_require" is for sample brevity.
# Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py
# and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def run_tests(test_suite: Annotated[str, "Name of the test suite to run"]) -> str:
    """Run automated tests for the application."""
    return f"Test suite '{test_suite}' completed: 47 passed, 0 failed, 0 skipped"


@tool(approval_mode="never_require")
def check_staging_status() -> str:
    """Check the current status of the staging environment."""
    return "Staging environment: Healthy, Version 2.3.0 deployed, All services running"


@tool(approval_mode="always_require")
def deploy_to_production(
    version: Annotated[str, "The version to deploy"],
    components: Annotated[str, "Comma-separated list of components to deploy"],
) -> str:
    """Deploy specified components to production. Requires human approval."""
    return f"Production deployment complete: Version {version}, Components: {components}"


@tool(approval_mode="never_require")
def create_rollback_plan(version: Annotated[str, "The version being deployed"]) -> str:
    """Create a rollback plan for the deployment."""
    return (
        f"Rollback plan created for version {version}: "
        "Automated rollback to v2.2.0 if health checks fail within 5 minutes"
    )


# 2. Define the speaker selector function
def select_next_speaker(state: GroupChatState) -> str:
    """Select the next speaker based on the conversation flow.

    This simple selector follows a predefined flow:
    1. QA Engineer runs tests
    2. DevOps Engineer checks staging and creates rollback plan
    3. DevOps Engineer deploys to production (triggers approval)
    """
    if not state.conversation:
        raise RuntimeError("Conversation is empty; cannot select next speaker.")

    if len(state.conversation) == 1:
        return "QAEngineer"  # First speaker

    return "DevOpsEngineer"  # Subsequent speakers


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, Content] | None:
    """Process events from the workflow stream to capture human feedback requests."""
    requests: dict[str, Content] = {}
    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, Content):
            # We are only expecting tool approval requests in this sample
            requests[event.request_id] = event.data
        elif event.type == "output":
            # The output of the workflow comes from the orchestrator and it's a list of messages
            print("\n" + "=" * 60)
            print("Workflow summary:")
            outputs = cast(list[ChatMessage], event.data)
            for msg in outputs:
                speaker = msg.author_name or msg.role
                print(f"[{speaker}]: {msg.text}")

    responses: dict[str, Content] = {}
    if requests:
        for request_id, request in requests.items():
            if request.type == "function_approval_request":
                print("\n[APPROVAL REQUIRED]")
                print(f"  Tool: {request.function_call.name}")  # type: ignore
                print(f"  Arguments: {request.function_call.arguments}")  # type: ignore
                print(f"Simulating human approval for: {request.function_call.name}")  # type: ignore
                # Create approval response
                responses[request_id] = request.to_function_approval_response(approved=True)

    return responses if responses else None


async def main() -> None:
    # 3. Create specialized agents
    chat_client = OpenAIChatClient()

    qa_engineer = chat_client.as_agent(
        name="QAEngineer",
        instructions=(
            "You are a QA engineer responsible for running tests before deployment. "
            "Run the appropriate test suites and report results clearly."
        ),
        tools=[run_tests],
    )

    devops_engineer = chat_client.as_agent(
        name="DevOpsEngineer",
        instructions=(
            "You are a DevOps engineer responsible for deployments. First check staging "
            "status and create a rollback plan, then proceed with production deployment. "
            "Always ensure safety measures are in place before deploying."
        ),
        tools=[check_staging_status, create_rollback_plan, deploy_to_production],
    )

    # 4. Build a group chat workflow with the selector function
    # max_rounds=4: Set a hard limit to 4 rounds
    # First round: QAEngineer speaks
    # Second round: DevOpsEngineer speaks (check staging + create rollback)
    # Third round: DevOpsEngineer speaks with an approval request (deploy to production)
    # Fourth round: DevOpsEngineer speaks again after approval
    workflow = GroupChatBuilder(
        participants=[qa_engineer, devops_engineer],
        max_rounds=4,
        selection_func=select_next_speaker,
    ).build()

    # 5. Start the workflow
    print("Starting group chat workflow for software deployment...")
    print(f"Agents: {[qa_engineer.name, devops_engineer.name]}")
    print("-" * 60)

    # Initiate the first run of the workflow.
    # Runs are not isolated; state is preserved across multiple calls to run.
    stream = workflow.run(
        "We need to deploy version 2.4.0 to production. Please coordinate the deployment.", stream=True
    )

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)

    """
    Sample Output:
    Starting group chat workflow for software deployment...
    Agents: QA Engineer, DevOps Engineer
    ------------------------------------------------------------

    [QAEngineer]: Running the integration test suite to verify the application
    before deployment... Test suite 'integration' completed: 47 passed, 0 failed.
    All tests passing - ready for deployment.

    [DevOpsEngineer]: Checking staging environment status... Staging is healthy
    with version 2.3.0. Creating rollback plan for version 2.4.0... Rollback plan
    created with automated rollback to v2.2.0 if health checks fail.

    [APPROVAL REQUIRED]
      Tool: deploy_to_production
      Arguments: {"version": "2.4.0", "components": "api,web,worker"}

    ============================================================
    Human review required for production deployment!
    In a real scenario, you would review the deployment details here.
    Simulating approval for demo purposes...
    ============================================================

    [DevOpsEngineer]: Production deployment complete! Version 2.4.0 has been
    successfully deployed with components: api, web, worker.

    ------------------------------------------------------------
    Deployment workflow completed successfully!
    All agents have finished their tasks.
    """


if __name__ == "__main__":
    asyncio.run(main())
