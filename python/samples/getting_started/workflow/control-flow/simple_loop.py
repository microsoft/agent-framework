# Copyright (c) Microsoft. All rights reserved.

import asyncio
from enum import Enum

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatMessage,
    Executor,
    ExecutorCompletedEvent,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Sample: Simple Loop (with an Agent Judge)

What it does:
- Guesser performs a binary search; judge is an agent that returns ABOVE/BELOW/MATCHED.
- Demonstrates feedback loops in workflows with agent steps.
- The workflow completes when the correct number is guessed.

Prerequisites:
- Azure AI/ Azure OpenAI for `AzureChatClient` agent.
- Authentication via `azure-identity` — uses `AzureCliCredential()` (run `az login`).
"""


class NumberSignal(Enum):
    """Enum to represent number signals for the workflow."""

    # The target number is above the guess.
    ABOVE = "above"
    # The target number is below the guess.
    BELOW = "below"
    # The guess matches the target number.
    MATCHED = "matched"
    # Initial signal to start the guessing process.
    INIT = "init"


class GuessNumberExecutor(Executor):
    """An executor that guesses a number."""

    def __init__(self, bound: tuple[int, int], id: str | None = None):
        """Initialize the executor with a target number."""
        super().__init__(id=id or "guess_number")
        self._lower = bound[0]
        self._upper = bound[1]

    @handler
    async def guess_number(self, feedback: NumberSignal, ctx: WorkflowContext[int, str]) -> None:
        """Execute the task by guessing a number."""
        if feedback == NumberSignal.INIT:
            self._guess = (self._lower + self._upper) // 2
            await ctx.send_message(self._guess)
        elif feedback == NumberSignal.MATCHED:
            # The previous guess was correct.
            await ctx.yield_output(f"Guessed the number: {self._guess}")
        elif feedback == NumberSignal.ABOVE:
            # The previous guess was too low.
            # Update the lower bound to the previous guess.
            # Generate a new number that is between the new bounds.
            self._lower = self._guess + 1
            self._guess = (self._lower + self._upper) // 2
            await ctx.send_message(self._guess)
        else:
            # The previous guess was too high.
            # Update the upper bound to the previous guess.
            # Generate a new number that is between the new bounds.
            self._upper = self._guess - 1
            self._guess = (self._lower + self._upper) // 2
            await ctx.send_message(self._guess)


class SubmitToJudgeAgent(Executor):
    """Send the numeric guess to a judge agent which replies ABOVE/BELOW/MATCHED."""

    def __init__(self, judge_agent_id: str, target: int, id: str | None = None):
        super().__init__(id=id or "submit_to_judge")
        self._judge_agent_id = judge_agent_id
        self._target = target

    @handler
    async def submit(self, guess: int, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        prompt = (
            "You are a number judge. Given a target number and a guess, reply with exactly one token:"
            " 'MATCHED' if guess == target, 'ABOVE' if the target is above the guess,"
            " or 'BELOW' if the target is below.\n"
            f"Target: {self._target}\nGuess: {guess}\nResponse:"
        )
        await ctx.send_message(
            AgentExecutorRequest(messages=[ChatMessage(Role.USER, text=prompt)], should_respond=True),
            target_id=self._judge_agent_id,
        )


class ParseJudgeResponse(Executor):
    """Parse AgentExecutorResponse into NumberSignal for the loop."""

    @handler
    async def parse(self, response: AgentExecutorResponse, ctx: WorkflowContext[NumberSignal]) -> None:
        text = response.agent_run_response.text.strip().upper()
        if "MATCHED" in text:
            await ctx.send_message(NumberSignal.MATCHED)
        elif "ABOVE" in text and "BELOW" not in text:
            await ctx.send_message(NumberSignal.ABOVE)
        else:
            await ctx.send_message(NumberSignal.BELOW)


async def main():
    """Main function to run the workflow."""
    # Step 1: Create the executors.
    guess_number_executor = GuessNumberExecutor((1, 100))

    # Agent judge setup
    chat_client = AzureChatClient(credential=AzureCliCredential())
    judge_agent = AgentExecutor(
        chat_client.create_agent(
            instructions=(
                "You strictly respond with one of: MATCHED, ABOVE, BELOW based on the given target and guess."
            )
        ),
        id="judge_agent",
    )
    submit_to_judge = SubmitToJudgeAgent(judge_agent_id=judge_agent.id, target=30, id="submit_judge")
    parse_judge = ParseJudgeResponse(id="parse_judge")

    # Step 2: Build the workflow with the defined edges.
    # This time we are creating a loop in the workflow.
    workflow = (
        WorkflowBuilder()
        .add_edge(guess_number_executor, submit_to_judge)
        .add_edge(submit_to_judge, judge_agent)
        .add_edge(judge_agent, parse_judge)
        .add_edge(parse_judge, guess_number_executor)
        .set_start_executor(guess_number_executor)
        .build()
    )

    # Step 3: Run the workflow and print the events.
    iterations = 0
    async for event in workflow.run_stream(NumberSignal.INIT):
        if isinstance(event, ExecutorCompletedEvent) and event.executor_id == guess_number_executor.id:
            iterations += 1
        elif isinstance(event, WorkflowOutputEvent):
            print(f"Final result: {event.data}")
        print(f"Event: {event}")

    # This is essentially a binary search, so the number of iterations should be logarithmic.
    # The maximum number of iterations is [log2(range size)]. For a range of 1 to 100, this is log2(100) which is 7.
    # Subtract because the last round is the MATCHED event.
    print(f"Guessed {iterations - 1} times.")


if __name__ == "__main__":
    asyncio.run(main())
