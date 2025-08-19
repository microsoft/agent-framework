# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

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
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "workflow"))
    from agent_framework_workflow import WorkflowExecutor

"""
The following sample demonstrates basic sub-workflow functionality.

This sample shows how to:
1. Create a simple sub-workflow that processes data
2. Execute that sub-workflow as an executor within a parent workflow
3. Collect results from the sub-workflow

The example shows a text processing pipeline where:
- The sub-workflow converts text to uppercase
- The parent workflow orchestrates multiple sub-workflow executions
"""


@dataclass
class TextRequest:
    """Request to process text."""
    text: str


@dataclass
class TextResult:
    """Result of text processing."""
    original: str
    processed: str


class TextProcessor(Executor):
    """A simple text processor that works as a sub-workflow."""
    
    def __init__(self):
        super().__init__(id="text_processor")
    
    @handler(output_types=[])
    async def process_text(self, request: TextRequest, ctx: WorkflowContext) -> None:
        """Process text by converting to uppercase."""
        print(f"Sub-workflow processing: '{request.text}'")
        
        processed = request.text.upper()
        result = TextResult(original=request.text, processed=processed)
        
        # Complete the sub-workflow with the result
        await ctx.add_event(WorkflowCompletedEvent(data=result))


class TextOrchestrator(Executor):
    """Parent orchestrator that manages text processing sub-workflows."""
    
    def __init__(self):
        super().__init__(id="text_orchestrator")
        self.results = []
    
    @handler(output_types=[TextRequest])
    async def start_processing(self, texts: list[str], ctx: WorkflowContext) -> None:
        """Start processing a batch of texts."""
        print(f"Starting processing of {len(texts)} texts")
        for text in texts:
            request = TextRequest(text=text)
            await ctx.send_message(request, target_id="text_processor_workflow")
    
    @handler(output_types=[])
    async def collect_result(self, result: TextResult, ctx: WorkflowContext) -> None:
        """Collect processing results."""
        print(f"Collected result: '{result.original}' -> '{result.processed}'")
        self.results.append(result)


async def main():
    """Main function to run the simple sub-workflow example."""
    print("Setting up simple sub-workflow...")
    
    # Step 1: Create the text processing sub-workflow
    text_processor = TextProcessor()
    
    # For workflow validation, we need at least one edge, so add a dummy executor
    class DummyExecutor(Executor):
        def __init__(self):
            super().__init__(id="dummy")
        @handler(output_types=[])
        async def process(self, message: object, ctx: WorkflowContext) -> None:
            pass  # Do nothing
    
    dummy = DummyExecutor()
    processing_workflow = (
        WorkflowBuilder()
        .set_start_executor(text_processor)
        .add_edge(text_processor, dummy)  # Dummy edge for validation
        .build()
    )
    
    print("Setting up parent workflow...")
    
    # Step 2: Create the parent workflow
    orchestrator = TextOrchestrator()
    workflow_executor = WorkflowExecutor(processing_workflow, id="text_processor_workflow")
    
    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, workflow_executor)
        .add_edge(workflow_executor, orchestrator)
        .build()
    )
    
    # Step 3: Test with some texts
    test_texts = ["hello", "world", "sub-workflow"]
    
    print(f"\nTesting with texts: {test_texts}")
    print("=" * 50)
    
    # Step 4: Run the workflow
    result = await main_workflow.run(test_texts)
    
    print("\nFinal Results:")
    print("=" * 50)
    for result in orchestrator.results:
        print(f"'{result.original}' -> '{result.processed}'")
    
    print(f"\nProcessed {len(orchestrator.results)} texts total")


if __name__ == "__main__":
    asyncio.run(main())