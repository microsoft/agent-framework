# Copyright (c) Microsoft. All rights reserved.

"""Harness Research Assistant.

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
a simple interactive chat loop. The agent will plan research tasks using todos,
switch between plan and execute modes, search the web for current information,
and track its progress.

Special commands:
    /exit  — End the session.

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
from dotenv import load_dotenv

RESEARCH_INSTRUCTIONS = """\
## Research Assistant Instructions

You are a research assistant. When given a research topic, research it thoroughly using web search and web browsing.
Use your knowledge to form good search queries and hypotheses, but always verify claims with the tools available to you rather than relying on memory alone.

### Research quality

Consult multiple sources when possible and cross-reference key claims.
When sources disagree, note the discrepancy and explain which source you consider more reliable and why.
If a web page fails to load or a search returns irrelevant results, try alternative search queries or sources before moving on.
Track your sources — you will need them when presenting results.

### Presenting results

When presenting your final findings:
- Use Markdown formatting for clarity.
- Use clear sections with headings for each major topic or sub-question.
- Cite your sources inline (e.g., "According to [source name](URL), ...").
- End with a brief summary of key takeaways.
- In addition to returning the results to the user, save the final research report to file memory so it survives compaction and can be referenced later.
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

    # Create a session to maintain conversation state across turns.
    session = agent.create_session()

    print("Research Assistant (powered by create_harness_agent)")
    print("=" * 50)
    print("Enter a research topic to get started.")
    print("Type /exit to end the session.\n")

    # Simple interactive chat loop.
    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "/exit":
            print("\nGoodbye!")
            break

        # Run the agent with streaming and print the response as it arrives.
        print("\nAssistant: ", end="", flush=True)
        async for update in agent.run(user_input, session=session, stream=True):
            if update.contents:
                for content in update.contents:
                    # Print a brief message for each tool call in the stream.
                    if content.type == "function_call":
                        print(f"\n  [calling tool: {content.name}]", flush=True)
                        print("  ", end="", flush=True)
                    # Show web search activity when the result arrives with action details.
                    elif content.type in ("search_tool_call", "search_tool_result") and getattr(content, "tool_name", None) == "web_search":
                        action = None
                        if content.type == "search_tool_result" and isinstance(content.result, dict):
                            action = content.result.get("action", {})
                        elif content.type == "search_tool_call":
                            action = content.arguments if isinstance(content.arguments, dict) else None
                        if action:
                            action_type = action.get("type", "search")
                            if action_type == "search":
                                queries = action.get("queries") or []
                                query_str = ", ".join(f'"{q}"' for q in queries) if queries else action.get("query", "")
                                print(f"\n  🌐 Web search: {query_str}", flush=True)
                                print("  ", end="", flush=True)
                            elif action_type == "open_page":
                                url = action.get("url", "(unknown)")
                                print(f"\n  🌐 Opening: {url}", flush=True)
                                print("  ", end="", flush=True)
                            elif action_type == "find_in_page":
                                pattern = action.get("pattern", "")
                                print(f'\n  🌐 Find in page: "{pattern}"', flush=True)
                                print("  ", end="", flush=True)
                            else:
                                print(f"\n  🌐 Web search: {action_type}", flush=True)
                                print("  ", end="", flush=True)
            # Print text content as it streams in.
            if update.text:
                print(update.text, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
