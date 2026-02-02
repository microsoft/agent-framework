# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import (
    AgentResponse,
    ChatAgent,
    ChatMessage,
    FunctionCallContent,
    FunctionResultContent,
    HandoffAgentUserRequest,
    HandoffBuilder,
    Role,
    WorkflowAgent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""Sample: Handoff Workflow as Agent with Human-in-the-Loop.

This sample demonstrates how to use a handoff workflow as an agent, enabling
human-in-the-loop interactions through the agent interface.

A handoff workflow defines a pattern that assembles agents in a mesh topology, allowing
them to transfer control to each other based on the conversation context.

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables configured for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)

Key Concepts:
    - Auto-registered handoff tools: HandoffBuilder automatically creates handoff tools
      for each participant, allowing the coordinator to transfer control to specialists
    - Termination condition: Controls when the workflow stops requesting user input
    - Request/response cycle: Workflow requests input, user responds, cycle continues
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def process_refund(order_number: Annotated[str, "Order number to process refund for"]) -> str:
    """Simulated function to process a refund for a given order number."""
    return f"Refund processed successfully for order {order_number}."


@tool(approval_mode="never_require")
def check_order_status(order_number: Annotated[str, "Order number to check status for"]) -> str:
    """Simulated function to check the status of a given order number."""
    return f"Order {order_number} is currently being processed and will ship in 2 business days."


@tool(approval_mode="never_require")
def process_return(order_number: Annotated[str, "Order number to process return for"]) -> str:
    """Simulated function to process a return for a given order number."""
    return f"Return initiated successfully for order {order_number}. You will receive return instructions via email."


def create_agents(chat_client: AzureOpenAIChatClient) -> tuple[ChatAgent, ChatAgent, ChatAgent, ChatAgent]:
    """Create and configure the triage and specialist agents.

    Args:
        chat_client: The AzureOpenAIChatClient to use for creating agents.

    Returns:
        Tuple of (triage_agent, refund_agent, order_agent, return_agent)
    """
    # Triage agent: Acts as the frontline dispatcher
    triage_agent = chat_client.as_agent(
        instructions=(
            "You are frontline support triage. Route customer issues to the appropriate specialist agents "
            "based on the problem described."
        ),
        name="triage_agent",
    )

    # Refund specialist: Handles refund requests
    refund_agent = chat_client.as_agent(
        instructions="You process refund requests.",
        name="refund_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[process_refund],
    )

    # Order/shipping specialist: Resolves delivery issues
    order_agent = chat_client.as_agent(
        instructions="You handle order and shipping inquiries.",
        name="order_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[check_order_status],
    )

    # Return specialist: Handles return requests
    return_agent = chat_client.as_agent(
        instructions="You manage product return requests.",
        name="return_agent",
        # In a real application, an agent can have multiple tools; here we keep it simple
        tools=[process_return],
    )

    return triage_agent, refund_agent, order_agent, return_agent


def handle_response_and_requests(response: AgentResponse) -> dict[str, HandoffAgentUserRequest]:
    """Process agent response messages and extract any user requests.

    This function inspects the agent response and:
    - Displays agent messages to the console
    - Collects HandoffAgentUserRequest instances for response handling

    Args:
        response: The AgentResponse from the agent run call.

    Returns:
        A dictionary mapping request IDs to HandoffAgentUserRequest instances.
    """
    pending_requests: dict[str, HandoffAgentUserRequest] = {}
    for message in response.messages:
        if message.text:
            print(f"- {message.author_name or message.role.value}: {message.text}")
        for content in message.contents:
            if isinstance(content, FunctionCallContent):
                if isinstance(content.arguments, dict):
                    request = WorkflowAgent.RequestInfoFunctionArgs.from_dict(content.arguments)
                elif isinstance(content.arguments, str):
                    request = WorkflowAgent.RequestInfoFunctionArgs.from_json(content.arguments)
                else:
                    raise ValueError("Invalid arguments type. Expecting a request info structure for this sample.")
                if isinstance(request.data, HandoffAgentUserRequest):
                    pending_requests[request.request_id] = request.data
    return pending_requests


async def main() -> None:
    """Main entry point for the handoff workflow demo.

    This function demonstrates:
    1. Creating triage and specialist agents
    2. Building a handoff workflow with custom termination condition
    3. Running the workflow with scripted user responses
    4. Processing events and handling user input requests

    The workflow uses scripted responses instead of interactive input to make
    the demo reproducible and testable. In a production application, you would
    replace the scripted_responses with actual user input collection.
    """
    # Initialize the Azure OpenAI chat client
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create all agents: triage + specialists
    triage, refund, order, support = create_agents(chat_client)

    # Build the handoff workflow
    # - participants: All agents that can participate in the workflow
    # - with_start_agent: The triage agent is designated as the start agent, which means
    #   it receives all user input first and orchestrates handoffs to specialists
    # - with_termination_condition: Custom logic to stop the request/response loop.
    #   Without this, the default behavior continues requesting user input until max_turns
    #   is reached. Here we use a custom condition that checks if the conversation has ended
    #   naturally (when one of the agents says something like "you're welcome").
    agent = (
        HandoffBuilder(
            name="customer_support_handoff",
            participants=[triage, refund, order, support],
        )
        .with_start_agent(triage)
        .with_termination_condition(
            # Custom termination: Check if one of the agents has provided a closing message.
            # This looks for the last message containing "welcome", which indicates the
            # conversation has concluded naturally.
            lambda conversation: len(conversation) > 0 and "welcome" in conversation[-1].text.lower()
        )
        .build()
        .as_agent()  # Convert workflow to agent interface
    )

    # Scripted user responses for reproducible demo
    # In a console application, replace this with:
    #   user_input = input("Your response: ")
    # or integrate with a UI/chat interface
    scripted_responses = [
        "My order 1234 arrived damaged and the packaging was destroyed. I'd like to return it.",
        "Please also process a refund for order 1234.",
        "Thanks for resolving this.",
    ]

    # Start the workflow with the initial user message
    print("[Starting workflow with initial user message...]\n")
    initial_message = "Hello, I need assistance with my recent purchase."
    print(f"- User: {initial_message}")
    response = await agent.run(initial_message)
    pending_requests = handle_response_and_requests(response)

    # Process the request/response cycle
    # The workflow will continue requesting input until:
    # 1. The termination condition is met, OR
    # 2. We run out of scripted responses
    while pending_requests:
        for request in pending_requests.values():
            for message in request.agent_response.messages:
                if message.text:
                    print(f"- {message.author_name or message.role.value}: {message.text}")

        if not scripted_responses:
            # No more scripted responses; terminate the workflow
            responses = {req_id: HandoffAgentUserRequest.terminate() for req_id in pending_requests}
        else:
            # Get the next scripted response
            user_response = scripted_responses.pop(0)
            print(f"\n- User: {user_response}")

            # Send response(s) to all pending requests
            # In this demo, there's typically one request per cycle, but the API supports multiple
            responses = {req_id: HandoffAgentUserRequest.create_response(user_response) for req_id in pending_requests}

        function_results = [
            FunctionResultContent(call_id=req_id, result=response) for req_id, response in responses.items()
        ]
        response = await agent.run(ChatMessage(role=Role.TOOL, contents=function_results))
        pending_requests = handle_response_and_requests(response)


if __name__ == "__main__":
    asyncio.run(main())
