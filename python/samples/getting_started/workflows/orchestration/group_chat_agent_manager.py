# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    GroupChatBuilder,
    Role,
    WorkflowOutputEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Group Chat with Agent-Based Manager

What it does:
- Demonstrates the new set_manager() API for agent-based coordination
- Manager is a full ChatAgent with access to tools, context, and observability
- Coordinates a researcher and writer agent to solve tasks collaboratively

Prerequisites:
- OpenAI environment variables configured for OpenAIChatClient
"""

ORCHESTRATOR_AGENT_INSTRUCTIONS = """
You coordinate a team conversation to solve the user's task.

Guidelines:
- Start with Researcher to gather information
- Then have Writer synthesize the final answer
- Only finish after both have contributed meaningfully
"""


async def main() -> None:
    # Create a chat client using Azure OpenAI and Azure CLI credentials for all agents
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Orchestrator agent that manages the conversation
    # Note: This agent (and the underlying chat client) must support structured outputs.
    # The group chat workflow relies on this to parse the orchestrator's decisions.
    # `response_format` is set internally by the GroupChat workflow when the agent is invoked.
    orchestrator_agent = ChatAgent(
        name="Orchestrator",
        description="Coordinates multi-agent collaboration by selecting speakers",
        instructions=ORCHESTRATOR_AGENT_INSTRUCTIONS,
        chat_client=chat_client,
    )

    # Participant agents
    researcher = ChatAgent(
        name="Researcher",
        description="Collects relevant background information",
        instructions="Gather concise facts that help a teammate answer the question.",
        chat_client=chat_client,
    )

    writer = ChatAgent(
        name="Writer",
        description="Synthesizes polished answers from gathered information",
        instructions="Compose clear and structured answers using any notes provided.",
        chat_client=chat_client,
    )

    # Build the group chat workflow
    workflow = (
        GroupChatBuilder()
        .with_orchestrator(agent=orchestrator_agent)
        .participants([researcher, writer])
        # Set a hard termination condition: stop after 4 assistant messages
        # The agent orchestrator will intelligently decide when to end before this limit but just in case
        .with_termination_condition(lambda messages: sum(1 for msg in messages if msg.role == Role.ASSISTANT) >= 4)
        .build()
    )

    task = "What are the key benefits of using async/await in Python? Provide a concise summary."

    print("\nStarting Group Chat with Agent-Based Manager...\n")
    print(f"TASK: {task}\n")
    print("=" * 80)

    # Keep track of the last executor to format output nicely in streaming mode
    last_executor_id: str | None = None
    output_event: WorkflowOutputEvent | None = None
    async for event in workflow.run_stream(task):
        if isinstance(event, AgentRunUpdateEvent):
            eid = event.executor_id
            if eid != last_executor_id:
                if last_executor_id is not None:
                    print("\n")
                print(f"{eid}:", end=" ", flush=True)
                last_executor_id = eid
            print(event.data, end="", flush=True)
        elif isinstance(event, WorkflowOutputEvent):
            output_event = event

    # The output of the workflow is the full list of messages exchanged
    if output_event:
        if not isinstance(output_event.data, list) or not all(
            isinstance(msg, ChatMessage)
            for msg in output_event.data  # type: ignore
        ):
            raise RuntimeError("Unexpected output event data format.")
        print("\n" + "=" * 80)
        print("\nFINAL OUTPUT (The conversation history)\n")
        for msg in output_event.data:  # type: ignore
            assert isinstance(msg, ChatMessage)
            print(f"{msg.author_name or msg.role}: {msg.text}\n")
    else:
        raise RuntimeError("Workflow did not produce a final output event.")


if __name__ == "__main__":
    asyncio.run(main())
