# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
from dataclasses import dataclass
from typing import Annotated, Never

from agent_framework import (
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    WorkflowBuilder,
    WorkflowContext,
    ai_function,
    executor,
    handler,
)
from agent_framework.openai import OpenAIChatClient

"""
Sample: Agents in a workflow with AI functions requiring approval

This sample creates a workflow that automatically replies to incoming emails.
If historical email data is needed, it uses an AI function to read the data,
which requires human approval before execution.

This sample works as follows:
1. An incoming email is received by the workflow.
2. The EmailPreprocessor executor preprocesses the email, adding special notes if the sender is important.
3. The preprocessed email is sent to the Email Writer agent, which generates a response.
4. If the agent needs to read historical email data, it calls the read_historical_email_data AI function,
   which triggers an approval request.
5. The sample automatically approves the request for demonstration purposes.
6. Once approved, the AI function executes and returns the historical email data to the agent.
7. The agent uses the historical data to compose a comprehensive email response.
8. The response is sent to the conclude_workflow_executor, which yields the final response.

Purpose:
Show how to integrate AI functions with approval requests into a workflow.

Demonstrate:
- Creating AI functions that require approval before execution.
- Building a workflow that includes an agent and executors.
- Handling approval requests during workflow execution.

Prerequisites:
- Azure AI Agent Service configured, along with the required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
- Basic familiarity with WorkflowBuilder, edges, events, RequestInfoEvent, and streaming runs.
"""


@ai_function
def get_current_date() -> str:
    """Get the current date in YYYY-MM-DD format."""
    # For demonstration purposes, we return a fixed date.
    return "2025-11-07"


@ai_function
def get_team_members_email_addresses() -> list[dict[str, str]]:
    """Get the email addresses of team members."""
    # In a real implementation, this might query a database or directory service.
    return [
        {
            "name": "Alice",
            "email": "alice@contoso.com",
            "position": "Software Engineer",
            "manager": "John Doe",
        },
        {
            "name": "Bob",
            "email": "bob@contoso.com",
            "position": "Product Manager",
            "manager": "John Doe",
        },
        {
            "name": "Charlie",
            "email": "charlie@contoso.com",
            "position": "Senior Software Engineer",
            "manager": "John Doe",
        },
        {
            "name": "Mike",
            "email": "mike@contoso.com",
            "position": "Principal Software Engineer Manager",
            "manager": "VP of Engineering",
        },
    ]


@ai_function
def get_my_information() -> dict[str, str]:
    """Get my personal information."""
    return {
        "name": "John Doe",
        "email": "john@contoso.com",
        "position": "Software Engineer Manager",
        "manager": "Mike",
    }


