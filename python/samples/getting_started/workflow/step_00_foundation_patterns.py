# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework.workflow import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler

"""
The following sample demonstrates the foundation patterns that the workflow framework supports.
These patterns include:
- Single connection
- Single connection with condition
- Fan-out and fan-in connections
- Conditional fan-out connections
- Partitioning fan-out connections

The samples here use numbers and simple arithmetic operations to demonstrate the patterns.
"""


class AddOneExecutor(Executor):
    """An executor that processes a number by adding one."""

    @handler
    async def add_one(self, number: int, ctx: WorkflowContext[int]) -> None:
        """Execute the task by adding one to the input number."""
        result = number + 1

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)

        print("Adding one to the number:", number, "Result:", result)


class MultiplyByTwoExecutor(Executor):
    """An executor that processes a number by multiplying it by two."""

    @handler
    async def multiply_by_two(self, number: int, ctx: WorkflowContext[int]) -> None:
        """Execute the task by multiplying the input number by two."""
        result = number * 2

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)

        print("Multiplying the number by two:", number, "Result:", result)


class DivideByTwoExecutor(Executor):
    """An executor that processes a number by dividing it by two."""

    @handler
    async def divide_by_two(self, number: int, ctx: WorkflowContext[float]) -> None:
        """Execute the task by dividing the input number by two."""
        result = number / 2

        # Send the result with a workflow completion event.
        await ctx.send_message(result)

        print("Dividing the number by two:", number, "Result:", result)


class AggregateResultExecutor(Executor):
    """An executor that receives results and prints them."""

    @handler
    async def aggregate_results(self, results: Any, ctx: WorkflowContext[None]) -> None:
        """Print whatever results are received."""
        print("Aggregating results:", results)


async def single_edge():
    """A sample to demonstrate a single directed connection between two executors.

    Three executors are connected in a sequence: AddOneExecutor -> AddOneExecutor -> AggregateResultExecutor.

    Expected output:
        Adding one to the number: 1 Result: 2
        Adding one to the number: 2 Result: 3
        Aggregating results: 3
    """
    add_one_executor_a = AddOneExecutor()
    add_one_executor_b = AddOneExecutor()
    aggregate_result_executor = AggregateResultExecutor()

    workflow = (
        WorkflowBuilder()
        .add_edge(add_one_executor_a, add_one_executor_b)
        .add_edge(add_one_executor_b, aggregate_result_executor)
        .set_start_executor(add_one_executor_a)
        .build()
    )

    await workflow.run(1)


async def single_edge_with_condition():
    """A sample to demonstrate a single directed connection with a condition.

    Three executors are connected: AddOneExecutor -> AddOneExecutor, AggregateResultExecutor.
    The AddOneExecutor will loop back to itself until the number reaches 10, then it will start
    sending the result to AggregateResultExecutor when the number is greater than 8. The workflow
    stops when the number reaches 11.

    Expected output:
        Adding one to the number: 1 Result: 2
        Adding one to the number: 2 Result: 3
        Adding one to the number: 3 Result: 4
        Adding one to the number: 4 Result: 5
        Adding one to the number: 5 Result: 6
        Adding one to the number: 6 Result: 7
        Adding one to the number: 7 Result: 8
        Adding one to the number: 8 Result: 9
        Adding one to the number: 9 Result: 10
        Aggregating results: 9
        Adding one to the number: 10 Result: 11
        Aggregating results: 10
        Aggregating results: 11
    """
    add_one_executor_a = AddOneExecutor()
    aggregate_result_executor = AggregateResultExecutor()

    workflow = (
        WorkflowBuilder()
        .add_edge(add_one_executor_a, add_one_executor_a, condition=lambda x: x < 11)
        .add_edge(add_one_executor_a, aggregate_result_executor, condition=lambda x: x > 8)
        .set_start_executor(add_one_executor_a)
        .build()
    )

    await workflow.run(1)


async def fan_out_fan_in_edge_group():
    """A sample to demonstrate a fan-out and fan-in connection between executors.

    Four executors are connected in a fan-out and fan-in pattern:
    AddOneExecutor -> MultiplyByTwoExecutor, DivideByTwoExecutor -> AggregateResultExecutor.
    The AddOneExecutor sends its output to both MultiplyByTwoExecutor and DivideByTwoExecutor,
    and both of these executors send their results to AggregateResultExecutor.

    The target of the fan-in connection will wait for all the results from the sources before proceeding.

    Expected output:
        Adding one to the number: 1 Result: 2
        Multiplying the number by two: 2 Result: 4
        Dividing the number by two: 2 Result: 1.0
        Aggregating results: [4, 1.0]
    """
    add_one_executor = AddOneExecutor()
    multiply_by_two_executor = MultiplyByTwoExecutor()
    divide_by_two_executor = DivideByTwoExecutor()
    aggregate_result_executor = AggregateResultExecutor()

    workflow = (
        WorkflowBuilder()
        .add_fan_out_edges(add_one_executor, [multiply_by_two_executor, divide_by_two_executor])
        .add_fan_in_edges([multiply_by_two_executor, divide_by_two_executor], aggregate_result_executor)
        .set_start_executor(add_one_executor)
        .build()
    )

    await workflow.run(1)


