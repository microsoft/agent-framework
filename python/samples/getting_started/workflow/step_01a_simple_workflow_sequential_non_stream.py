# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowViz,
    handler,
)

"""
The following sample demonstrates a basic workflow with two executors
that process a string in sequence. The first executor converts the
input string to uppercase, and the second executor reverses the string.
"""


class UpperCaseExecutor(Executor):
    """An executor that converts text to uppercase."""

    @handler(output_types=[str])
    async def to_upper_case(self, text: str, ctx: WorkflowContext) -> None:
        """Execute the task by converting the input string to uppercase."""
        result = text.upper()

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)


class ReverseTextExecutor(Executor):
    """An executor that reverses text."""

    @handler
    async def reverse_text(self, text: str, ctx: WorkflowContext) -> None:
        """Execute the task by reversing the input string."""
        result = text[::-1]

        # Send the result with a workflow completion event.
        await ctx.add_event(WorkflowCompletedEvent(result))


async def main():
    """Main function to run the workflow."""
    # Step 1: Create the executors.
    upper_case_executor = UpperCaseExecutor(id="upper_case_executor")
    reverse_text_executor = ReverseTextExecutor(id="reverse_text_executor")

    # Step 2: Build the workflow with the defined edges.
    workflow = (
        WorkflowBuilder()
        .add_edge(upper_case_executor, reverse_text_executor)
        .set_start_executor(upper_case_executor)
        .build()
    )

    # Step 2.5: Visualize the workflow (optional)
    print("🎨 Generating workflow visualization...")
    viz = WorkflowViz(workflow)
    # Print out the mermaid string.
    print("🧜 Mermaid string: \n=======")
    print(viz.to_mermaid())
    print("=======")
    # Print out the DiGraph string.
    print("📊 DiGraph string: \n=======")
    print(viz.to_digraph())
    print("=======")
    try:
        # Export the DiGraph visualization as SVG.
        svg_file = viz.export(format="svg")
        print(f"🖼️  SVG file saved to: {svg_file}")
    except ImportError:
        print("💡 Tip: Install 'viz' extra to export workflow visualization: pip install agent-framework-workflow[viz]")

    # Step 3: Run the workflow with an initial message.
    events = await workflow.run("hello world")
    print(events.get_completed_event())


if __name__ == "__main__":
    asyncio.run(main())
