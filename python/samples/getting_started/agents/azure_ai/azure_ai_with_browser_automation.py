# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework.azure import AzureAIClient
from azure.identity.aio import AzureCliCredential

"""
Azure AI Agent with Browser Automation Example

This sample demonstrates usage of AzureAIClient with Browser Automation
to perform automated web browsing tasks and provide responses based on web interactions.

Prerequisites:
1. Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME environment variables.
2. Ensure you have a Browser Automation connection configured in your Azure AI project
   and set BROWSER_AUTOMATION_PROJECT_CONNECTION_ID environment variable.
"""


async def main() -> None:
    async with (
        AzureCliCredential() as credential,
        AzureAIClient(credential=credential).create_agent(
            name="MyBrowserAutomationAgent",
            instructions="""You are an Agent helping with browser automation tasks.
            You can answer questions, provide information, and assist with various tasks
            related to web browsing using the Browser Automation tool available to you.""",
            tools={
                "type": "browser_automation_preview",
                "browser_automation_preview": {
                    "connection": {
                        "project_connection_id": os.environ["BROWSER_AUTOMATION_PROJECT_CONNECTION_ID"],
                    }
                },
            },
        ) as agent,
    ):
        query = """Your goal is to report the percent of Microsoft year-to-date stock price change.
        To do that, go to the website finance.yahoo.com.
        At the top of the page, you will find a search bar.
        Enter the value 'MSFT', to get information about the Microsoft stock price.
        At the top of the resulting page you will see a default chart of Microsoft stock price.
        Click on 'YTD' at the top of that chart, and report the percent value that shows up just below it."""

        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Result: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
