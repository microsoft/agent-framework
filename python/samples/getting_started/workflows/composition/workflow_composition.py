# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Workflow Composition with add_workflow()

What it does:
- Demonstrates composing high-level orchestration patterns (ConcurrentBuilder, SequentialBuilder)
  using WorkflowBuilder.add_workflow()
- Shows how to chain workflows together with add_edge() using logical workflow IDs
- Demonstrates adding pre/post-processing executors around composed workflows

This new API simplifies workflow composition by allowing you to:
1. Add orchestration patterns as logical units
2. Connect them using the workflow ID directly (no need to know internal executor names)
3. Mix and match high-level patterns with custom executors

Prerequisites:
- Azure OpenAI credentials
"""

import asyncio
import os

from agent_framework import (
    AgentExecutorResponse,
    ChatAgent,
    ChatMessage,
    ConcurrentBuilder,
    Executor,
    Role,
    SequentialBuilder,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential
from typing_extensions import Never


def create_chat_client():
    """Create a chat client based on available environment variables."""
    return AzureOpenAIChatClient(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        credential=DefaultAzureCredential(),
        model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
    )


# =============================================================================
# EXAMPLE CUSTOM EXECUTORS
# =============================================================================
# The executors below are FOR DEMONSTRATION PURPOSES ONLY. They show patterns
# for building your own pre-processors, post-processors, and custom aggregators.
# These are NOT part of the agent_framework library - you would write your own
# versions tailored to your specific use case.
# =============================================================================


class InputFormatter(Executor):
    """Example preprocessor that formats input before sending to analysis.

    This demonstrates how to add custom preprocessing before a composed workflow.
    """

    def __init__(self):
        super().__init__(id="input_formatter")

    @handler
    async def format_input(self, message: str, ctx: WorkflowContext[str]) -> None:
        """Format the input message."""
        print(f"\n{'=' * 60}")
        print("INPUT FORMATTER")
        print(f"{'=' * 60}")
        print(f"Received: {message[:100]}...")
        formatted = f"Please analyze the following topic thoroughly:\n\n{message}"
        print("Formatted input for analysis agents.")
        await ctx.send_message(formatted)


class ForwardingAggregator(Executor):
    """Example aggregator that forwards messages to downstream executors.

    This demonstrates how to create a custom aggregator for ConcurrentBuilder
    when you need to chain to downstream executors. The default aggregator uses
    yield_output() which makes it terminal. This version uses send_message()
    to forward data through edges to downstream executors.
    """

    def __init__(self):
        super().__init__(id="forwarding_aggregator")

    @handler
    async def aggregate(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[list[ChatMessage]]) -> None:
        """Aggregate responses and forward to downstream."""
        # Extract assistant messages from each agent's response
        messages: list[ChatMessage] = []
        for r in results:
            if r.agent_response and r.agent_response.messages:
                for msg in r.agent_response.messages:
                    if msg.role == Role.ASSISTANT:
                        messages.append(msg)

        # Forward to downstream executor (OutputFormatter)
        await ctx.send_message(messages)


class OutputFormatter(Executor):
    """Example postprocessor that formats the final output from the workflow.

    This demonstrates how to add custom postprocessing after a composed workflow.
    """

    def __init__(self):
        super().__init__(id="output_formatter")

    @handler
    async def format_output(self, messages: list[ChatMessage], ctx: WorkflowContext[Never, str]) -> None:
        """Format and yield the final output."""
        print(f"\n{'=' * 60}")
        print("OUTPUT FORMATTER")
        print(f"{'=' * 60}")

        # Extract text content from the messages
        output_parts: list[str] = []
        for msg in messages:
            if isinstance(msg, ChatMessage):
                output_parts.append(msg.text)
            else:
                output_parts.append(str(msg))

        final_output = "\n\n---\n\n".join(output_parts)
        print(f"Compiled {len(output_parts)} analysis sections into final report.")
        await ctx.yield_output(final_output)


async def example_simple_composition():
    """Example: Compose two high-level patterns together.

    This shows the simplest use case - chaining a ConcurrentBuilder (parallel analysis)
    with a SequentialBuilder (summarization).
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Simple Workflow Composition")
    print("=" * 80)
    print("Chaining ConcurrentBuilder -> SequentialBuilder")

    client = create_chat_client()

    # Create agents for parallel analysis
    technical_analyst = ChatAgent(
        name="technical_analyst",
        chat_client=client,
        instructions="You are a technical analyst. Analyze the technical aspects of the topic in 2-3 sentences.",
    )
    business_analyst = ChatAgent(
        name="business_analyst",
        chat_client=client,
        instructions="You are a business analyst. Analyze the business implications in 2-3 sentences.",
    )

    # Create agent for summarization
    summarizer = ChatAgent(
        name="summarizer",
        chat_client=client,
        instructions="You are a summarizer. Combine the analyses into a brief executive summary in 2-3 sentences.",
    )

    # Create high-level orchestration patterns
    analysis = ConcurrentBuilder().participants([technical_analyst, business_analyst])
    summary = SequentialBuilder().participants([summarizer])

    # Compose them together using add_workflow()
    workflow = (
        WorkflowBuilder()
        .add_workflow(analysis, id="analysis")
        .add_workflow(summary, id="summary")
        .add_edge("analysis", "summary")  # Framework resolves to analysis/aggregator -> summary/input-conversation
        .set_start_executor("analysis")  # Framework knows this means analysis/dispatcher
        .build()
    )

    print("\nWorkflow structure:")
    print(f"  Start executor: {workflow.start_executor_id}")
    print(f"  Executors: {list(workflow.executors.keys())}")

    # Run the workflow
    result = await workflow.run("Artificial Intelligence in Healthcare")
    outputs = result.get_outputs()

    print("\n--- Final Output ---")
    for output in outputs:
        if isinstance(output, list):
            for item in output:
                if isinstance(item, ChatMessage):
                    print(f"\n{item.text}")
                else:
                    print(f"\n{item}")
        elif isinstance(output, ChatMessage):
            print(f"\n{output.text}")
        else:
            print(f"\n{output}")


