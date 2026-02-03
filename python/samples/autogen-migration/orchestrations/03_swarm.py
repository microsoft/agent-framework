# Copyright (c) Microsoft. All rights reserved.
"""AutoGen Swarm pattern vs Agent Framework HandoffBuilder.

Demonstrates agent handoff coordination where agents can transfer control
to other specialized agents based on the task requirements.
"""

import asyncio


async def run_autogen() -> None:
    """AutoGen's Swarm pattern with human-in-the-loop handoffs."""
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.conditions import HandoffTermination, TextMentionTermination
    from autogen_agentchat.messages import HandoffMessage
    from autogen_agentchat.teams import Swarm
    from autogen_agentchat.ui import Console
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    client = OpenAIChatCompletionClient(model="gpt-4.1-mini")

    # Create triage agent that routes to specialists
    triage_agent = AssistantAgent(
        name="triage",
        model_client=client,
        system_message=(
            "You are a triage agent. Analyze the user's request and hand off to the appropriate specialist.\n"
            "If you need information from the user, first send your message, then handoff to user.\n"
            "Use TERMINATE when the issue is fully resolved."
        ),
        handoffs=["billing_agent", "technical_support", "user"],
        model_client_stream=True,
    )

    # Create billing specialist
    billing_agent = AssistantAgent(
        name="billing_agent",
        model_client=client,
        system_message=(
            "You are a billing specialist. Help with payment and billing questions.\n"
            "If you need information from the user, first send your message, then handoff to user.\n"
            "When the issue is resolved, handoff to triage to finalize."
        ),
        handoffs=["triage", "user"],
        model_client_stream=True,
    )

    # Create technical support specialist
    tech_support = AssistantAgent(
        name="technical_support",
        model_client=client,
        system_message=(
            "You are technical support. Help with technical issues.\n"
            "If you need information from the user, first send your message, then handoff to user.\n"
            "When the issue is resolved, handoff to triage to finalize."
        ),
        handoffs=["triage", "user"],
        model_client_stream=True,
    )

    # Create swarm team with human-in-the-loop termination
    termination = HandoffTermination(target="user") | TextMentionTermination("TERMINATE")
    team = Swarm(
        participants=[triage_agent, billing_agent, tech_support],
        termination_condition=termination,
    )

    # Scripted user responses for demonstration
    scripted_responses = [
        "I was charged twice for my subscription",
        "Yes, the charge of $49.99 appears twice on my credit card statement.",
        "Thank you for your help!",
    ]
    response_index = 0

    # Run with human-in-the-loop pattern
    print("[AutoGen] Swarm handoff conversation:")
    task_result = await Console(team.run_stream(task=scripted_responses[response_index]))
    last_message = task_result.messages[-1]
    response_index += 1

    # Continue conversation when agents handoff to user
    while (
        isinstance(last_message, HandoffMessage)
        and last_message.target == "user"
        and response_index < len(scripted_responses)
    ):
        user_message = scripted_responses[response_index]
        task_result = await Console(
            team.run_stream(task=HandoffMessage(source="user", target=last_message.source, content=user_message))
        )
        last_message = task_result.messages[-1]
        response_index += 1


async def run_agent_framework() -> None:
    """Agent Framework's HandoffBuilder for agent coordination."""
    from agent_framework import (
        AgentRunUpdateEvent,
        HandoffBuilder,
        HandoffUserInputRequest,
        RequestInfoEvent,
        WorkflowRunState,
        WorkflowStatusEvent,
        tool,
    )
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(model_id="gpt-4.1-mini")

    # Create triage agent
    triage_agent = client.as_agent(
        name="triage",
        instructions=(
            "You are a triage agent. Analyze the user's request and route to the appropriate specialist:\n"
            "- For billing issues: call handoff_to_billing_agent\n"
            "- For technical issues: call handoff_to_technical_support"
        ),
        description="Routes requests to appropriate specialists",
    )

    # Create billing specialist
    billing_agent = client.as_agent(
        name="billing_agent",
        instructions="You are a billing specialist. Help with payment and billing questions. Provide clear assistance.",
        description="Handles billing and payment questions",
    )

    # Create technical support specialist
    tech_support = client.as_agent(
        name="technical_support",
        instructions="You are technical support. Help with technical issues. Provide clear assistance.",
        description="Handles technical support questions",
    )

    # Create handoff workflow - simpler configuration
    # After specialists respond, control returns to user (via triage as coordinator)
    workflow = (
        HandoffBuilder(
            name="support_handoff",
            participants=[triage_agent, billing_agent, tech_support],
        )
        .set_coordinator(triage_agent)
        .add_handoff(triage_agent, [billing_agent, tech_support])
        .with_termination_condition(lambda conv: sum(1 for msg in conv if msg.role.value == "user") > 3)
        .build()
    )

    # Scripted user responses
    scripted_responses = [
        "I was charged twice for my subscription",
        "Yes, the charge of $49.99 appears twice on my credit card statement.",
        "Thank you for your help!",
    ]

    # Run with initial message
    print("[Agent Framework] Handoff conversation:")
    print("---------- user ----------")
    print(scripted_responses[0])

    current_executor = None
    stream_line_open = False
    pending_requests: list[RequestInfoEvent] = []

    async for event in workflow.run_stream(scripted_responses[0]):
        if isinstance(event, AgentRunUpdateEvent):
            # Print executor name header when switching to a new agent
            if current_executor != event.executor_id:
                if stream_line_open:
                    print()
                    stream_line_open = False
                print(f"---------- {event.executor_id} ----------")
                current_executor = event.executor_id
                stream_line_open = True
            if event.data:
                print(event.data.text, end="", flush=True)
        elif isinstance(event, RequestInfoEvent):
            if isinstance(event.data, HandoffUserInputRequest):
                pending_requests.append(event)
        elif isinstance(event, WorkflowStatusEvent):
            if event.state in {WorkflowRunState.IDLE_WITH_PENDING_REQUESTS} and stream_line_open:
                print()
                stream_line_open = False

    # Process scripted responses
    response_index = 1
    while pending_requests and response_index < len(scripted_responses):
        user_response = scripted_responses[response_index]
        print("---------- user ----------")
        print(user_response)

        responses = {req.request_id: user_response for req in pending_requests}
        pending_requests = []
        current_executor = None
        stream_line_open = False

        async for event in workflow.send_responses_streaming(responses):
            if isinstance(event, AgentRunUpdateEvent):
                # Print executor name header when switching to a new agent
                if current_executor != event.executor_id:
                    if stream_line_open:
                        print()
                        stream_line_open = False
                    print(f"---------- {event.executor_id} ----------")
                    current_executor = event.executor_id
                    stream_line_open = True
                if event.data:
                    print(event.data.text, end="", flush=True)
            elif isinstance(event, RequestInfoEvent):
                if isinstance(event.data, HandoffUserInputRequest):
                    pending_requests.append(event)
            elif isinstance(event, WorkflowStatusEvent):
                if (
                    event.state in {WorkflowRunState.IDLE_WITH_PENDING_REQUESTS, WorkflowRunState.IDLE}
                    and stream_line_open
                ):
                    print()
                    stream_line_open = False

        response_index += 1

    if stream_line_open:
        print()
    print()  # Final newline after conversation


async def main() -> None:
    print("=" * 60)
    print("Swarm / Handoff Pattern Comparison")
    print("=" * 60)
    print("AutoGen: Swarm with handoffs")
    print("Agent Framework: HandoffBuilder\n")
    await run_autogen()
    print()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
