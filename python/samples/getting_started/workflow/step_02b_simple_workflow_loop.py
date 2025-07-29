# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys
from enum import Enum

from agent_framework.workflow import (
    Executor,
    ExecutorCompleteEvent,
    ExecutorContext,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    output_message_types,
)

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


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


@output_message_types(int)
class GuessNumberExecutor(Executor[NumberSignal]):
    """An executor that guesses a number."""

    def __init__(self, bound: tuple[int, int], id: str | None = None):
        """Initialize the executor with a target number."""
        super().__init__(id=id)
        self._lower = bound[0]
        self._upper = bound[1]

    @override
    async def _execute(self, data: NumberSignal, ctx: ExecutorContext) -> int:
        """Execute the task by guessing a number."""
        if data == NumberSignal.INIT:
            self._guess = (self._lower + self._upper) // 2
            await ctx.send_message(self._guess)
            return self._guess

        if data == NumberSignal.MATCHED:
            # The previous guess was correct.
            await ctx.add_event(WorkflowCompletedEvent(f"Guessed the number: {self._guess}"))
            return self._guess

        if data == NumberSignal.ABOVE:
            # The previous guess was too low.
            # Update the lower bound to the previous guess.
            # Generate a new number that is between the new bounds.
            self._lower = self._guess + 1
            self._guess = (self._lower + self._upper) // 2
            await ctx.send_message(self._guess)
            return self._guess

        # The previous guess was too high.
        # Update the upper bound to the previous guess.
        # Generate a new number that is between the new bounds.
        self._upper = self._guess - 1
        self._guess = (self._lower + self._upper) // 2
        await ctx.send_message(self._guess)
        return self._guess


@output_message_types(NumberSignal)
class JudgeExecutor(Executor[int]):
    """An executor that judges the guessed number."""

    def __init__(self, target: int, id: str | None = None):
        """Initialize the executor with a target number."""
        super().__init__(id=id)
        self._target = target

    @override
    async def _execute(self, data: int, ctx: ExecutorContext) -> NumberSignal:
        """Judge the guessed number."""
        if data == self._target:
            result = NumberSignal.MATCHED
        elif data < self._target:
            result = NumberSignal.ABOVE
        else:
            result = NumberSignal.BELOW

        await ctx.send_message(result)
        return result


async def main():
    """Main function to run the workflow."""
    guess_number_executor = GuessNumberExecutor((1, 100))
    judge_executor = JudgeExecutor(30)

    workflow = (
        WorkflowBuilder()
        .add_loop(guess_number_executor, judge_executor)
        .set_start_executor(guess_number_executor)
        .build()
    )

    iterations = 0
    async for event in workflow.run_stream(NumberSignal.INIT):
        if isinstance(event, ExecutorCompleteEvent) and event.executor_id == guess_number_executor.id:
            iterations += 1
        print(f"Event: {event}")

    # This is essentially a binary search, so the number of iterations should be logarithmic.
    # The maximum number of iterations is [log2(range size)]. For a range of 1 to 100, this is log2(100) which is 7.
    # Subtract because the last round is the MATCHED event.
    print(f"Guessed {iterations - 1} times.")


if __name__ == "__main__":
    asyncio.run(main())
