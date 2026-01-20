# Copyright (c) Microsoft. All rights reserved.

"""
CustomerSupport workflow sample.

This workflow demonstrates using multiple agents to provide automated
troubleshooting steps to resolve common issues with escalation options.

Example input: "My PC keeps rebooting and I can't use it."

Usage:
    python main.py

The workflow:
1. SelfServiceAgent: Works with user to provide troubleshooting steps
2. TicketingAgent: Creates a ticket if issue needs escalation
3. TicketRoutingAgent: Determines which team should handle the ticket
4. WindowsSupportAgent: Provides Windows-specific troubleshooting
5. TicketResolutionAgent: Resolves the ticket when issue is fixed
6. TicketEscalationAgent: Escalates to human support if needed
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path

from agent_framework import RequestInfoEvent, WorkflowOutputEvent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.declarative import (
    AgentExternalInputRequest,
    AgentExternalInputResponse,
    WorkflowFactory,
)
from azure.identity import AzureCliCredential
from pydantic import BaseModel, Field
from ticketing_plugin import TicketingPlugin

logging.basicConfig(level=logging.ERROR)

# ANSI color codes for output formatting
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RESET = "\033[0m"

# Agent Instructions

SELF_SERVICE_INSTRUCTIONS = """
Use your knowledge to work with the user to provide the best possible troubleshooting steps.

- If the user confirms that the issue is resolved, then the issue is resolved.
- If the user reports that the issue persists, then escalate.
""".strip()

TICKETING_INSTRUCTIONS = """Always create a ticket in Azure DevOps using the available tools.

Include the following information in the TicketSummary.

- Issue description: {{IssueDescription}}
- Attempted resolution steps: {{AttemptedResolutionSteps}}

After creating the ticket, provide the user with the ticket ID."""

TICKET_ROUTING_INSTRUCTIONS = """Determine how to route the given issue to the appropriate support team.

Choose from the available teams and their functions:
- Windows Activation Support: Windows license activation issues
- Windows Support: Windows related issues
- Azure Support: Azure related issues
- Network Support: Network related issues
- Hardware Support: Hardware related issues
- Microsoft Office Support: Microsoft Office related issues
- General Support: General issues not related to the above categories"""

WINDOWS_SUPPORT_INSTRUCTIONS = """
Use your knowledge to work with the user to provide the best possible troubleshooting steps
for issues related to Windows operating system.

- Utilize the "Attempted Resolutions Steps" as a starting point for your troubleshooting.
- Never escalate without troubleshooting with the user.
- If the user confirms that the issue is resolved, then the issue is resolved.
- If the user reports that the issue persists, then escalate.

Issue: {{IssueDescription}}
Attempted Resolution Steps: {{AttemptedResolutionSteps}}"""

RESOLUTION_INSTRUCTIONS = """Resolve the following ticket in Azure DevOps.
Always include the resolution details.

- Ticket ID: #{{TicketId}}
- Resolution Summary: {{ResolutionSummary}}"""

ESCALATION_INSTRUCTIONS = """
You escalate the provided issue to human support team by sending an email.

Here are some additional details that might help:
- TicketId : {{TicketId}}
- IssueDescription : {{IssueDescription}}
- AttemptedResolutionSteps : {{AttemptedResolutionSteps}}

Before escalating, gather the user's email address for follow-up.
If not known, ask the user for their email address so that the support team can reach them when needed.

When sending the email, include the following details:
- To: support@contoso.com
- Cc: user's email address
- Subject of the email: "Support Ticket - {TicketId} - [Compact Issue Description]"
- Body:
  - Issue description
  - Attempted resolution steps
  - User's email address
  - Any other relevant information from the conversation history

