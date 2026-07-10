# Copyright (c) Microsoft. All rights reserved.

"""
Agent-as-Tool: Parallel Sub-agent Execution with Structured Context

Demonstrates a Research Supervisor that delegates work to three specialist
sub-agents running in parallel via ``asyncio.gather``:

1. ``summarizer`` -- produces a concise summary of the input text
2. ``fact_checker`` -- verifies key factual claims in the input
3. ``sentiment_analyzer`` -- analyzes the tone and sentiment

Each sub-agent is wrapped with the ``@tool`` decorator and returns structured
output (dictionaries).  The supervisor invokes them concurrently with individual
error handling per sub-agent, aggregates the results, and produces a final
synthesized report via a supervisor agent.

Key concepts:
- Wrapping agent calls in ``@tool``-decorated async functions
- Parallel execution via ``asyncio.gather`` with per-sub-agent error handling
- Structured output from sub-agents (returning dicts instead of raw strings)
- Result aggregation and synthesis by a supervisor agent
"""

import asyncio
from typing import Any

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Sub-agent definitions
# ---------------------------------------------------------------------------

summarizer_agent = Agent(
    client=OpenAIChatClient(),
    name="Summarizer",
    instructions=(
        "You are a professional text summarizer. "
        "Given an input text, produce a concise summary of 2-3 sentences "
        "capturing the key points. Respond ONLY with the summary, no preamble."
    ),
)

fact_checker_agent = Agent(
    client=OpenAIChatClient(),
    name="FactChecker",
    instructions=(
        "You are a fact-checking specialist. "
        "Given an input text, identify up to 3 key factual claims and, for each, "
        "state whether it is verifiably true, false, or uncertain based on "
        "widely available knowledge. Respond with a bulleted list."
    ),
)

sentiment_agent = Agent(
    client=OpenAIChatClient(),
    name="SentimentAnalyzer",
    instructions=(
        "You are a sentiment analysis specialist. "
        "Given an input text, classify the overall sentiment as positive, "
        "negative, neutral, or mixed. Include a confidence score between 0 and 1 "
        "and a one-line explanation. Respond with a single line."
    ),
)


# ---------------------------------------------------------------------------
# @tool wrappers -- expose sub-agents as callable tools
# ---------------------------------------------------------------------------


@tool(description="Summarize input text into 2-3 concise sentences.", approval_mode="never_require")
async def summarize(text: str) -> dict[str, Any]:
    """Run the summarizer sub-agent and return structured output."""
    result = await summarizer_agent.run(text)
    return {
        "agent": "summarizer",
        "status": "success",
        "summary": result.text.strip(),
    }


@tool(description="Fact-check up to 3 key claims in the input text.", approval_mode="never_require")
async def fact_check(text: str) -> dict[str, Any]:
    """Run the fact-checker sub-agent and return structured output."""
    result = await fact_checker_agent.run(
        f"Fact-check the following text. List up to 3 key claims and assess "
        f"each as true, false, or uncertain.\n\n{text}"
    )
    return {
        "agent": "fact_checker",
        "status": "success",
        "claims": result.text.strip(),
    }


@tool(
    description="Analyze the sentiment and tone of the input text.",
    approval_mode="never_require",
)
async def analyze_sentiment(text: str) -> dict[str, Any]:
    """Run the sentiment analyzer sub-agent and return structured output."""
    result = await sentiment_agent.run(
        f"Analyze the sentiment of the following text. Classify as positive, "
        f"negative, neutral, or mixed with a confidence score (0-1) and a "
        f"one-line explanation.\n\n{text}"
    )
    return {
        "agent": "sentiment_analyzer",
        "status": "success",
        "sentiment": result.text.strip(),
    }


# ---------------------------------------------------------------------------
# Supervisor agent -- synthesizes aggregated results into a final report
# ---------------------------------------------------------------------------

