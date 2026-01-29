# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    tool,
)
from typing_extensions import Never
 
"""
Sample: Sub-Workflows (Basics)

What it does:
- Shows how a parent workflow invokes a sub-workflow via `WorkflowExecutor` and collects results.
- Example: parent orchestrates multiple text processors that count words/characters.
- Demonstrates how sub-workflows complete by yielding outputs when processing is done.

Prerequisites:
- No external services required.
"""


# Message types
@dataclass
class TextProcessingRequest:
    """Request to process a text string."""

    text: str
    task_id: str


@dataclass
class TextProcessingResult:
    """Result of text processing."""

    task_id: str
    text: str
    word_count: int
    char_count: int


# Sub-workflow executor
class TextProcessor(Executor):
    """Processes text strings - counts words and characters."""

    def __init__(self):
        super().__init__(id="text_processor")

    @handler
    async def process_text(
        self, request: TextProcessingRequest, ctx: WorkflowContext[Never, TextProcessingResult]
    ) -> None:
        """Process a text string and return statistics."""
        text_preview = f"'{request.text[:50]}{'...' if len(request.text) > 50 else ''}'"
        print(f"🔍 Sub-workflow processing text (Task {request.task_id}): {text_preview}")

        # Simple text processing
        word_count = len(request.text.split()) if request.text.strip() else 0
        char_count = len(request.text)

        print(f"📊 Task {request.task_id}: {word_count} words, {char_count} characters")

        # Create result
        result = TextProcessingResult(
            task_id=request.task_id,
            text=request.text,
            word_count=word_count,
            char_count=char_count,
        )

        print(f"✅ Sub-workflow completed task {request.task_id}")
        # Signal completion by yielding the result
        await ctx.yield_output(result)


# Parent workflow
class TextProcessingOrchestrator(Executor):
    """Orchestrates multiple text processing tasks using sub-workflows."""

    results: list[TextProcessingResult] = []
    expected_count: int = 0

    def __init__(self):
        super().__init__(id="text_orchestrator")

    @handler
    async def start_processing(self, texts: list[str], ctx: WorkflowContext[TextProcessingRequest]) -> None:
        """Start processing multiple text strings."""
        print(f"📄 Starting processing of {len(texts)} text strings")
        print("=" * 60)

        self.expected_count = len(texts)

        # Send each text to a sub-workflow
        for i, text in enumerate(texts):
            task_id = f"task_{i + 1}"
            request = TextProcessingRequest(text=text, task_id=task_id)
            print(f"📤 Dispatching {task_id} to sub-workflow")
            await ctx.send_message(request, target_id="text_processor_workflow")

    @handler
    async def collect_result(
        self,
        result: TextProcessingResult,
        ctx: WorkflowContext[Never, list[TextProcessingResult]],
    ) -> None:
        """Collect results from sub-workflows."""
        print(f"📥 Collected result from {result.task_id}")
        self.results.append(result)

        # Check if all results are collected
        if len(self.results) == self.expected_count:
            print("\n🎉 All tasks completed!")
            await ctx.yield_output(self.results)


def get_result_summary(results: list[TextProcessingResult]) -> dict[str, Any]:
    """Get a summary of all processing results."""
    total_words = sum(result.word_count for result in results)
    total_chars = sum(result.char_count for result in results)
    avg_words = total_words / len(results) if results else 0
    avg_chars = total_chars / len(results) if results else 0

    return {
        "total_texts": len(results),
        "total_words": total_words,
        "total_characters": total_chars,
        "average_words_per_text": round(avg_words, 2),
        "average_characters_per_text": round(avg_chars, 2),
    }


def create_sub_workflow() -> WorkflowExecutor:
    """Create the text processing sub-workflow."""
    print("🚀 Setting up sub-workflow...")

    processing_workflow = (
        WorkflowBuilder()
        .register_executor(TextProcessor, name="text_processor")
        .set_start_executor("text_processor")
        .build()
    )

    return WorkflowExecutor(processing_workflow, id="text_processor_workflow")


async def main():
    """Main function to run the basic sub-workflow example."""
    print("🔧 Setting up parent workflow...")
    # Step 1: Create the parent workflow
    main_workflow = (
        WorkflowBuilder()
        .register_executor(TextProcessingOrchestrator, name="text_orchestrator")
        .register_executor(create_sub_workflow, name="text_processor_workflow")
        .set_start_executor("text_orchestrator")
        .add_edge("text_orchestrator", "text_processor_workflow")
        .add_edge("text_processor_workflow", "text_orchestrator")
        .build()
    )

    # Step 2: Test data - various text strings
    test_texts = [
        "Hello world! This is a simple test.",
        "Python is a powerful programming language used for many applications.",
        "Short text.",
        "This is a longer text with multiple sentences. It contains more words and characters. We use it to test our text processing workflow.",  # noqa: E501
        "",  # Empty string
        "   Spaces   around   text   ",
    ]

    print(f"\n🧪 Testing with {len(test_texts)} text strings")
    print("=" * 60)

    # Step 3: Run the workflow
    result = await main_workflow.run(test_texts)

    # Step 4: Display results
    print("\n📊 Processing Results:")
    print("=" * 60)

    # Sort results by task_id for consistent display
    task_results = result.get_outputs()
    assert len(task_results) == 1
    sorted_results = sorted(task_results[0], key=lambda r: r.task_id)

    for result in sorted_results:
        preview = result.text[:30] + "..." if len(result.text) > 30 else result.text
        preview = preview.replace("\n", " ").strip() or "(empty)"
        print(f"✅ {result.task_id}: '{preview}' -> {result.word_count} words, {result.char_count} chars")

    # Step 6: Display summary
    summary = get_result_summary(sorted_results)
    print("\n📈 Summary:")
    print("=" * 60)
    print(f"📄 Total texts processed: {summary['total_texts']}")
    print(f"📝 Total words: {summary['total_words']}")
    print(f"🔤 Total characters: {summary['total_characters']}")
    print(f"📊 Average words per text: {summary['average_words_per_text']}")
    print(f"📏 Average characters per text: {summary['average_characters_per_text']}")

    print("\n🏁 Processing complete!")


if __name__ == "__main__":
    asyncio.run(main())
