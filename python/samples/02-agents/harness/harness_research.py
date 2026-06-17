# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework",
#     "textual>=6.2.1",
#     "rich>=13.7.1",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/02-agents/harness/harness_research.py

# Copyright (c) Microsoft. All rights reserved.

"""Harness Research Assistant with Console UI.

Demonstrates ``create_harness_agent`` — a factory function that builds a
pre-configured agent with batteries included, automatically wiring up function
invocation, per-service-call history persistence, compaction, and a rich set of
context providers:

- **TodoProvider** — the agent can create, track, and complete work items
- **AgentModeProvider** — plan/execute mode tracking (interactive vs. autonomous)
- **SkillsProvider** — file-based skill discovery and progressive loading
- **CompactionProvider** — automatic context-window management
- **InMemoryHistoryProvider** — session history with per-service-call persistence
- **OpenTelemetry** — built-in observability via AgentTelemetryLayer
- **Web Search** — real-time web search via ``get_web_search_tool()``

The sample creates a research-focused agent with web search capability and runs
it inside the Textual-based harness console. The agent will plan research tasks
using todos, switch between plan and execute modes, search the web for current
information, and track its progress.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""

import asyncio

from agent_framework import create_harness_agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from console import build_observers_with_planning, run_agent_async
from dotenv import load_dotenv

RESEARCH_INSTRUCTIONS = """\
## Research Assistant Instructions

You are a research assistant. When given a research topic, research it
thoroughly using web search and web browsing. Use your knowledge to form good
search queries and hypotheses, but always verify claims with the tools
available to you rather than relying on memory alone.

### Research quality

Consult multiple sources when possible and cross-reference key claims.
When sources disagree, note the discrepancy and explain which source you
consider more reliable and why.
If a web page fails to load or a search returns irrelevant results, try
alternative search queries or sources before moving on.
Track your sources — you will need them when presenting results.

### Presenting results

When presenting your final findings:
- Use Markdown formatting for clarity.
- Use clear sections with headings for each major topic or sub-question.
- Cite your sources inline (e.g., "According to [source name](URL), ...").
- End with a brief summary of key takeaways.
- In addition to returning the results to the user, save the final research
  report to file memory so it survives compaction and can be referenced later.
"""


async def main() -> None:
    load_dotenv()

    # Create the chat client.
    # For authentication, run `az login` in terminal or replace AzureCliCredential
    # with your preferred authentication option.
    client = FoundryChatClient(credential=AzureCliCredential())

    # Create a harness agent with research-specific instructions.
    # All other features (todo, mode, compaction, skills, telemetry, web search) are
    # automatically configured with sensible defaults.
    agent = create_harness_agent(
        client=client,
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
        name="ResearchAgent",
        description="A research assistant that plans and executes research tasks.",
        agent_instructions=RESEARCH_INSTRUCTIONS,
    )

    # Run the harness console with the research agent.
    await run_agent_async(
        agent,
        session=agent.create_session(),
        observers=build_observers_with_planning(agent),
        initial_mode="plan",
        title="🔬 Research Assistant",
        placeholder="Enter a research topic...",
        max_context_window_tokens=128_000,
        max_output_tokens=16_384,
    )


if __name__ == "__main__":
    asyncio.run(main())
