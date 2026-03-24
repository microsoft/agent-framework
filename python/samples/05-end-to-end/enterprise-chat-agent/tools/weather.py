"""
Weather Tool

Provides weather information for a given location.
In a production scenario, this would integrate with a weather API.
"""

import random

from agent_framework import tool


@tool
def get_weather(location: str) -> dict:
    """
    Get current weather for a location.

    Args:
        location: The city or location to get weather for.

    Returns:
        A dictionary containing temperature and weather condition.
    """
    # Simulated weather data (replace with actual API call in production)
    conditions = ["sunny", "cloudy", "light rain", "partly cloudy", "overcast"]

    return {
        "location": location,
        "temp": random.randint(32, 85),
        "condition": random.choice(conditions),
        "humidity": random.randint(30, 90),
        "unit": "fahrenheit",
    }
