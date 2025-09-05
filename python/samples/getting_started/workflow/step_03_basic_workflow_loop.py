# Copyright (c) Microsoft. All rights reserved.

import asyncio
from enum import Enum

from agent_framework.workflow import (
    Executor,
    ExecutorCompletedEvent,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

"""
The following sample demonstrates a basic workflow with two executors
where one executor guesses a number and the other executor judges the
guess iteratively.
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
        super().__init__(id=id)
        self._lower = bound[0]
        self._upper = bound[1]

    @handler
    async def guess_number(self, feedback: NumberSignal, ctx: WorkflowContext[int]) -> None:
        """Execute the task by guessing a number."""
        if feedback == NumberSignal.INIT:
            self._guess = (self._lower + self._upper) // 2
            await ctx.send_message(self._guess)
        elif feedback == NumberSignal.MATCHED:
            # The previous guess was correct.
            await ctx.add_event(WorkflowCompletedEvent(f"Guessed the number: {self._guess}"))
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


class JudgeExecutor(Executor):
    """An executor that judges the guessed number."""

    def __init__(self, target: int, id: str | None = None):
        """Initialize the executor with a target number."""
        super().__init__(id=id)
        self._target = target

    @handler
    async def judge(self, number: int, ctx: WorkflowContext[NumberSignal]) -> None:
        """Judge the guessed number."""
        if number == self._target:
            result = NumberSignal.MATCHED
        elif number < self._target:
            result = NumberSignal.ABOVE
        else:
            result = NumberSignal.BELOW

        await ctx.send_message(result)


async def main():
    """Main function to run the workflow."""
    # Step 1: Create the executors.
    guess_number_executor = GuessNumberExecutor((1, 100))
    judge_executor = JudgeExecutor(30)

    # Step 2: Build the workflow with the defined edges.
    # This time we are creating a loop in the workflow.
    workflow = (
        WorkflowBuilder()
        .add_edge(guess_number_executor, judge_executor)
        .add_edge(judge_executor, guess_number_executor)
        .set_start_executor(guess_number_executor)
        .build()
    )

    # Step 3: Run the workflow and print the events.
    iterations = 0
    async for event in workflow.run_stream(NumberSignal.INIT):
        if isinstance(event, ExecutorCompletedEvent) and event.executor_id == guess_number_executor.id:
            iterations += 1
        print(f"Event: {event}")

    # This is essentially a binary search, so the number of iterations should be logarithmic.
    # The maximum number of iterations is [log2(range size)]. For a range of 1 to 100, this is log2(100) which is 7.
    # Subtract because the last round is the MATCHED event.
    print(f"Guessed {iterations - 1} times.")


if __name__ == "__main__":
    asyncio.run(main())
