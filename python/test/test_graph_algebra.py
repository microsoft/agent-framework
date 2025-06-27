# Copyright (c) Microsoft. All rights reserved.
from __future__ import annotations

from python.test.test_utils import Assertions

from agent_framework.graph import Executor, GraphAlgebra, If
from agent_framework.graph._graph_low import LogTracer


def create_test_graph():
    """A sample function to demonstrate the usage of GraphAlgebra."""
    def int_str_action(input: int) -> str:
        return f"s({input // 2})"

    def str_int_action(input: str) -> int:
        try:
            return int(input[2:-1]) + 1
        except ValueError:
            return 0

    def is_nonnegative_even(input: int) -> bool:
        return input >= 0 and input % 2 == 0

    def is_nonnegative_odd(input: int) -> bool:
        return input > 0 and input % 2 != 0

    def is_negative(input: int) -> bool:
        return input < 0

    def create_error_message(input: int) -> str:
        return f"Error: {input} is negative"

    def create_result_message(input: int) -> str:
        return f"Result: {input}"

    def output_action(input: str) -> str:
        return input

    START = GraphAlgebra[int].start(int_str_action)

    STEP2 = START + str_int_action
    # This syntax for loops is a bit awkward.
    _ = STEP2 + (If(is_nonnegative_even) << START)

    CREATE_RESULT = STEP2 + (If(is_nonnegative_odd) << create_result_message)
    CREATE_ERROR = STEP2 + (If(is_negative) << create_error_message)

    # We have to add an "identity" action (output_action) here due to type inference issues
    OUTPUT = (CREATE_RESULT | CREATE_ERROR) + output_action
    # OUTPUT = CREATE_RESULT + output_action  # noqa: ERA001
    # _ = CREATE_ERROR + OUTPUT               # noqa: ERA001

    return OUTPUT.as_result()


def test_graph_algebra():  # noqa: D103
    def log_callback(message: str):
        print(f"[TRACE] {message}")  # noqa: T201

    graph = create_test_graph()
    executor = Executor(graph, tracer=LogTracer(log_callback))

    input_value = 4  # results in => "Result: 3"
    result = executor.run(input_value)
    Assertions.check(result == "Result: 3", f"Expected 'Result: 3', got '{result}'")

    input_value = -2  # results in => "Result: 1"
    result = executor.run(input_value)
    Assertions.check(result == "Result: 1", f"Expected 'Result: 1', got '{result}'")

    input_value = -5  # results in => "Error: -2 is negative"
    result = executor.run(input_value)
    Assertions.check(result == "Error: -2 is negative", f"Expected 'Error: -2 is negative', got '{result}'")
