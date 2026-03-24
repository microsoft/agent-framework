# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import cast

from agent_framework import (
    Agent,
    AgentResponseUpdate,
    Message,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import GroupChatBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Group Chat with Agent-Based Manager

What it does:
- Demonstrates the new set_manager() API for agent-based coordination
- Manager is a full Agent with access to tools, context, and observability
- Coordinates a researcher and writer agent to solve tasks collaboratively

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Azure OpenAI configured for AzureOpenAIResponsesClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
"""

ORCHESTRATOR_AGENT_INSTRUCTIONS = """
You coordinate a team conversation to solve the user's task.

Guidelines:
- Start with Researcher to gather information
- Then have Writer synthesize the final answer
- Only finish after both have contributed meaningfully
"""


async def main() -> None:
    # Create a Responses client using Azure OpenAI and Azure CLI credentials for all agents
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    # Orchestrator agent that manages the conversation
    # Note: This agent (and the underlying chat client) must support structured outputs.
    # The group chat workflow relies on this to parse the orchestrator's decisions.
    # `response_format` is set internally by the GroupChat workflow when the agent is invoked.
    orchestrator_agent = Agent(
        name="Orchestrator",
        description="Coordinates multi-agent collaboration by selecting speakers",
        instructions=ORCHESTRATOR_AGENT_INSTRUCTIONS,
        client=client,
    )

    # Participant agents
    researcher = Agent(
        name="Researcher",
        description="Collects relevant background information",
        instructions="Gather concise facts that help a teammate answer the question.",
        client=client,
    )

    writer = Agent(
        name="Writer",
        description="Synthesizes polished answers from gathered information",
        instructions="Compose clear and structured answers using any notes provided.",
        client=client,
    )

    # Build the group chat workflow
    # termination_condition: stop after 4 assistant messages
    # (The agent orchestrator will intelligently decide when to end before this limit but just in case)
    # intermediate_outputs=True: Enable intermediate outputs to observe the conversation as it unfolds
    # (Intermediate outputs will be emitted as WorkflowOutputEvent events)
    workflow = (
        GroupChatBuilder(
            participants=[researcher, writer],
            termination_condition=lambda messages: sum(1 for msg in messages if msg.role == "assistant") >= 4,
            intermediate_outputs=True,
            orchestrator_agent=orchestrator_agent,
        )
        # Set a hard termination condition: stop after 4 assistant messages
        # The agent orchestrator will intelligently decide when to end before this limit but just in case
        .with_termination_condition(lambda messages: sum(1 for msg in messages if msg.role == "assistant") >= 4)
        .build()
    )

    task = "What are the key benefits of using async/await in Python? Provide a concise summary."

    print("\nStarting Group Chat with Agent-Based Manager...\n")
    print(f"TASK: {task}\n")
    print("=" * 80)

    # Keep track of the last response to format output nicely in streaming mode
    last_response_id: str | None = None
    async for event in workflow.run(task, stream=True):
        if event.type == "output":
            data = event.data
            if isinstance(data, AgentResponseUpdate):
                rid = data.response_id
                if rid != last_response_id:
                    if last_response_id is not None:
                        print("\n")
                    print(f"{data.author_name}:", end=" ", flush=True)
                    last_response_id = rid
                print(data.text, end="", flush=True)
            elif event.type == "output":
                # The output of the group chat workflow is a collection of chat messages from all participants
                outputs = cast(list[Message], event.data)
                print("\n" + "=" * 80)
                print("\nFinal Conversation Transcript:\n")
                for message in outputs:
                    print(f"{message.author_name or message.role}: {message.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
