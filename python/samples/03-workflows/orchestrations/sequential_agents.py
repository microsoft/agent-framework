# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import cast

from agent_framework import Agent, AgentResponse, Message
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Sequential workflow (agent-focused API) with shared conversation context

Build a high-level sequential workflow using SequentialBuilder and two domain agents.
The shared conversation flows through each participant. Each agent appends its
assistant message to the context. The sample prints the original user message plus
the visible outputs from both agents.

Note on internal adapters:
- Sequential orchestration includes small adapter nodes for input normalization
  ("input-conversation"), agent-response conversion ("to-conversation:<participant>"),
  and completion ("complete"). These may appear as ExecutorInvoke/Completed events in
  the stream—similar to how concurrent orchestration includes a dispatcher/aggregator.
  You can safely ignore them when focusing on agent progress.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL must be set to your Azure OpenAI model deployment name.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
"""


async def main() -> None:
    # 1) Create agents
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    writer = Agent(
        client=client,
        instructions=("You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."),
        name="writer",
    )

    reviewer = Agent(
        client=client,
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        name="reviewer",
    )

    # 2) Build sequential workflow: writer -> reviewer
    workflow = SequentialBuilder(participants=[writer, reviewer], output_from="all").build()

    # 3) Run and collect outputs
    prompt = "Write a tagline for a budget-friendly eBike."
    result = await workflow.run(prompt)
    conversation = [Message(role="user", contents=[prompt])]
    for output in result.get_outputs():
        response = cast(AgentResponse, output)
        conversation.extend(response.messages)

    if conversation:
        print("===== Final Conversation =====")
        for i, msg in enumerate(conversation, start=1):
            name = msg.author_name or ("assistant" if msg.role == "assistant" else "user")
            print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")

    """
    Sample Output:

    ===== Final Conversation =====
    ------------------------------------------------------------
    01 [user]
    Write a tagline for a budget-friendly eBike.
    ------------------------------------------------------------
    02 [writer]
    Ride farther, spend less—your affordable eBike adventure starts here.
    ------------------------------------------------------------
    03 [reviewer]
    This tagline clearly communicates affordability and the benefit of extended travel, making it
    appealing to budget-conscious consumers. It has a friendly and motivating tone, though it could
    be slightly shorter for more punch. Overall, a strong and effective suggestion!
    """


if __name__ == "__main__":
    asyncio.run(main())
