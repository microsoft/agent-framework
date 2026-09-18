# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import (
    Agent,
    AgentResponse,
    AgentSession,
    Content,
    Message,
    ToolApprovalMiddleware,
    create_always_approve_tool_response,
    create_always_approve_tool_with_arguments_response,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
This sample demonstrates how a host application can decide which approval
requests may run now, which must be rejected, and which can be remembered for
future runs.

The model may not request every tool on every run. The important part is the
approval mechanism:

1. Tools that are safe to run immediately use ``approval_mode="never_require"``.
2. Sensitive tools use ``approval_mode="always_require"``.
3. ``ToolApprovalMiddleware`` coordinates approval prompts and standing rules.
4. The host turns user policy into ``function_approval_response`` content:
   - approve for this request only;
   - reject for this request;
   - approve and remember the tool for future requests;
   - approve and remember the tool only when called again with the same arguments.
5. Heuristic auto-approval rules can approve low-risk function calls before
   the user is prompted.
"""

# Load environment variables from .env file
load_dotenv()


@tool(approval_mode="never_require")
def lookup_ticket(ticket_id: Annotated[str, "Support ticket id, for example T-123"]) -> str:
    """Look up a support ticket. This read-only tool runs without approval."""
    return f"Ticket {ticket_id}: customer confirmed the issue can be closed."


@tool(approval_mode="always_require")
def close_ticket(
    ticket_id: Annotated[str, "Support ticket id, for example T-123"],
    resolution: Annotated[str, "Short resolution text"],
) -> str:
    """Close a support ticket."""
    return f"Ticket {ticket_id} closed with resolution: {resolution}"


@tool(approval_mode="always_require")
def notify_customer(
    ticket_id: Annotated[str, "Support ticket id, for example T-123"],
    message: Annotated[str, "Message to send to the customer"],
) -> str:
    """Notify the customer about a ticket update."""
    return f"Customer notified for {ticket_id}: {message}"


@tool(approval_mode="always_require")
def add_internal_note(
    ticket_id: Annotated[str, "Support ticket id, for example T-123"],
    note: Annotated[str, "Internal note text"],
) -> str:
    """Add an internal note to a support ticket."""
    return f"Internal note added to {ticket_id}: {note}"


@tool(approval_mode="always_require")
def delete_attachment(
    ticket_id: Annotated[str, "Support ticket id, for example T-123"],
    attachment_name: Annotated[str, "Attachment file name"],
) -> str:
    """Delete an attachment from a support ticket."""
    return f"Deleted {attachment_name} from ticket {ticket_id}."


def auto_approve_low_risk_notes(function_call: Content) -> bool:
    """Heuristic rule: auto-approve short internal notes for the target ticket."""
    if function_call.name != "add_internal_note":
        return False

    arguments = function_call.parse_arguments() or {}
    note = str(arguments.get("note", ""))
    return arguments.get("ticket_id") == "T-123" and len(note) <= 120


def approval_response_for_user_policy(request: Content) -> Content:
    """Convert user/host policy into an approval response for one tool request."""
    function_call = request.function_call
    if function_call is None or function_call.name is None:
        return request.to_function_approval_response(approved=False)

    tool_name = function_call.name
    print(f"Approval requested: {tool_name}({function_call.arguments})")

    if tool_name in {"close_ticket"}:
        print(f"Decision: approve and remember future {tool_name} calls with these exact arguments")
        return create_always_approve_tool_with_arguments_response(request)

    if tool_name in {"notify_customer"}:
        print(f"Decision: approve and remember all future {tool_name} calls")
        return create_always_approve_tool_response(request)

    if tool_name in {"delete_attachment"}:
        print(f"Decision: reject {tool_name} for this run")
        return request.to_function_approval_response(approved=False)

    print(f"Decision: reject {tool_name}; no policy allowed it")
    return request.to_function_approval_response(approved=False)


async def resolve_approval_requests(agent: Agent, response: AgentResponse, session: AgentSession) -> AgentResponse:
    """Resolve approval prompts until the agent returns a regular answer."""
    result = response
    while result.user_input_requests:
        approval_responses = [approval_response_for_user_policy(request) for request in result.user_input_requests]
        result = await agent.run(Message(role="user", contents=approval_responses), session=session)
    return result


async def main() -> None:
    """Run the tool approval middleware sample."""
    # 1. Create a regular chat client.
    client = FoundryChatClient(credential=AzureCliCredential())

    # 2. Create an agent with sensitive tools and opt-in ToolApprovalMiddleware.
    agent = Agent(
        client=client,
        name="SupportAgent",
        instructions=(
            "You are a support agent. Use tools when useful. "
            "Look up ticket T-123, close it if the customer confirmed, notify the customer, "
            "add a short internal note, and do not delete attachments unless the tool is approved."
        ),
        tools=[lookup_ticket, close_ticket, notify_customer, add_internal_note, delete_attachment],
        middleware=[ToolApprovalMiddleware(auto_approval_rules=[auto_approve_low_risk_notes])],
    )
    session = agent.create_session()

    # 3. Ask for work that may trigger a mixed batch of safe and sensitive tool calls.
    query = (
        "Please process ticket T-123: check the ticket, close it as resolved, "
        "notify the customer, add a short internal note, and remove debug.log if it is attached."
    )
    print(f"User: {query}")
    result = await agent.run(query, session=session)

    # 4. Convert approval requests into approve/reject/always-approve responses.
    result = await resolve_approval_requests(agent, result, session)
    print(f"Agent: {result.text}")

    # 5. Later runs can use remembered approval rules:
    #    - notify_customer: all future calls to the tool.
    #    - close_ticket: only future calls with the same arguments.
    #    - add_internal_note: low-risk matching calls are auto-approved by the heuristic callback.
    follow_up = "Send the customer a short follow-up for ticket T-123."
    print(f"\nUser: {follow_up}")
    result = await agent.run(follow_up, session=session)
    result = await resolve_approval_requests(agent, result, session)
    print(f"Agent: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
User: Please process ticket T-123: check the ticket, close it as resolved,
notify the customer, add a short internal note, and remove debug.log if it is attached.
Approval requested: close_ticket({"ticket_id": "T-123", "resolution": "resolved"})
Decision: approve and remember future close_ticket calls with these exact arguments
Approval requested: notify_customer({"ticket_id": "T-123", "message": "Your ticket has been resolved."})
Decision: approve and remember all future notify_customer calls
Approval requested: delete_attachment({"ticket_id": "T-123", "attachment_name": "debug.log"})
Decision: reject delete_attachment for this run
Agent: Ticket T-123 was closed, the customer was notified, and a short internal note was added.
I did not delete debug.log.

User: Send the customer a short follow-up for ticket T-123.
Agent: The customer was sent a short follow-up for ticket T-123.
"""