Assure the user that their issue will be resolved and provide them with a ticket ID for reference."""


# Pydantic models for structured outputs


class SelfServiceResponse(BaseModel):
    """Response from self-service agent evaluation."""

    IsResolved: bool = Field(description="True if the user issue/ask has been resolved.")
    NeedsTicket: bool = Field(description="True if the user issue/ask requires that a ticket be filed.")
    IssueDescription: str = Field(description="A concise description of the issue.")
    AttemptedResolutionSteps: str = Field(description="An outline of the steps taken to attempt resolution.")


class TicketingResponse(BaseModel):
    """Response from ticketing agent."""

    TicketId: str = Field(description="The identifier of the ticket created in response to the user issue.")
    TicketSummary: str = Field(description="The summary of the ticket created in response to the user issue.")


class RoutingResponse(BaseModel):
    """Response from routing agent."""

    TeamName: str = Field(description="The name of the team to route the issue")


class SupportResponse(BaseModel):
    """Response from support agent."""

    IsResolved: bool = Field(description="True if the user issue/ask has been resolved.")
    NeedsEscalation: bool = Field(
        description="True resolution could not be achieved and the issue/ask requires escalation."
    )
    ResolutionSummary: str = Field(description="The summary of the steps that led to resolution.")


class EscalationResponse(BaseModel):
    """Response from escalation agent."""

    IsComplete: bool = Field(description="Has the email been sent and no more user input is required.")
    UserMessage: str = Field(description="A natural language message to the user.")


async def main() -> None:
    """Run the customer support workflow."""
    # Create ticketing plugin
    plugin = TicketingPlugin()

    # Create Azure OpenAI client
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents with structured outputs
    self_service_agent = chat_client.as_agent(
        name="SelfServiceAgent",
        instructions=SELF_SERVICE_INSTRUCTIONS,
        default_options={"response_format": SelfServiceResponse},
    )

    ticketing_agent = chat_client.as_agent(
        name="TicketingAgent",
        instructions=TICKETING_INSTRUCTIONS,
        tools=plugin.get_functions(),
        default_options={"response_format": TicketingResponse},
    )

    routing_agent = chat_client.as_agent(
        name="TicketRoutingAgent",
        instructions=TICKET_ROUTING_INSTRUCTIONS,
        tools=[plugin.get_ticket],
        default_options={"response_format": RoutingResponse},
    )

    windows_support_agent = chat_client.as_agent(
        name="WindowsSupportAgent",
        instructions=WINDOWS_SUPPORT_INSTRUCTIONS,
        tools=[plugin.get_ticket],
        default_options={"response_format": SupportResponse},
    )

    resolution_agent = chat_client.as_agent(
        name="TicketResolutionAgent",
        instructions=RESOLUTION_INSTRUCTIONS,
        tools=[plugin.resolve_ticket],
    )

    escalation_agent = chat_client.as_agent(
        name="TicketEscalationAgent",
        instructions=ESCALATION_INSTRUCTIONS,
        tools=[plugin.get_ticket, plugin.send_notification],
        default_options={"response_format": EscalationResponse},
    )

    # Agent registry for lookup
    agents = {
        "SelfServiceAgent": self_service_agent,
        "TicketingAgent": ticketing_agent,
        "TicketRoutingAgent": routing_agent,
        "WindowsSupportAgent": windows_support_agent,
        "TicketResolutionAgent": resolution_agent,
        "TicketEscalationAgent": escalation_agent,
    }

    # Print loaded agents (similar to .NET "PROMPT AGENT: AgentName:1")
    for agent_name in agents:
        print(f"{CYAN}PROMPT AGENT: {agent_name}:1{RESET}")

    # Create workflow factory
    factory = WorkflowFactory(agents=agents)

    # Load workflow from YAML
    samples_root = Path(__file__).parent.parent.parent.parent.parent.parent.parent
    workflow_path = samples_root / "workflow-samples" / "CustomerSupport.yaml"
    if not workflow_path.exists():
        # Fall back to local copy if workflow-samples doesn't exist
        workflow_path = Path(__file__).parent / "workflow.yaml"

    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print()
    print("=" * 60)

    # Example input
    user_input = "My computer won't boot"
    pending_request_id: str | None = None

    # Track responses for formatting
    accumulated_response: str = ""
    last_agent_name: str | None = None

    print(f"\n{GREEN}INPUT:{RESET} {user_input}\n")

    while True:
        if pending_request_id:
            # Continue workflow with user response
            print(f"\n{YELLOW}WORKFLOW:{RESET} Restore\n")
            response = AgentExternalInputResponse(user_input=user_input)
            stream = workflow.send_responses_streaming({pending_request_id: response})
            pending_request_id = None
        else:
            # Start workflow
            stream = workflow.run_stream(user_input)

        async for event in stream:
            if isinstance(event, WorkflowOutputEvent):
                data = event.data
                source_id = getattr(event, "source_executor_id", "")

                # Check if this is a SendActivity output (activity text from log_ticket, log_route, etc.)
                if "log_" in source_id.lower():
                    # Print any accumulated agent response first
                    if accumulated_response and last_agent_name:
                        msg_id = f"msg_{uuid.uuid4().hex[:32]}"
                        print(f"{CYAN}{last_agent_name.upper()}:{RESET} [{msg_id}]")
                        try:
                            parsed = json.loads(accumulated_response)
                            print(json.dumps(parsed))
                        except (json.JSONDecodeError, TypeError):
                            print(accumulated_response)
                        accumulated_response = ""
                        last_agent_name = None
                    # Print activity
                    print(f"\n{MAGENTA}ACTIVITY:{RESET}")
                    print(data)
                else:
                    # Accumulate agent response (streaming text)
                    if isinstance(data, str):
                        accumulated_response += data
                    else:
                        accumulated_response += str(data)

            elif isinstance(event, RequestInfoEvent) and isinstance(event.data, AgentExternalInputRequest):
                request = event.data

                # The agent_response from the request contains the structured response
                agent_name = request.agent_name
                agent_response = request.agent_response

                # Print the agent's response
                if agent_response:
                    msg_id = f"msg_{uuid.uuid4().hex[:32]}"
                    print(f"{CYAN}{agent_name.upper()}:{RESET} [{msg_id}]")
                    try:
                        parsed = json.loads(agent_response)
                        print(json.dumps(parsed))
                    except (json.JSONDecodeError, TypeError):
                        print(agent_response)

                # Clear accumulated since we printed from the request
                accumulated_response = ""
                last_agent_name = agent_name

                pending_request_id = event.request_id
                print(f"\n{YELLOW}WORKFLOW:{RESET} Yield")

        # Print any remaining accumulated response at end of stream
        if accumulated_response:
            # Try to identify which agent this came from based on content
            msg_id = f"msg_{uuid.uuid4().hex[:32]}"
            print(f"\nResponse: [{msg_id}]")
            try:
                parsed = json.loads(accumulated_response)
                print(json.dumps(parsed))
            except (json.JSONDecodeError, TypeError):
                print(accumulated_response)
            accumulated_response = ""

        if not pending_request_id:
            break

        # Get next user input
        user_input = input(f"\n{GREEN}INPUT:{RESET} ").strip()  # noqa: ASYNC250
        if not user_input:
            print("Exiting...")
            break
        print()

    print("\n" + "=" * 60)
    print("Workflow Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
