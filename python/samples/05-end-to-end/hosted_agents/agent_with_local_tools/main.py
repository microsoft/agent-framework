# Copyright (c) Microsoft. All rights reserved.

"""
Seattle Hotel Agent - A simple agent with a tool to find hotels in Seattle.
Uses Microsoft Agent Framework with Azure AI Foundry.
Ready for deployment to Foundry Hosted Agent service.
"""

import asyncio
import os
from datetime import datetime
from typing import Annotated

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential

# Configure these for your Foundry project
# Read the explicit variables present in the .env file
FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT")  # e.g., "https://<project>.services.ai.azure.com"
FOUNDRY_MODEL = os.getenv("FOUNDRY_MODEL", "gpt-4.1-mini")  # Your model deployment name e.g., "gpt-4.1-mini"


# Simulated hotel data for Seattle
SEATTLE_HOTELS = [
    {
        "name": "Contoso Suites",
        "price_per_night": 189,
        "rating": 4.5,
        "location": "Downtown",
    },
    {
        "name": "Fabrikam Residences",
        "price_per_night": 159,
        "rating": 4.2,
        "location": "Pike Place Market",
    },
    {
        "name": "Alpine Ski House",
        "price_per_night": 249,
        "rating": 4.7,
        "location": "Seattle Center",
    },
    {
        "name": "Margie's Travel Lodge",
        "price_per_night": 219,
        "rating": 4.4,
        "location": "Waterfront",
    },
    {
        "name": "Northwind Inn",
        "price_per_night": 139,
        "rating": 4.0,
        "location": "Capitol Hill",
    },
    {
        "name": "Relecloud Hotel",
        "price_per_night": 99,
        "rating": 3.8,
        "location": "University District",
    },
]


def get_available_hotels(
    check_in_date: Annotated[str, "Check-in date in YYYY-MM-DD format"],
    check_out_date: Annotated[str, "Check-out date in YYYY-MM-DD format"],
    max_price: Annotated[int, "Maximum price per night in USD (optional)"] = 500,
) -> str:
    """
    Get available hotels in Seattle for the specified dates.
    This simulates a call to a fake hotel availability API.
    """
    try:
        # Parse dates
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
        check_out = datetime.strptime(check_out_date, "%Y-%m-%d")

        # Validate dates
        if check_out <= check_in:
            return "Error: Check-out date must be after check-in date."

        nights = (check_out - check_in).days

        # Filter hotels by price
        available_hotels = [hotel for hotel in SEATTLE_HOTELS if hotel["price_per_night"] <= max_price]

        if not available_hotels:
            return f"No hotels found in Seattle within your budget of ${max_price}/night."

        # Build response
        result = f"Available hotels in Seattle from {check_in_date} to {check_out_date} ({nights} nights):\n\n"

        for hotel in available_hotels:
            total_cost = hotel["price_per_night"] * nights
            result += f"**{hotel['name']}**\n"
            result += f"   Location: {hotel['location']}\n"
            result += f"   Rating: {hotel['rating']}/5\n"
            result += f"   ${hotel['price_per_night']}/night (Total: ${total_cost})\n\n"

        return result

    except ValueError as e:
        return f"Error parsing dates. Please use YYYY-MM-DD format. Details: {str(e)}"


def get_credential():
    """Will use Managed Identity when running in Azure, otherwise falls back to Azure CLI Credential."""
    return ManagedIdentityCredential() if os.getenv("MSI_ENDPOINT") else AzureCliCredential()


async def main():
    """Main function to run the agent as a web server."""
    async with get_credential() as credential:
        client = FoundryChatClient(
            project_endpoint=FOUNDRY_PROJECT_ENDPOINT,
            model=FOUNDRY_MODEL,
            credential=credential,
        )
        agent = Agent(
            client=client,
            name="SeattleHotelAgent",
            instructions="""You are a helpful travel assistant specializing in finding hotels in Seattle, Washington.

When a user asks about hotels in Seattle:
1. Ask for their check-in and check-out dates if not provided
2. Ask about their budget preferences if not mentioned
3. Use the get_available_hotels tool to find available options
4. Present the results in a friendly, informative way
5. Offer to help with additional questions about the hotels or Seattle

Be conversational and helpful. If users ask about things outside of Seattle hotels,
politely let them know you specialize in Seattle hotel recommendations.""",
            tools=[get_available_hotels],
        )

        print("Seattle Hotel Agent Server running on http://localhost:8088")
        server = from_agent_framework(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
