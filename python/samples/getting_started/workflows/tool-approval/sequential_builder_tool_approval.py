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
from agent_framework.orchestrations import SequentialBuilder

"""
Sample: Sequential Workflow with Tool Approval Requests

This sample demonstrates how to use SequentialBuilder with tools that require human
approval before execution. The approval flow uses the existing @tool decorator
with approval_mode="always_require" to trigger human-in-the-loop interactions.

This sample works as follows:
1. A SequentialBuilder workflow is created with a single agent that has tools requiring approval.
2. The agent receives a user task and determines it needs to call a sensitive tool.
3. The tool call triggers a function_approval_request Content, pausing the workflow.
4. The sample simulates human approval by responding to the .
5. Once approved, the tool executes and the agent completes its response.
6. The workflow outputs the final conversation with all messages.

Purpose:
Show how tool call approvals integrate seamlessly with SequentialBuilder without
requiring any additional builder configuration.

Demonstrate:
- Using @tool(approval_mode="always_require") for sensitive operations.
- Handling request_info events with function_approval_request Content in sequential workflows.
- Resuming workflow execution after approval via run(responses=..., stream=True).

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


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/getting_started/tools/function_tool_with_approval.py and
# samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_database_schema() -> str:
    """Get the current database schema. Does not require approval."""
    return """
    Tables:
    - users (id, name, email, created_at)
    - orders (id, user_id, total, status, created_at)
    - products (id, name, price, stock)
    """


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
    workflow = SequentialBuilder(participants=[database_agent]).build()

    # 4. Start the workflow with a user task
    print("Starting sequential workflow with tool approval...")
    print("-" * 60)

    # Initiate the first run of the workflow.
    # Runs are not isolated; state is preserved across multiple calls to run.
    stream = workflow.run(
        "Check the schema and then update all orders with status 'pending' to 'processing'", stream=True
    )

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)

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
