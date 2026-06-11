# Copyright (c) Microsoft. All rights reserved.

"""Calling agents inside functional workflows.

Agent calls work inside @workflow as plain function calls — no decorator needed.
Just call the agent and use the result.

If you want per-step caching (so agent calls don't re-execute on HITL resume
or crash recovery), add @step. Since each agent call hits an LLM API (time +
money), @step is often worth it. But it's always opt-in.

This sample shows both approaches side-by-side so you can see the difference.
"""

import asyncio

from agent_framework import Agent, step, workflow
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

# ---------------------------------------------------------------------------
# Create agents
# ---------------------------------------------------------------------------

client = FoundryChatClient(credential=AzureCliCredential())

classifier_agent = Agent(
    name="ClassifierAgent",
    instructions=(
        "Classify documents into one category: Technical, Legal, Marketing, or Scientific. "
        "Reply with only the category name."
    ),
    client=client,
)

writer_agent = Agent(
    name="WriterAgent",
    instructions="Summarize the given content in one sentence.",
    client=client,
)

reviewer_agent = Agent(
    name="ReviewerAgent",
    instructions="Review the given summary in one sentence. Is it accurate and complete?",
    client=client,
)

# ---------------------------------------------------------------------------
# Simplest approach: call agents directly inside the workflow.
# No @step, no wrappers — just plain function calls.
# ---------------------------------------------------------------------------


@workflow
async def simple_pipeline(document: str) -> str:
    """Process a document — agents called inline, no @step."""
    classification = (await classifier_agent.run(f"Classify this document: {document}")).text
    summary = (await writer_agent.run(f"Summarize: {document}")).text
    review = (await reviewer_agent.run(f"Review this summary: {summary}")).text

    return f"Classification: {classification}\nSummary: {summary}\nReview: {review}"


# ---------------------------------------------------------------------------
# With @step: agent results are cached. On HITL resume or checkpoint
# recovery, completed steps return their saved result instead of calling
# the LLM again. Worth it for expensive operations.
# ---------------------------------------------------------------------------


@step
async def classify_document(doc: str) -> str:
    return (await classifier_agent.run(f"Classify this document: {doc}")).text


@step
async def generate_summary(doc: str) -> str:
    return (await writer_agent.run(f"Summarize: {doc}")).text


@step
async def review_summary(summary: str) -> str:
    return (await reviewer_agent.run(f"Review this summary: {summary}")).text


@workflow
async def cached_pipeline(document: str) -> str:
    """Same pipeline, but @step caches each agent call."""
    classification = await classify_document(document)
    summary = await generate_summary(document)
    review = await review_summary(summary)

    return f"Classification: {classification}\nSummary: {summary}\nReview: {review}"


async def main():
    # Simple version — agents called inline
    result = await simple_pipeline.run("This is a technical document about machine learning...")
    print(result.get_outputs()[0])

    # Cached version — same result, but steps won't re-execute on resume
    result = await cached_pipeline.run("This is a technical document about machine learning...")
    print(f"\nCached: {result.get_outputs()[0]}")


if __name__ == "__main__":
    asyncio.run(main())
