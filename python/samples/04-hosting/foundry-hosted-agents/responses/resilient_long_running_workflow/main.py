# Copyright (c) Microsoft. All rights reserved.

"""Host a three-executor workflow that extracts and counts down a target.

The start executor asks a Foundry-backed agent to extract a positive integer
from the incoming message. The countdown executor repeatedly decrements that
integer and sends it back to itself. At zero, it sends a completion message to
the terminal executor, which yields the workflow output.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name.
"""

import asyncio
import os

from agent_framework import Agent, Executor, Message, WorkflowBuilder, WorkflowContext, executor, handler
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing_extensions import Never

load_dotenv()


class CounterTarget(BaseModel):
    """The counter target extracted from the user's message."""

    target: int | None = Field(
        description="The positive integer to count down from, or null when no valid target was provided."
    )


class StartExecutor(Executor):
    """Extract a valid counter target and start the countdown."""

    def __init__(self, agent: Agent, id: str = "start") -> None:
        super().__init__(id=id)
        self._agent = agent

    @handler
    async def extract_target(self, messages: list[Message], ctx: WorkflowContext[int, str]) -> None:
        """Ask the model for a target and forward valid positive integers."""
        response = await self._agent.run(messages, options={"response_format": CounterTarget})
        extraction = response.value
        if not isinstance(extraction, CounterTarget) or extraction.target is None or extraction.target <= 0:
            await ctx.yield_output("The message must contain a positive integer counter target.")
            return

        await ctx.send_message(extraction.target)


class CountdownExecutor(Executor):
    def __init__(self, id: str = "countdown") -> None:
        super().__init__(id=id)

    @handler
    async def countdown(self, target: int, ctx: WorkflowContext[int | str, str]) -> None:
        """Decrement the target through a self-loop, then signal completion."""
        if target <= 0:
            await ctx.send_message("Countdown complete.", target_id="complete")
            return

        await asyncio.sleep(1)  # Simulate a long-running operation
        await ctx.yield_output(str(target))
        await ctx.send_message(target - 1, target_id=self.id)


@executor(id="complete")
async def complete(message: str, ctx: WorkflowContext[Never, str]) -> None:
    """Yield the workflow's completion output."""
    await ctx.yield_output(message)


def build_workflow():
    """Build the target extraction, countdown, and completion workflow."""
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )
    target_agent = Agent(
        client=client,
        name="counter_target_extractor",
        instructions=(
            "Extract the counter target requested by the user. Return the target only when it is a positive integer. "
            "Return null for zero, negative numbers, fractions, or messages without a clear counter target."
        ),
    )
    start = StartExecutor(target_agent)
    countdown = CountdownExecutor()

    return (
        WorkflowBuilder(start_executor=start, output_from="all")
        .add_edge(start, countdown)
        .add_edge(countdown, countdown)
        .add_edge(countdown, complete)
        .build()
    )


def main() -> None:
    """Run the workflow as a durable Responses API host."""
    print(f"PID: {os.getpid()}")  # lets crash-recovery testing find and kill this process
    workflow_agent = build_workflow().as_agent(name="countdown-workflow")
    server = ResponsesHostServer(
        workflow_agent,
        options=ResponsesServerOptions(resilient_background=True),
        log_level="DEBUG",
    )
    server.run()


if __name__ == "__main__":
    main()
