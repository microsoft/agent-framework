# Copyright (c) Microsoft. All rights reserved.

import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# --- Tools the agent can call -------------------------------------------------

def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    conditions = ["sunny", "cloudy", "rainy", "windy", "snowy", "foggy"]
    temp_c = random.randint(-5, 35)
    sky = random.choice(conditions)
    return f"{location}: {temp_c}°C and {sky}"


def get_local_time(timezone: str = "UTC") -> str:
    """Get the current local time for an IANA timezone, e.g. 'Asia/Tokyo'."""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except Exception:
        return f"Unknown timezone '{timezone}'. Try something like 'Asia/Tokyo' or 'America/New_York'."
    return now.strftime("%A %H:%M") + f" ({timezone})"


def suggest_activity(location: str, weather: str) -> str:
    """Suggest something fun to do given a location and its weather."""
    indoor = ["visit a cozy museum", "hunt for the best ramen in town", "catch a movie", "browse a bookshop"]
    outdoor = ["take a scenic walk", "rent a bike", "find a rooftop view", "picnic in a park"]
    picks = indoor if any(w in weather.lower() for w in ("rain", "snow", "fog")) else outdoor
    return f"In {location}, you could {random.choice(picks)}."


# --- Agent --------------------------------------------------------------------

def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        name="Wanderbot",
        client=client,
        instructions=(
            "You are Wanderbot, a witty, upbeat travel buddy. "
            "You love helping people plan spontaneous adventures. "
            "Use your tools to check the weather and local time, then suggest a fun activity. "
            "Keep replies short, playful, and sprinkle in the occasional emoji."
        ),
        tools=[get_weather, get_local_time, suggest_activity],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