async def example_pre_post_processing():
    """Example: Add pre/post-processing around a high-level pattern.

    This shows how to wrap a ConcurrentBuilder with custom preprocessing
    and postprocessing executors.

    Note: The default ConcurrentBuilder aggregator uses yield_output() which makes it
    a terminal node. To chain to downstream executors, we use a custom ForwardingAggregator
    that uses send_message() instead.
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Pre/Post Processing with Composed Workflows")
    print("=" * 80)
    print("InputFormatter -> ConcurrentBuilder (with custom aggregator) -> OutputFormatter")

    client = create_chat_client()

    # Create agents for analysis
    technical_analyst = ChatAgent(
        name="technical_analyst",
        chat_client=client,
        instructions="You are a technical analyst. Provide a technical analysis in 2-3 sentences.",
    )
    market_analyst = ChatAgent(
        name="market_analyst",
        chat_client=client,
        instructions="You are a market analyst. Provide market analysis in 2-3 sentences.",
    )

    # Create the concurrent analysis pattern with a custom forwarding aggregator
    # The ForwardingAggregator uses send_message() to forward to downstream executors,
    # unlike the default aggregator which uses yield_output() (terminal)
    analysis = (
        ConcurrentBuilder().participants([technical_analyst, market_analyst]).with_aggregator(ForwardingAggregator())
    )

    # Compose with pre/post-processing
    workflow = (
        WorkflowBuilder()
        .register_executor(InputFormatter, name="input_formatter")
        .add_workflow(analysis, id="analysis")
        .register_executor(OutputFormatter, name="output_formatter")
        .add_edge("input_formatter", "analysis")
        .add_edge("analysis", "output_formatter")
        .set_start_executor("input_formatter")
        .build()
    )

    print("\nWorkflow structure:")
    print(f"  Start executor: {workflow.start_executor_id}")
    print(f"  Executors: {list(workflow.executors.keys())}")

    # Run the workflow
    result = await workflow.run("Electric Vehicle Adoption")
    outputs = result.get_outputs()

    print("\n--- Final Output ---")
    for output in outputs:
        print(output)


async def main():
    """Run all composition examples."""
    print("=" * 80)
    print("WORKFLOW COMPOSITION SAMPLES")
    print("=" * 80)
    print("\nThese examples demonstrate the new add_workflow() API for composing")
    print("high-level orchestration patterns (ConcurrentBuilder, SequentialBuilder)")
    print("with WorkflowBuilder.\n")

    # Run examples
    await example_simple_composition()
    await example_pre_post_processing()

    print("\n" + "=" * 80)
    print("ALL EXAMPLES COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
