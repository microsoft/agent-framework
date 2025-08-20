# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.workflow import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

# Import the new sub-workflow types directly from the implementation package
try:
    from agent_framework_workflow import WorkflowExecutor
except ImportError:
    # For development/testing when agent_framework_workflow is not installed
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "workflow"))
    from agent_framework_workflow import WorkflowExecutor

"""
This sample demonstrates the simplest sub-workflow pattern.

This sample shows how to:
1. Create a simple sub-workflow that processes data
2. Execute that sub-workflow as an executor within a parent workflow
3. Collect results from the sub-workflow

The example shows a text processing pipeline where:
- The sub-workflow converts text to uppercase
- The parent workflow orchestrates multiple sub-workflow executions

Key concepts demonstrated:
- WorkflowExecutor: Wraps a workflow to make it behave as an executor
- Sub-workflow composition: Using workflows as components within larger workflows
- Simple data flow: Parent sends data, sub-workflow processes, parent collects results
"""


# Step 1: Define your sub-workflow
class TextProcessor(Executor):
    """A simple text processor that works as a sub-workflow."""

    def __init__(self):
        super().__init__(id="text_processor")

    @handler(output_types=[])
    async def process_text(self, text: str, ctx: WorkflowContext) -> None:
        """Process text by converting to uppercase."""
        print(f"Sub-workflow processing: '{text}'")
        processed = text.upper()
        print(f"Sub-workflow result: '{processed}'")
        # Complete the sub-workflow with the result
        await ctx.add_event(WorkflowCompletedEvent(data=processed))


# Step 3: Use it in a parent workflow
class ParentOrchestrator(Executor):
    """Parent orchestrator that manages text processing sub-workflows."""

    def __init__(self):
        super().__init__(id="orchestrator")
        self.results: list[str] = []

    @handler(output_types=[str])
    async def start(self, texts: list[str], ctx: WorkflowContext) -> None:
        """Send texts to sub-workflow for processing."""
        print(f"Parent starting processing of {len(texts)} texts")
        for text in texts:
            await ctx.send_message(text, target_id="text_workflow")

    @handler(output_types=[])
    async def collect_result(self, result: str, ctx: WorkflowContext) -> None:
        """Collect results from sub-workflow."""
        print(f"Parent collected result: '{result}'")
        self.results.append(result)


async def main():
    """Main function to run the simple sub-workflow example."""
    print("Setting up simple sub-workflow...")

    # Step 2: Create the sub-workflow
    text_processor = TextProcessor()

    processing_workflow = WorkflowBuilder().set_start_executor(text_processor).build()

    print("Setting up parent workflow...")

    # Step 4: Wire everything together
    parent = ParentOrchestrator()
    text_workflow_executor = WorkflowExecutor(processing_workflow, id="text_workflow")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, text_workflow_executor)
        .add_edge(text_workflow_executor, parent)
        .build()
    )

    # Test with some sample texts
    test_texts = ["hello", "world", "sub-workflow", "example"]

    print(f"\nTesting with texts: {test_texts}")
    print("=" * 50)

    # Run the workflow
    result = await main_workflow.run(test_texts)

    print("\nFinal Results:")
    print("=" * 50)
    for i, result_text in enumerate(parent.results):
        original = test_texts[i] if i < len(test_texts) else "unknown"
        print(f"'{original}' -> '{result_text}'")

    print(f"\nProcessed {len(parent.results)} texts total")

    # Verify all texts were processed
    if len(parent.results) == len(test_texts):
        print("SUCCESS: All texts processed successfully!")
    else:
        print(f"WARNING: Expected {len(test_texts)} results, got {len(parent.results)}")


if __name__ == "__main__":
    asyncio.run(main())
