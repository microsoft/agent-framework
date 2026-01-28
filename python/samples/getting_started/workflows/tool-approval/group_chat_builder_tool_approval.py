# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import (
    AgentRunUpdateEvent,
    FunctionApprovalRequestContent,
    GroupChatBuilder,
    GroupChatRequestSentEvent,
    GroupChatState,
    RequestInfoEvent,
    tool,
)
from agent_framework.openai import OpenAIChatClient

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
- Handling RequestInfoEvent in group chat scenarios.
- Multi-round group chat with tool approval interruption and resumption.

Prerequisites:
- OpenAI or Azure OpenAI configured with the required environment variables.
- Basic familiarity with GroupChatBuilder and streaming workflow events.
"""


# 1. Define tools for different agents
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
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
    workflow = (
        GroupChatBuilder()
        .with_orchestrator(selection_func=select_next_speaker)
        .participants([qa_engineer, devops_engineer])
        # Set a hard limit to 4 rounds
        # First round: QAEngineer speaks
        # Second round: DevOpsEngineer speaks (check staging + create rollback)
        # Third round: DevOpsEngineer speaks with an approval request (deploy to production)
        # Fourth round: DevOpsEngineer speaks again after approval
        .with_max_rounds(4)
        .build()
    )

    # 5. Start the workflow
    print("Starting group chat workflow for software deployment...")
    print(f"Agents: {[qa_engineer.name, devops_engineer.name]}")
    print("-" * 60)

    # Phase 1: Run workflow and collect all events (stream ends at IDLE or IDLE_WITH_PENDING_REQUESTS)
    request_info_events: list[RequestInfoEvent] = []
    # Keep track of the last response to format output nicely in streaming mode
    last_response_id: str | None = None
    async for event in workflow.run_stream(
        "We need to deploy version 2.4.0 to production. Please coordinate the deployment."
    ):
        if isinstance(event, RequestInfoEvent):
            request_info_events.append(event)
            if isinstance(event.data, FunctionApprovalRequestContent):
                print("\n[APPROVAL REQUIRED] From agent:", event.source_executor_id)
                print(f"  Tool: {event.data.function_call.name}")
                print(f"  Arguments: {event.data.function_call.arguments}")
        elif isinstance(event, AgentRunUpdateEvent):
            if not event.data.text:
                continue  # Skip empty updates
            response_id = event.data.response_id
            if response_id != last_response_id:
                if last_response_id is not None:
                    print("\n")
                print(f"- {event.executor_id}:", end=" ", flush=True)
                last_response_id = response_id
            print(event.data, end="", flush=True)
        elif isinstance(event, GroupChatRequestSentEvent):
            print(f"\n[REQUEST SENT ({event.round_index})] to agent: {event.participant_name}")

    # 6. Handle approval requests
    if request_info_events:
        for request_event in request_info_events:
            if isinstance(request_event.data, FunctionApprovalRequestContent):
                print("\n" + "=" * 60)
                print("Human review required for production deployment!")
                print("In a real scenario, you would review the deployment details here.")
                print("Simulating approval for demo purposes...")
                print("=" * 60)

                # Create approval response
                approval_response = request_event.data.create_response(approved=True)

                # Phase 2: Send approval and continue workflow
                # Keep track of the response to format output nicely in streaming mode
                last_response_id: str | None = None
                async for event in workflow.send_responses_streaming({request_event.request_id: approval_response}):
                    if isinstance(event, AgentRunUpdateEvent):
                        if not event.data.text:
                            continue  # Skip empty updates
                        response_id = event.data.response_id
                        if response_id != last_response_id:
                            if last_response_id is not None:
                                print("\n")
                            print(f"- {event.executor_id}:", end=" ", flush=True)
                            last_response_id = response_id
                        print(event.data, end="", flush=True)
                    elif isinstance(event, GroupChatRequestSentEvent):
                        print(f"\n[REQUEST SENT ({event.round_index})] To agent: {event.participant_name}")

                print("\n" + "-" * 60)
                print("Deployment workflow completed successfully!")
                print("All agents have finished their tasks.")
    else:
        print("\nWorkflow completed without requiring production deployment approval.")

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
