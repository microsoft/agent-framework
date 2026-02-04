# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any, Never

from agent_framework import (
    ChatAgent,
    ChatMessage,
    ConcurrentBuilder,
    Executor,
    Role,
    Workflow,
    WorkflowContext,
    handler,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Concurrent Orchestration with participant factories and Custom Aggregator

Build a concurrent workflow with ConcurrentBuilder that fans out one prompt to
multiple domain agents and fans in their responses.

Override the default aggregator with a custom Executor class that uses
AzureOpenAIChatClient.get_response() to synthesize a concise, consolidated summary
from the experts' outputs.

All participants and the aggregator are created via factory functions that return
their respective ChatAgent or Executor instances.

Using participant factories allows you to set up proper state isolation between workflow
instances created by the same builder. This is particularly useful when you need to handle
requests or tasks in parallel with stateful participants.

Demonstrates:
- ConcurrentBuilder().register_participants([...]).with_aggregator(callback)
- Fan-out to agents and fan-in at an aggregator
- Aggregation implemented via an LLM call (chat_client.get_response)
- Workflow output yielded with the synthesized summary string

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient (az login + required env vars)
"""


def create_researcher() -> ChatAgent:
    """Factory function to create a researcher agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
            " opportunities, and risks."
        ),
        name="researcher",
    )


def create_marketer() -> ChatAgent:
    """Factory function to create a marketer agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
            " aligned to the prompt."
        ),
        name="marketer",
    )


def create_legal() -> ChatAgent:
    """Factory function to create a legal/compliance agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).as_agent(
        instructions=(
            "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
            " based on the prompt."
        ),
        name="legal",
    )


class SummarizationExecutor(Executor):
    """Custom aggregator executor that synthesizes expert outputs into a concise summary."""

    def __init__(self) -> None:
        super().__init__(id="summarization_executor")
        self.chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    @handler
    async def summarize_results(self, results: list[Any], ctx: WorkflowContext[Never, str]) -> None:
        expert_sections: list[str] = []
        for r in results:
            try:
                messages = getattr(r.agent_response, "messages", [])
                final_text = messages[-1].text if messages and hasattr(messages[-1], "text") else "(no content)"
                expert_sections.append(f"{getattr(r, 'executor_id', 'expert')}:\n{final_text}")
            except Exception as e:
                expert_sections.append(f"{getattr(r, 'executor_id', 'expert')}: (error: {type(e).__name__}: {e})")

        # Ask the model to synthesize a concise summary of the experts' outputs
        system_msg = ChatMessage(
            Role.SYSTEM,
            text=(
                "You are a helpful assistant that consolidates multiple domain expert outputs "
                "into one cohesive, concise summary with clear takeaways. Keep it under 200 words."
            ),
        )
        user_msg = ChatMessage(Role.USER, text="\n\n".join(expert_sections))

        response = await self.chat_client.get_response([system_msg, user_msg])

        await ctx.yield_output(response.messages[-1].text if response.messages else "")


async def run_workflow(workflow: Workflow, query: str) -> None:
    events = await workflow.run(query)
    outputs = events.get_outputs()

    if outputs:
        print(outputs[0])  # Get the first (and typically only) output
    else:
        raise RuntimeError("No outputs received from the workflow.")


async def main() -> None:
    # Create a concurrent builder with participant factories and a custom aggregator
    # - register_participants([...]) accepts factory functions that return
    #   AgentProtocol (agents) or Executor instances.
    # - register_aggregator(...) takes a factory function that returns an Executor instance.
    concurrent_builder = (
        ConcurrentBuilder()
        .register_participants([create_researcher, create_marketer, create_legal])
        .register_aggregator(SummarizationExecutor)
    )

    # Build workflow_a
    workflow_a = concurrent_builder.build()

    # Run workflow_a
    # Context is maintained across runs
    print("=== First Run on workflow_a ===")
    await run_workflow(workflow_a, "We are launching a new budget-friendly electric bike for urban commuters.")
    print("\n=== Second Run on workflow_a ===")
    await run_workflow(workflow_a, "Refine your response to focus on the California market.")

    # Build workflow_b
    # This will create new instances of all participants and the aggregator
    # The agents will also get new threads
    workflow_b = concurrent_builder.build()
    # Run workflow_b
    # Context is not maintained across instances
    # Should not expect mentions of electric bikes in the results
    print("\n=== First Run on workflow_b ===")
    await run_workflow(workflow_b, "Refine your response to focus on the California market.")

    """
    Sample Output:

    === First Run on workflow_a ===
    The budget-friendly electric bike market is poised for significant growth, driven by urbanization, ...

    === Second Run on workflow_a ===
    Launching a budget-friendly electric bike in California presents significant opportunities, driven ...

    === First Run on workflow_b ===
    To successfully penetrate the California market, consider these tailored strategies focused on ...
    """


if __name__ == "__main__":
    asyncio.run(main())