@ai_function(approval_mode="always_require")
async def read_historical_email_data(
    email_address: Annotated[str, "The email address to read historical data from"],
    start_date: Annotated[str, "The start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "The end date in YYYY-MM-DD format"],
) -> list[dict[str, str]]:
    """Read historical email data for a given email address and date range."""
    historical_data = {
        "alice@contoso.com": [
            {
                "from": "alice@contoso.com",
                "to": "john@contoso.com",
                "date": "2025-11-05",
                "subject": "Bug Bash Results",
                "body": "We just completed the bug bash and found a few issues that need immediate attention.",
            },
            {
                "from": "alice@contoso.com",
                "to": "john@contoso.com",
                "date": "2025-11-03",
                "subject": "Code Freeze",
                "body": "We are entering code freeze starting tomorrow.",
            },
        ],
        "bob@contoso.com": [
            {
                "from": "bob@contoso.com",
                "to": "john@contoso.com",
                "date": "2025-11-04",
                "subject": "Team Outing",
                "body": "Don't forget about the team outing this Friday!",
            },
            {
                "from": "bob@contoso.com",
                "to": "john@contoso.com",
                "date": "2025-11-02",
                "subject": "Requirements Update",
                "body": "The requirements for the new feature have been updated. Please review them.",
            },
        ],
        "charlie@contoso.com": [
            {
                "from": "charlie@contoso.com",
                "to": "john@contoso.com",
                "date": "2025-11-05",
                "subject": "Project Update",
                "body": "The bug bash went well. A few critical bugs but should be fixed by the end of the week.",
            },
            {
                "from": "charlie@contoso.com",
                "to": "john@contoso.com",
                "date": "2025-11-06",
                "subject": "Code Review",
                "body": "Please review my latest code changes.",
            },
        ],
    }

    emails = historical_data.get(email_address, [])
    return [email for email in emails if start_date <= email["date"] <= end_date]


@ai_function(approval_mode="always_require")
async def send_email(
    to: Annotated[str, "The recipient email address"],
    subject: Annotated[str, "The email subject"],
    body: Annotated[str, "The email body"],
) -> str:
    """Send an email."""
    await asyncio.sleep(1)  # Simulate sending email
    return "Email successfully sent."


@dataclass
class Email:
    sender: str
    subject: str
    body: str


class EmailPreprocessor(Executor):
    def __init__(self, special_email_addresses: set[str]) -> None:
        super().__init__(id="email_preprocessor")
        self.special_email_addresses = special_email_addresses

    @handler
    async def preprocess(self, email: Email, ctx: WorkflowContext[str]) -> None:
        """Preprocess the incoming email."""
        message = str(email)
        if email.sender in self.special_email_addresses:
            note = (
                "Pay special attention to this sender. This email is very important. "
                "Gather relevant information from all previous emails within my team before responding."
            )
            message = f"{note}\n\n{message}"

        await ctx.send_message(message)


@executor(id="conclude_workflow_executor")
async def conclude_workflow(
    email_response: AgentExecutorResponse,
    ctx: WorkflowContext[Never, str],
) -> None:
    """Conclude the workflow by yielding the final email response."""
    await ctx.yield_output(email_response.agent_run_response.text)


async def main() -> None:
    # Create the agent and executors
    chat_client = OpenAIChatClient()
    email_writer = chat_client.create_agent(
        name="Email Writer",
        instructions=("You are an excellent email assistant. You respond to incoming emails."),
        # tools with `approval_mode="always_require"` will trigger approval requests
        tools=[
            read_historical_email_data,
            send_email,
            get_current_date,
            get_team_members_email_addresses,
            get_my_information,
        ],
    )
    email_preprocessor = EmailPreprocessor(special_email_addresses={"mike@contoso.com"})

    # Build the workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(email_preprocessor)
        .add_edge(email_preprocessor, email_writer)
        .add_edge(email_writer, conclude_workflow)
        .build()
    )

    # Simulate an incoming email
    incoming_email = Email(
        sender="mike@contoso.com",
        subject="Important: Project Update",
        body="Please provide your team's status update on the project since last week.",
    )

    responses: dict[str, FunctionApprovalResponseContent] = {}
    output: list[ChatMessage] | None = None
    while True:
        if responses:
            events = await workflow.send_responses(responses)
            responses.clear()
        else:
            events = await workflow.run(incoming_email)

        request_info_events = events.get_request_info_events()
        for request_info_event in request_info_events:
            # We should only expect FunctionApprovalRequestContent in this sample
            if not isinstance(request_info_event.data, FunctionApprovalRequestContent):
                raise ValueError(f"Unexpected request info content type: {type(request_info_event.data)}")

            # Pretty print the function call details
            arguments = json.dumps(request_info_event.data.function_call.parse_arguments(), indent=2)
            print(
                f"Received approval request for function: {request_info_event.data.function_call.name} "
                f"with args:\n{arguments}"
            )

            # For demo purposes, we automatically approve the request
            # The expected response type of the request is `FunctionApprovalResponseContent`,
            # which can be created via `create_response` method on the request content
            print("Performing automatic approval for demo purposes...")
            responses[request_info_event.request_id] = request_info_event.data.create_response(approved=True)

        # Once we get an output event, we can conclude the workflow
        # Outputs can only be produced by the conclude_workflow_executor in this sample
        if outputs := events.get_outputs():
            # We expect only one output from the conclude_workflow_executor
            output = outputs[0]
            break

    if not output:
        raise RuntimeError("Workflow did not produce any output event.")

    print("Final email response conversation:")
    print(output)

    """
    Sample Output:
    Received approval request for function: read_historical_email_data with args:
    {
        "email_address": "alice@contoso.com",
        "start_date": "2025-10-31",
        "end_date": "2025-11-07"
    }
    Performing automatic approval for demo purposes...
    Received approval request for function: read_historical_email_data with args:
    {
        "email_address": "bob@contoso.com",
        "start_date": "2025-10-31",
        "end_date": "2025-11-07"
    }
    Performing automatic approval for demo purposes...
    Received approval request for function: read_historical_email_data with args:
    {
        "email_address": "charlie@contoso.com",
        "start_date": "2025-10-31",
        "end_date": "2025-11-07"
    }
    Performing automatic approval for demo purposes...
    Received approval request for function: send_email with args:
    {
        "to": "mike@contoso.com",
        "subject": "Team's Status Update on the Project",
        "body": "
        Hi Mike,

        Here's the status update from our team:
        - **Bug Bash and Code Freeze:**
            - We recently completed a bug bash, during which several issues were identified. Alice and Charlie are working on fixing these critical bugs, and we anticipate resolving them by the end of this week.
            - We have entered a code freeze as of November 4, 2025.

        - **Requirements Update:**
            - Bob has updated the requirements for a new feature, and all team members are reviewing these changes to ensure alignment.

        - **Ongoing Reviews:**
            - Charlie has submitted his latest code changes for review to ensure they meet our quality standards.

        Please let me know if you need more detailed information or have any questions.

        Best regards,
        John"
    }
    Performing automatic approval for demo purposes...
    Final email response conversation:
    I've sent the status update to Mike with the relevant information from the team. Let me know if there's anything else you need
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
