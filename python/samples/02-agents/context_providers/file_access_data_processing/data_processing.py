# Copyright (c) Microsoft. All rights reserved.

"""Sample: use ``FileAccessProvider`` to give an agent access to a folder of CSV data files.

This sample demonstrates how to attach :class:`FileAccessProvider` (backed by
:class:`FileSystemAgentFileStore`) to an ``Agent`` so the model can read input
data, perform analysis, and write summary output back to the same folder via
the ``file_access_*`` tools.

The sibling ``working/`` folder contains ``sales.csv`` — ~50 rows of sales
transactions (date, product, category, quantity, unit_price, region,
salesperson). The agent is asked, in a single session, to: list available
files, inspect the data, compute regional totals, and save a markdown summary.

Prerequisites:
    - ``FOUNDRY_PROJECT_ENDPOINT``: Your Azure AI Foundry project endpoint.
    - ``FOUNDRY_MODEL``: Chat model deployment name.
    - Run ``az login`` before executing the sample.
"""

import asyncio
import os
from pathlib import Path

from agent_framework import Agent, FileAccessProvider, FileSystemAgentFileStore
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load python/.env (python-dotenv walks up from this file by default). Pass
# override=True so values from .env take precedence over any pre-existing OS
# environment variables — without this, OS-level values silently win.
load_dotenv(override=True)

INSTRUCTIONS = """
You are a data analyst assistant. You have access to a folder of data files via
the file_access_* tools.

## Getting started
- Start by listing available files with file_access_list_files to see what data
  is available.
- Read the files to understand their structure and contents.

## Working with data
- When asked to analyze data, read the relevant files first, then perform the
  analysis.
- Show your analysis clearly with tables, summaries, and key insights.
- When calculations are needed, work through them step by step and show your
  reasoning.

## Writing output
- When asked to produce output files (e.g., reports, summaries, filtered data),
  use file_access_save_file to write them.
- Use appropriate file formats: CSV for tabular data, Markdown for reports.
- Confirm what you wrote and where.

## Important
- Never modify or delete the original input data files unless explicitly asked
  to do so.
- If asked about data you haven't read yet, read it first before answering.
- Always explain your reasoning between tool calls so the user can follow along.
"""

PROMPTS = [
    "What files do you have access to?",
    "Read sales.csv and summarize what columns it contains and how many rows it has.",
    "Calculate the total revenue (quantity * unit_price) per region and show the result as a table.",
    (
        "Save a markdown report named region_totals.md that contains the regional totals "
        "and a one-paragraph summary of which region performed best."
    ),
    "List the files again so I can confirm region_totals.md was created.",
]


async def main() -> None:
    # 1. Resolve the working directory bundled alongside this script.
    working_dir = Path(__file__).parent / "working"

    # 2. Build the chat client.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # 3. Wire up the file access provider against a file-system-backed store
    #    rooted at the sample's working/ folder. The provider injects its
    #    default instructions plus exposes five file_access_* tools to the
    #    agent for the duration of each run.
    file_access = FileAccessProvider(store=FileSystemAgentFileStore(working_dir))

    # 4. Create the agent and attach the provider.
    async with Agent(
        client=client,
        name="DataAnalyst",
        description="A data analyst assistant that reads, analyzes, and processes data files.",
        instructions=INSTRUCTIONS,
        context_providers=[file_access],
    ) as agent:
        # 5. Run all prompts inside one session so the conversation remains
        #    coherent across turns.
        session = agent.create_session()
        for prompt in PROMPTS:
            print(f"\nUser: {prompt}")
            response = await agent.run(prompt, session=session)
            print(f"Assistant: {response}")

    # 6. Show the final folder contents so the side effects of the run are
    #    visible to the reader.
    print("\nFinal contents of working/:")
    for path in sorted(working_dir.iterdir()):
        print(f"  - {path.name} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())


# Sample output (truncated):
#
# User: What files do you have access to?
# Assistant: I can see one file in the working directory: sales.csv.
#
# User: Read sales.csv and summarize what columns it contains and how many rows it has.
# Assistant: sales.csv has 50 data rows and 7 columns: date, product, category,
# quantity, unit_price, region, salesperson.
#
# User: Calculate the total revenue (quantity * unit_price) per region and show the result as a table.
# Assistant:
# | Region | Total Revenue |
# |--------|---------------|
# | North  | $X,XXX.XX     |
# | South  | $X,XXX.XX     |
# | West   | $X,XXX.XX     |
#
# User: Save a markdown report named region_totals.md ...
# Assistant: I wrote region_totals.md to the working folder.
#
# User: List the files again so I can confirm region_totals.md was created.
# Assistant: The working folder now contains: region_totals.md, sales.csv.
#
# Final contents of working/:
#   - region_totals.md (NNN bytes)
#   - sales.csv (3175 bytes)
