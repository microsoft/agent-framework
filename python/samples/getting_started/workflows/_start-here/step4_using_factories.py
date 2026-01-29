# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    AgentResponse,
    ChatAgent,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    executor,
    handler,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Step 4: Using Factories to Define Executors and Agents

What this example shows
- Defining custom executors using both class-based and function-based approaches.
- Registering executor and agent factories with WorkflowBuilder for lazy instantiation.
- Building a simple workflow that transforms input text through multiple steps.

Benefits of using factories
- Decouples executor and agent creation from workflow definition.
- Isolated instances are created for workflow builder build, allowing for cleaner state management
  and handling parallel workflow runs.

It is recommended to use factories when defining executors and agents for production workflows.

Prerequisites
- No external services required.
"""


class UpperCase(Executor):
    def __init__(self, id: str):
        super().__init__(id=id)

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Convert the input to uppercase and forward it to the next node."""
        result = text.upper()

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)


@executor(id="reverse_text_executor")
async def reverse_text(text: str, ctx: WorkflowContext[str]) -> None:
    """Reverse the input string and send it downstream."""
    result = text[::-1]

    # Send the result to the next executor in the workflow.
    await ctx.send_message(result)


def create_agent() -> ChatAgent:
    """Factory function to create a Writer agent."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=("You decode messages. Try to reconstruct the original message."),
        name="decoder",
    )


async def main():
    """Build and run a simple 2-step workflow using the fluent builder API."""
    # Build the workflow using a fluent pattern:
    # 1) register_executor(factory, name) registers an executor factory
    # 2) register_agent(factory, name) registers an agent factory
    # 3) add_chain([node_names]) adds a sequence of nodes to the workflow
    # 4) set_start_executor(node) declares the entry point
    # 5) build() finalizes and returns an immutable Workflow object
    workflow = (
        WorkflowBuilder()
        .register_executor(lambda: UpperCase(id="upper_case_executor"), name="UpperCase")
        .register_executor(lambda: reverse_text, name="ReverseText")
        .register_agent(create_agent, name="DecoderAgent", output_response=True)
        .add_chain(["UpperCase", "ReverseText", "DecoderAgent"])
        .set_start_executor("UpperCase")
        .build()
    )

    output: AgentResponse | None = None
    async for event in workflow.run_stream("hello world"):
        if isinstance(event, WorkflowOutputEvent) and isinstance(event.data, AgentResponse):
            output = event.data

    if output:
        print(f"Decoded output: {output.text}")
    else:
        print("No output received.")

    """
    Sample Output:

    HELLO WORLD
    """


if __name__ == "__main__":
    asyncio.run(main())
