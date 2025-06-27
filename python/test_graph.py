# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

# We want to be able to test multiple types of graph transitions:
#   - Conditional transitions
#   - Unconditional transitions
#   - Fan-out transitions
#   - Accumulator transitions
# Define the a temp interface for the agents (no async, for simplicity)
from typing import Any, Generic, Literal, Protocol, TypeVar

import agent_framework.graph as g

TIn = TypeVar("TIn", contravariant=True)
TOut = TypeVar("TOut", covariant=True)


class Agent(Protocol, Generic[TIn, TOut]):  # noqa: D101
    def run(self, input: TIn) -> TOut:
        """Defines the action to be performed by the agent."""
        ...

    @property
    def name(self) -> str:
        """Returns the name of the agent."""
        ...


# Define the shared agents and message types first
@dataclass
class TextInputRequest:  # noqa: D101
    prompt: str


@dataclass
class UserInput:  # noqa: D101
    request_type: Literal["text_input"]
    input_text: str


class UserInputAgent(Agent[TextInputRequest, UserInput]):  # noqa: D101
    def run(self, msg: TextInputRequest) -> UserInput:  # noqa: D102
        return UserInput(request_type="text_input", input_text=msg.prompt)

    @property
    def name(self) -> str:  # noqa: D102
        return "UserInputAgent"


@dataclass
class ValidationResult:  # noqa: D101
    is_valid: bool
    message: str | None = None


class Validator(Protocol, Generic[TIn]):  # noqa: D101
    def __call__(self, input: TIn) -> ValidationResult | bool | str | tuple[bool, str] | None:
        """Defines the validation logic for the input.

        Returns one of the following:
            ValidationResult: The validation result.
            bool: True if valid, False if invalid. No message.
            str: Error message if invalid.
            tuple[bool, str]: (is_valid, error_message).
            None: If valid. No message.
        """
        ...


class ValidationAgent(Agent[UserInput, ValidationResult]):  # noqa: D101
    def __init__(self, condition: g.EdgeCondition[UserInput] | None = None):  # noqa: D107
        self.condition = condition

    def run(self, msg: UserInput) -> ValidationResult:  # noqa: D102
        if self.condition is None:
            return ValidationResult(is_valid=True)

        result = self.condition(msg)
        if result is None:
            return ValidationResult(is_valid=True)

        if isinstance(result, bool):
            return ValidationResult(is_valid=result)

        if isinstance(result, str):
            return ValidationResult(is_valid=False, message=result)

        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[0], bool)
            and isinstance(result[1], str)
        ):
            return ValidationResult(is_valid=result[0], message=str(result[1]))

        return ValidationResult(is_valid=False, message=f"Unexpected condition result: {result}")


def test_simple_validation_loop():  # noqa: D103
    uia = UserInputAgent()

    def count_parens(input: UserInput) -> ValidationResult:
        stack_count = 0
        for idx, char in enumerate(input.input_text):
            if char == "(":
                stack_count += 1
            elif char == ")":
                stack_count -= 1

            if stack_count < 0:
                return ValidationResult(is_valid=False, message=f"Unexpected closing parenthesis at position {idx}.")

        if stack_count > 0:
            return ValidationResult(is_valid=False, message="Missing closing parenthesis.")

        return ValidationResult(is_valid=True)

    va = ValidationAgent(condition=count_parens)

    builder = g.GraphBuilder[TextInputRequest]()

    builder.add_edge(builder.start_node, uia)
    builder.add_edge(uia, va)

    def generate_input_request() -> TextInputRequest:
        return TextInputRequest(prompt="Please enter a string with parentheses, e.g. (Hello, World!)")

    @g.runnable(id="output_success")
    def output_success(input: ValidationResult) -> Any:
        if not input.is_valid:
            raise ValueError(f"Validation failed: {input.message}")

        print("Validation succeeded. Proceeding with the next turn.")  # noqa: T201
        return generate_input_request()

    @g.runnable(id="output_error")
    def output_error(input: ValidationResult) -> Any:
        if input.is_valid:
            raise ValueError("Validation succeeded unexpectedly.")

        output = (
            "Validation failed with no message." if input.message is None else f"Validation failed: {input.message}"
        )
        print(output)  # noqa: T201

        return generate_input_request()

    builder.add_edge(va, output_success, condition=lambda x: x.is_valid)
    builder.add_edge(va, output_error, condition=lambda x: not x.is_valid)

    builder.add_edge(output_success, builder.start_node)
    builder.add_edge(output_error, builder.start_node)

    # The real issue with this variant of the API is that the control flow is all over the place.
    # It is not immediately clear how to properly set up output_error/output_success to ensure we can both deal with
    # errors, but also avoid breaking out of the loop, even when validation is unsuccessful.

    graph = builder.build()
    if not graph:
        raise ValueError("Graph is empty after building.")

    executor = g.Executor(graph)
    executor.run(TextInputRequest(prompt="(Hello, World!)"))

if __name__ == "__main__":
    test_simple_validation_loop()
    # This will run the validation loop with a valid input.
    # You can modify the input to test different scenarios.
