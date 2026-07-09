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
#   uv run samples/02-agents/harness/harness_data_processing.py

# Copyright (c) Microsoft. All rights reserved.

"""Harness Data Processing Assistant with Console UI and tool approvals.

Demonstrates ``create_harness_agent`` configured with a ``FileAccessProvider``
to give an agent access to a folder of CSV data files. The agent can read,
analyze, and extract information from the data, then write results back as new
files via the ``file_access_*`` tools.

This sample also demonstrates **tool approval**. The ``FileAccessProvider``
registers all of its tools with ``approval_mode="always_require"``, so every
file operation would normally prompt the host for approval. To keep read-only
exploration frictionless while still guarding mutations, the agent is given the
:meth:`FileAccessProvider.read_only_tools_auto_approval_rule` auto-approval
rule. With this rule:

- Read-only tools (read, list files, list subdirectories, search) are
  auto-approved and run without prompting.
- Write tools (save and delete) still require explicit approval, so you are
  asked before the agent modifies the file store.

The sample includes a pre-populated ``working/`` folder with sales transaction
data. The ``FileAccessProvider`` is pointed at that folder (resolved relative to
this script) so it works regardless of the current working directory. Ask the
agent to analyze the data, produce summaries, or create new output files. For
example::

    Please process the sales.csv file by first filtering it to only North region
    sales, and then calculating the sum of sales by person. I'd like to write the
    results of the processing to north_region_totals.csv

When the agent reads ``sales.csv`` it proceeds automatically, but when it tries
to save ``north_region_totals.csv`` you are prompted to approve the write.

Unused harness features (todos, plan/execute mode, web search) are disabled to
keep this a simple, conversational data-interaction sample.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Azure AI Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""

import asyncio
from pathlib import Path

from agent_framework import FileAccessProvider, FileSystemAgentFileStore, create_harness_agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from console import build_default_observers, run_agent_async
from dotenv import load_dotenv

DATA_ANALYST_INSTRUCTIONS = """\
You are a data analyst assistant. You have access to a folder of data files via the file_access_* tools.

## Getting started
- Start by listing available files with file_access_ls to see what data is available.
- Read the files to understand their structure and contents.

## Working with data
- When asked to analyze data, read the relevant files first, then perform the analysis.
- Show your analysis clearly with tables, summaries, and key insights.
- When calculations are needed, work through them step by step and show your reasoning.

## Writing output
- When asked to produce output files (e.g., reports, summaries, filtered data), use file_access_write to write them.
- Use appropriate file formats: CSV for tabular data, Markdown for reports.
- Confirm what you wrote and where.

## Important
- Never modify or delete the original input data files unless explicitly asked to do so.
- If asked about data you haven't read yet, read it first before answering.
- Always explain your reasoning and thought process as you work through tasks.
- Always explain what you learned and what you are going to do next between tool calls, so the user can
  follow along with your thought process.
"""

MAX_CONTEXT_WINDOW_TOKENS = 1_050_000
MAX_OUTPUT_TOKENS = 128_000


async def main() -> None:
    load_dotenv()

    # Resolve the working/ folder bundled alongside this script. The agent reads
    # the seed data from here and writes any output files back into it.
    working_dir = Path(__file__).parent / "working"

    # Create the chat client.
    # For authentication, run `az login` in terminal or replace AzureCliCredential
    # with your preferred authentication option.
    client = FoundryChatClient(credential=AzureCliCredential())

    # Create a harness agent with data-analyst instructions. Unused features are
    # disabled. The read_only_tools_auto_approval_rule auto-approves the
    # FileAccessProvider's read-only tools, so only write operations prompt.
    agent = create_harness_agent(
        client=client,
        max_context_window_tokens=MAX_CONTEXT_WINDOW_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        name="DataAnalyst",
        description="A data analyst assistant that reads, analyzes, and processes data files.",
        agent_instructions=DATA_ANALYST_INSTRUCTIONS,
        file_access_store=FileSystemAgentFileStore(working_dir),
        auto_approval_rules=[FileAccessProvider.read_only_tools_auto_approval_rule],
        disable_todo=True,
        disable_mode=True,
        disable_web_search=True,
    )

    # Run the harness console. This sample has no plan/execute mode, so it uses
    # the default observers (no planning observer) and no initial mode.
    await run_agent_async(
        agent,
        session=agent.create_session(),
        observers=build_default_observers(),
        title="📊 Data Analyst",
        placeholder="Ask me to analyze the data files, produce summaries, or create output files...",
        max_context_window_tokens=MAX_CONTEXT_WINDOW_TOKENS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


if __name__ == "__main__":
    asyncio.run(main())
