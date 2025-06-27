# Copyright (c) Microsoft. All rights reserved.

from python.test.test_utils import Assertions

from agent_framework.graph import (
    Executor,
    GraphBuilder,
)


class TestGraphBuilder:
    """Test class for GraphBuilder."""

    def test_countdown_graph(self):
        """Run a test of the graph builder by generating a graph equivalent of autogen's count sample."""
        counted = 0

        def count_one(input: int) -> int:
            """A simple action that counts down from the input."""
            nonlocal counted
            counted += 1
            return input - 1

        def should_continue(input: int) -> bool:
            """A condition that checks if the input is zero."""
            return input > 0

        def is_done(input: int) -> bool:
            """A condition that checks if the input is done."""
            return input == 0

        def final_action(input: int) -> str:
            """Final action that returns a message when counting is done."""
            return "Done!"

        builder = GraphBuilder.start(count_one)
        builder.add_edge(source=builder.start_node, target=builder.start_node, condition=should_continue)
        builder.add_edge(source=builder.start_node, target=final_action, condition=is_done)

        graph = builder.build(output_node="final_action")

        input = 2
        result = Executor(graph).run(input)

        Assertions.check(result == "Done!")
        Assertions.check(counted == input, f"Expected {input} count(s), but got {counted}.")