supervisor_agent = Agent(
    client=OpenAIChatClient(),
    name="ResearchSupervisor",
    instructions=(
        "You are a research supervisor who synthesizes findings from multiple "
        "specialist sub-agents. You receive structured results from a summarizer, "
        "a fact-checker, and a sentiment analyzer. Produce a clean, professional "
        "report that integrates all three analyses clearly."
    ),
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _extract_content(result: dict[str, Any]) -> str:
    """Extract the text content from a sub-agent result dict."""
    if result.get("status") == "error":
        return f"[ERROR: {result.get('error', 'unknown')}]"
    return (
        result.get("summary")
        or result.get("claims")
        or result.get("sentiment")
        or "[no content]"
    )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def main() -> None:
    print("=" * 70)
    print("  Agent-as-Tool: Parallel Sub-agent Execution with Structured Context")
    print("=" * 70)
    print()

    # Sample input text with multiple claims and varied sentiment
    input_text = (
        "Tesla's stock surged 15% last quarter, driven by record vehicle deliveries "
        "of 1.8 million units worldwide. Critics warn that growing competition from "
        "Chinese EV makers could erode market share. Separately, climate researchers "
        "report that global CO2 levels reached a new high of 425 ppm in 2024, "
        "exceeding the previous record by 3 ppm. The transition to renewable energy "
        "is accelerating, yet fossil fuel consumption also hit an all-time high. "
        "Meanwhile, the AI industry saw over $100 billion in venture funding this year, "
        "with breakthroughs in medical diagnostics and autonomous driving leading the way."
    )

    print("Input text:")
    print("-" * 70)
    print(input_text)
    print("-" * 70)
    print()

    # -----------------------------------------------------------------------
    # Run all three sub-agents in parallel with individual error handling
    # -----------------------------------------------------------------------

    async def safe_summarize() -> dict[str, Any]:
        try:
            return await summarize(input_text)
        except Exception as exc:
            return {"agent": "summarizer", "status": "error", "error": str(exc)}

    async def safe_fact_check() -> dict[str, Any]:
        try:
            return await fact_check(input_text)
        except Exception as exc:
            return {"agent": "fact_checker", "status": "error", "error": str(exc)}

    async def safe_analyze_sentiment() -> dict[str, Any]:
        try:
            return await analyze_sentiment(input_text)
        except Exception as exc:
            return {"agent": "sentiment_analyzer", "status": "error", "error": str(exc)}

    summary_result, fact_check_result, sentiment_result = await asyncio.gather(
        safe_summarize(),
        safe_fact_check(),
        safe_analyze_sentiment(),
    )

    # -----------------------------------------------------------------------
    # Display per-sub-agent results
    # -----------------------------------------------------------------------

    print("=" * 70)
    print("  INDIVIDUAL SUB-AGENT RESULTS")
    print("=" * 70)
    print()

    for idx, (label, result) in enumerate(
        [
            ("SUMMARIZER", summary_result),
            ("FACT CHECKER", fact_check_result),
            ("SENTIMENT ANALYZER", sentiment_result),
        ],
        1,
    ):
        print(f"  [{idx}] {label}")
        print(f"      Status : {result.get('status', 'unknown')}")
        if result.get("status") == "error":
            print(f"      Error  : {result['error']}")
        else:
            content = (
                result.get("summary")
                or result.get("claims")
                or result.get("sentiment")
                or ""
            )
            for line in content.split("\n"):
                print(f"      {line}")
        print()

    # -----------------------------------------------------------------------
    # Supervisor synthesizes a final report from aggregated results
    # -----------------------------------------------------------------------

    print("=" * 70)
    print("  SUPERVISOR SYNTHESIZED REPORT")
    print("=" * 70)
    print()

    synthesis_prompt = (
        "Synthesize the following findings from three specialist sub-agents into "
        "a single, well-structured final report.\n\n"
        f"=== Summarizer Result ===\n{_extract_content(summary_result)}\n\n"
        f"=== Fact Checker Result ===\n{_extract_content(fact_check_result)}\n\n"
        f"=== Sentiment Analyzer Result ===\n{_extract_content(sentiment_result)}\n\n"
        "Produce a final report with sections: Executive Summary, Key Facts, "
        "Sentiment Analysis, and Overall Assessment."
    )

    final_report = await supervisor_agent.run(synthesis_prompt)
    print(final_report.text)
    print()
    print("=" * 70)
    print("  Execution complete.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

======================================================================
  Agent-as-Tool: Parallel Sub-agent Execution with Structured Context
======================================================================

Input text:
----------------------------------------------------------------------
Tesla's stock surged 15% last quarter, driven by record vehicle deliveries
of 1.8 million units worldwide. Critics warn that growing competition from
...
----------------------------------------------------------------------

======================================================================
  INDIVIDUAL SUB-AGENT RESULTS
======================================================================

  [1] SUMMARIZER
      Status : success
      Tesla stock rose 15% on record 1.8M vehicle deliveries amid concern
      over Chinese EV competition. Global CO2 reached a record 425 ppm in
      2024 even as renewables accelerated. AI venture funding surpassed
      $100B with advances in medical diagnostics and autonomous driving.

  [2] FACT CHECKER
      Status : success
      - Claim: Tesla's stock surged 15% last quarter -- Uncertain ...
      - Claim: Global CO2 levels reached 425 ppm in 2024 -- True ...
      - Claim: AI industry saw over $100B in venture funding -- ...

  [3] SENTIMENT ANALYZER
      Status : success
      Mixed (confidence 0.8) -- Text contains both positive financial/AI
      milestones and concerning environmental warnings.

======================================================================
  SUPERVISOR SYNTHESIZED REPORT
======================================================================

Executive Summary
...
======================================================================
  Execution complete.
======================================================================
"""
