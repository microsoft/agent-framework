# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from typing import Annotated, Any, cast

from agent_framework import Agent, Message, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Sample: Global Workflow kwargs

This sample demonstrates how to pass the same kwargs to every agent in a
workflow using global targeting. When keys in function_invocation_kwargs do NOT
match any executor ID (agent name), the framework treats them as global and
delivers them to all agents.

Compare with workflow_kwargs_per_agent.py which targets kwargs to specific agents.

Key Concepts:
- Global function_invocation_kwargs are delivered to every agent in the workflow
- Useful when all agents share the same credentials, config, or context
- @tool functions receive kwargs via the **kwargs parameter

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Environment variables configured
"""


# 1. Define a tool for the research agent — queries a company's internal
#    database using credentials passed via global kwargs.
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def query_company_database(
    query: Annotated[
        str, Field(description="The database query to run, e.g. 'Q3 revenue' or 'headcount by department'")
    ],
    **kwargs: Any,
) -> str:
    """Query the company's internal database for business metrics and data."""
    db_config = kwargs.get("db_config", {})
    connection_string = db_config.get("connection_string", "")
    database = db_config.get("database", "")

    if not connection_string or not database:
        return f"ERROR: missing db_config — cannot run query '{query}'"

    print(f"\n  [query_company_database] Connecting to {database} at {connection_string[:30]}...")

    # Simulated company data that the LLM would not know on its own
    return (
        f"Query results from {database}:\n"
        f"- Contoso Q3 2025 revenue: $47.2M (up 12% YoY)\n"
        f"- Top product line: CloudSync Pro ($18.6M)\n"
        f"- Engineering headcount: 342 (up from 298 in Q2)\n"
        f"- Customer churn rate: 4.1% (down from 5.3% in Q2)\n"
        f"- Net new enterprise customers: 28"
    )


# 2. Define a tool for the writer agent — retrieves the formatting style
#    from user preferences passed via global kwargs.
@tool(approval_mode="never_require")
def get_formatting_instructions(
    section_title: Annotated[str, Field(description="The title of the section or report to format")],
    **kwargs: Any,
) -> str:
    """Get the formatting instructions based on user preferences."""
    user_prefs = kwargs.get("user_preferences", {})
    output_format = user_prefs.get("format", "plain")
    language = user_prefs.get("language", "en")

    print(f"\n  [get_formatting_instructions] Format: {output_format}, Language: {language}")

    return (
        f"Formatting rules for '{section_title}':\n"
        f"- Output format: {output_format}\n"
        f"- Language/locale: {language}\n"
        f"- Include a footer: 'Generated in {output_format} for locale {language}'"
    )


async def main() -> None:
    print("=" * 70)
    print("Global Workflow kwargs Demo")
    print("=" * 70)

    # 3. Create a shared chat client.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # 4. Create two agents with different tools and responsibilities.
    researcher = Agent(
        client=client,
        name="researcher",
        instructions=(
            "You are a data analyst. Call query_company_database exactly once "
            "with the user's request as the query. Return the raw results."
        ),
        tools=[query_company_database],
    )

    writer = Agent(
        client=client,
        name="writer",
        instructions=(
            "You are a report writer. Call get_formatting_instructions exactly once, "
            "then rewrite the data you receive into a polished report following those rules."
        ),
        tools=[get_formatting_instructions],
    )

    # 5. Build a sequential workflow: researcher -> writer.
    workflow = SequentialBuilder(participants=[researcher, writer]).build()

    # 6. Define global kwargs — every agent receives all of these.
    #    Because the keys ("db_config", "user_preferences") do NOT match any
    #    executor ID ("researcher", "writer"), the framework treats them as
    #    global and delivers the full dict to every agent.
    global_fi_kwargs = {
        "db_config": {
            "connection_string": "Server=contoso-sql.database.windows.net;Database=metrics",
            "database": "contoso_metrics_prod",
        },
        "user_preferences": {
            "format": "markdown",
            "language": "en-US",
        },
    }

    print("\nGlobal function_invocation_kwargs (sent to all agents):")
    print(json.dumps(global_fi_kwargs, indent=2))
    print("\n" + "-" * 70)
    print("Workflow Execution:")
    print("-" * 70)

    # 7. Run the workflow — every agent receives the same global kwargs.
    async for event in workflow.run(
        "Pull Contoso's Q3 2025 performance data and write an executive summary.",
        function_invocation_kwargs=global_fi_kwargs,
        stream=True,
    ):
        if event.type == "output":
            output_data = cast(list[Message], event.data)
            if isinstance(output_data, list):
                for item in output_data:
                    if isinstance(item, Message) and item.text:
                        print(f"\n[{item.author_name}]: {item.text}")

    print("\n" + "=" * 70)
    print("Sample Complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
