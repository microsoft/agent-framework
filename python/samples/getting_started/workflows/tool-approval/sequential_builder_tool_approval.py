# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import (
    ChatMessage,
    FunctionApprovalRequestContent,
    RequestInfoEvent,
    SequentialBuilder,
    WorkflowOutputEvent,
    tool,
)
from agent_framework.openai import OpenAIChatClient

"""
Sample: Sequential Workflow with Tool Approval Requests

This sample demonstrates how to use SequentialBuilder with tools that require human
approval before execution. The approval flow uses the existing @tool decorator
with approval_mode="always_require" to trigger human-in-the-loop interactions.

This sample works as follows:
1. A SequentialBuilder workflow is created with a single agent that has tools requiring approval.
2. The agent receives a user task and determines it needs to call a sensitive tool.
3. The tool call triggers a FunctionApprovalRequestContent, pausing the workflow.
4. The sample simulates human approval by responding to the RequestInfoEvent.
5. Once approved, the tool executes and the agent completes its response.
6. The workflow outputs the final conversation with all messages.

Purpose:
Show how tool call approvals integrate seamlessly with SequentialBuilder without
requiring any additional builder configuration.

Demonstrate:
- Using @tool(approval_mode="always_require") for sensitive operations.
- Handling RequestInfoEvent with FunctionApprovalRequestContent in sequential workflows.
- Resuming workflow execution after approval via send_responses_streaming.

Prerequisites:
- OpenAI or Azure OpenAI configured with the required environment variables.
- Basic familiarity with SequentialBuilder and streaming workflow events.
"""


# 1. Define tools - one requiring approval, one that doesn't
@tool(approval_mode="always_require")
def execute_database_query(
    query: Annotated[str, "The SQL query to execute against the production database"],
) -> str:
    """Execute a SQL query against the production database. Requires human approval."""
    # In a real implementation, this would execute the query
    return f"Query executed successfully. Results: 3 rows affected by '{query}'"


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_database_schema() -> str:
    """Get the current database schema. Does not require approval."""
    return """
    Tables:
    - users (id, name, email, created_at)
    - orders (id, user_id, total, status, created_at)
    - products (id, name, price, stock)
    """


async def main() -> None:
    # 2. Create the agent with tools (approval mode is set per-tool via decorator)
    chat_client = OpenAIChatClient()
    database_agent = chat_client.as_agent(
        name="DatabaseAgent",
        instructions=(
            "You are a database assistant. You can view the database schema and execute "
            "queries. Always check the schema before running queries. Be careful with "
            "queries that modify data."
        ),
        tools=[get_database_schema, execute_database_query],
    )

    # 3. Build a sequential workflow with the agent
    workflow = SequentialBuilder().participants([database_agent]).build()

    # 4. Start the workflow with a user task
    print("Starting sequential workflow with tool approval...")
    print("-" * 60)

    # Phase 1: Run workflow and collect all events (stream ends at IDLE or IDLE_WITH_PENDING_REQUESTS)
    request_info_events: list[RequestInfoEvent] = []
    async for event in workflow.run_stream(
        "Check the schema and then update all orders with status 'pending' to 'processing'"
    ):
        if isinstance(event, RequestInfoEvent):
            request_info_events.append(event)
            if isinstance(event.data, FunctionApprovalRequestContent):
                print(f"\nApproval requested for tool: {event.data.function_call.name}")
                print(f"  Arguments: {event.data.function_call.arguments}")

    # 5. Handle approval requests
    if request_info_events:
        for request_event in request_info_events:
            if isinstance(request_event.data, FunctionApprovalRequestContent):
                # In a real application, you would prompt the user here
                print("\nSimulating human approval (auto-approving for demo)...")

                # Create approval response
                approval_response = request_event.data.create_response(approved=True)

                # Phase 2: Send approval and continue workflow
                output: list[ChatMessage] | None = None
                async for event in workflow.send_responses_streaming({request_event.request_id: approval_response}):
                    if isinstance(event, WorkflowOutputEvent):
                        output = event.data

                if output:
                    print("\n" + "-" * 60)
                    print("Workflow completed. Final conversation:")
                    for msg in output:
                        role = msg.role.value if hasattr(msg.role, "value") else msg.role
                        text = msg.text[:200] + "..." if len(msg.text) > 200 else msg.text
                        print(f"  [{role}]: {text}")
    else:
        print("No approval requests were generated (schema check may have been sufficient).")

    """
    Sample Output:
    Starting sequential workflow with tool approval...
    ------------------------------------------------------------

    Approval requested for tool: execute_database_query
      Arguments: {"query": "UPDATE orders SET status = 'processing' WHERE status = 'pending'"}

    Simulating human approval (auto-approving for demo)...

    ------------------------------------------------------------
    Workflow completed. Final conversation:
      [user]: Check the schema and then update all orders with status 'pending' to 'processing'
      [assistant]: I've checked the schema and executed the update query. The query
                   "UPDATE orders SET status = 'processing' WHERE status = 'pending'"
                   was executed successfully, affecting 3 rows.
    """


if __name__ == "__main__":
    asyncio.run(main())