async def switch_case_edge_group():
    """A sample to demonstrate a switch-case connection.

    Four executors are connected in a switch-case pattern:
    AddOneExecutor -> AddOneExecutor, MultiplyByTwoExecutor, DivideByTwoExecutor -> AggregateResultExecutor.

    The message from AddOneExecutor will be evaluated against the conditions one by one, and the first condition
    that evaluates to True will determine the target executors. If no conditions match, the message will be sent
    to the last targets.

    This pattern resembles a switch-case statement with a default case where the first matching case is executed.

    Expected output:
        Adding one to the number: 1 Result: 2
        Adding one to the number: 2 Result: 3
        Adding one to the number: 3 Result: 4
        Adding one to the number: 4 Result: 5
        Adding one to the number: 5 Result: 6
        Adding one to the number: 6 Result: 7
        Adding one to the number: 7 Result: 8
        Adding one to the number: 8 Result: 9
        Adding one to the number: 9 Result: 10
        Adding one to the number: 10 Result: 11
        Multiplying the number by two: 11 Result: 22
    """
    add_one_executor = AddOneExecutor()
    multiply_by_two_executor = MultiplyByTwoExecutor()
    divide_by_two_executor = DivideByTwoExecutor()
    aggregate_result_executor = AggregateResultExecutor()

    workflow = (
        WorkflowBuilder()
        .set_start_executor(add_one_executor)
        .add_switch_case_edge_group(
            source=add_one_executor,
            cases=[
                # Loop back to the add_one_executor if the number is less than 11
                Case(condition=lambda x: x < 11, target=add_one_executor),
                # multiply_by_two_executor when the number is larger than or equal to 11 and even.
                Case(condition=lambda x: x % 2 == 0, target=multiply_by_two_executor),
                # Otherwise, send to the divide_by_two_executor.
                Default(target=divide_by_two_executor),
            ],
        )
        .add_fan_in_edges([multiply_by_two_executor, divide_by_two_executor], aggregate_result_executor)
        .build()
    )

    await workflow.run(1)


async def multi_selection_edge_group():
    """A sample to demonstrate a multi-selection edge connection.

    Four executors are connected in a multi-selection edge pattern:
    AddOneExecutor -> AddOneExecutor, MultiplyByTwoExecutor, DivideByTwoExecutor -> AggregateResultExecutor.

    The AddOneExecutor sends its output to one or more executors based on the partitioning function.

    Expected output:
        Adding one to the number: 1 Result: 2
        Adding one to the number: 2 Result: 3
        Adding one to the number: 3 Result: 4
        Adding one to the number: 4 Result: 5
        Adding one to the number: 5 Result: 6
        Adding one to the number: 6 Result: 7
        Adding one to the number: 7 Result: 8
        Adding one to the number: 8 Result: 9
        Adding one to the number: 9 Result: 10
        Adding one to the number: 10 Result: 11
        Adding one to the number: 11 Result: 12
        Adding one to the number: 12 Result: 13
        Dividing the number by two: 12 Result: 6.0
        Multiplying the number by two: 13 Result: 26
        Aggregating results: [26, 6.0]
    """
    add_one_executor = AddOneExecutor()
    multiply_by_two_executor = MultiplyByTwoExecutor()
    divide_by_two_executor = DivideByTwoExecutor()
    aggregate_result_executor = AggregateResultExecutor()

    def selection_func(number: int, target_ids: list[str]) -> list[str]:
        """Selection function to determine which executor to send the number to."""
        if number < 12:
            # Loop back to the add_one_executor if the number is less than 12
            return [add_one_executor.id]

        if number % 2 == 0:
            # Send it to the add_one_executor to add one more time and the
            # divide_by_two_executor to divide the result by two.
            return [add_one_executor.id, divide_by_two_executor.id]

        # Otherwise, send it to the multiply_by_two_executor to multiply the result by two.
        return [multiply_by_two_executor.id]

    workflow = (
        WorkflowBuilder()
        .set_start_executor(add_one_executor)
        .add_multi_selection_edge_group(
            add_one_executor,
            [add_one_executor, multiply_by_two_executor, divide_by_two_executor],
            selection_func=selection_func,
        )
        .add_fan_in_edges([multiply_by_two_executor, divide_by_two_executor], aggregate_result_executor)
        .build()
    )

    await workflow.run(1)


async def main():
    """Main function to run the workflows."""
    print("**Running single connection workflow**")
    await single_edge()
    print("**Running single connection with condition workflow**")
    await single_edge_with_condition()
    print("**Running fan-out and fan-in connection workflow**")
    await fan_out_fan_in_edge_group()
    print("**Running conditional fan-out connection workflow**")
    await switch_case_edge_group()
    print("**Running multi-selection edge group workflow**")
    await multi_selection_edge_group()


if __name__ == "__main__":
    asyncio.run(main())
