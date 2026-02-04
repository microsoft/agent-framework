# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Role, SequentialBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Build a sequential workflow orchestration and wrap it as an agent.

The script assembles a sequential conversation flow with `SequentialBuilder`, then
invokes the entire orchestration through the `workflow.as_agent(...)` interface so
other coordinators can reuse the chain as a single participant.

Note on internal adapters:
- Sequential orchestration includes small adapter nodes for input normalization
  ("input-conversation"), agent-response conversion ("to-conversation:<participant>"),
  and completion ("complete"). These may appear as ExecutorInvoke/Completed events in
  the stream—similar to how concurrent orchestration includes a dispatcher/aggregator.
  You can safely ignore them when focusing on agent progress.

Prerequisites:
- Azure OpenAI access configured for AzureOpenAIChatClient (use az login + env vars)
"""


async def main() -> None:
    # 1) Create agents
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    writer = chat_client.as_agent(
        instructions=("You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."),
        name="writer",
    )

    reviewer = chat_client.as_agent(
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        name="reviewer",
    )

    # 2) Build sequential workflow: writer -> reviewer
    workflow = SequentialBuilder().participants([writer, reviewer]).build()

    # 3) Treat the workflow itself as an agent for follow-up invocations
    agent = workflow.as_agent(name="SequentialWorkflowAgent")
    prompt = "Write a tagline for a budget-friendly eBike."
    agent_response = await agent.run(prompt)

    if agent_response.messages:
        print("\n===== Conversation =====")
        for i, msg in enumerate(agent_response.messages, start=1):
            role_value = getattr(msg.role, "value", msg.role)
            normalized_role = str(role_value).lower() if role_value is not None else "assistant"
            name = msg.author_name or ("assistant" if normalized_role == Role.ASSISTANT.value else "user")
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

    ===== as_agent() Conversation =====
    ------------------------------------------------------------
    01 [writer]
    Go electric, save big—your affordable ride awaits!
    ------------------------------------------------------------
    02 [reviewer]
    Catchy and straightforward! The tagline clearly emphasizes both the electric aspect and the affordability of the
    eBike. It's inviting and actionable. For even more impact, consider making it slightly shorter:
    "Go electric, save big." Overall, this is an effective and appealing suggestion for a budget-friendly eBike.
    """


if __name__ == "__main__":
    asyncio.run(main())
