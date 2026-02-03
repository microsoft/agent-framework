# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    ChatAgent,
    ChatMessage,
    Executor,
    Role,
    SequentialBuilder,
    Workflow,
    WorkflowContext,
    handler,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Sequential workflow with participant factories

This sample demonstrates how to create a sequential workflow with participant factories.

Using participant factories allows you to set up proper state isolation between workflow
instances created by the same builder. This is particularly useful when you need to handle
requests or tasks in parallel with stateful participants.

In this example, we create a sequential workflow with two participants: an accumulator
and a content producer. The accumulator is stateful and maintains a list of all messages it has
received. Context is maintained across runs of the same workflow instance but not across different
workflow instances.
"""


class Accumulate(Executor):
    """Simple accumulator.

    Accumulates all messages from the conversation and prints them out.
    """

    def __init__(self, id: str):
        super().__init__(id)
        # Some internal state to accumulate messages
        self._accumulated: list[str] = []

    @handler
    async def accumulate(self, conversation: list[ChatMessage], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        self._accumulated.extend([msg.text for msg in conversation])
        print(f"Number of queries received so far: {len(self._accumulated)}")
        await ctx.send_message(conversation)


def create_agent() -> ChatAgent:
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions="Produce a concise paragraph answering the user's request.",
        name="ContentProducer",
    )


async def run_workflow(workflow: Workflow, query: str) -> None:
    events = await workflow.run(query)
    outputs = events.get_outputs()

    if outputs:
        messages: list[ChatMessage] = outputs[0]
        for message in messages:
            name = message.author_name or ("assistant" if message.role == Role.ASSISTANT else "user")
            print(f"{name}: {message.text}")
    else:
        raise RuntimeError("No outputs received from the workflow.")


async def main() -> None:
    # 1) Create a builder with participant factories
    builder = SequentialBuilder().register_participants([
        lambda: Accumulate("accumulator"),
        create_agent,
    ])
    # 2) Build workflow_a
    workflow_a = builder.build()

    # 3) Run workflow_a
    # Context is maintained across runs
    print("=== First Run on workflow_a ===")
    await run_workflow(workflow_a, "Why is the sky blue?")
    print("\n=== Second Run on workflow_a ===")
    await run_workflow(workflow_a, "Repeat my previous question.")

    # 4) Build workflow_b
    # This will create a new instance of the accumulator and content producer
    # using the same workflow builder
    workflow_b = builder.build()

    # 5) Run workflow_b
    # Context is not maintained across instances
    print("\n=== First Run on workflow_b ===")
    await run_workflow(workflow_b, "Repeat my previous question.")

    """
    Sample Output:

    === First Run on workflow_a ===
    Number of queries received so far: 1
    user: Why is the sky blue?
    ContentProducer: The sky appears blue due to a phenomenon called Rayleigh scattering.
                     When sunlight enters the Earth's atmosphere, it collides with gases
                     and particles, scattering shorter wavelengths of light (blue and violet)
                     more than the longer wavelengths (red and yellow). Although violet light
                     is scattered even more than blue, our eyes are more sensitive to blue
                     light, and some violet light is absorbed by the ozone layer. As a result,
                     we perceive the sky as predominantly blue during the day.

    === Second Run on workflow_a ===
    Number of queries received so far: 2
    user: Repeat my previous question.
    ContentProducer: Why is the sky blue?

    === First Run on workflow_b ===
    Number of queries received so far: 1
    user: Repeat my previous question.
    ContentProducer: I'm sorry, but I can't repeat your previous question as I don't have
                     access to your past queries. However, feel free to ask anything again,
                     and I'll be happy to help!
    """


if __name__ == "__main__":
    asyncio.run(main())
