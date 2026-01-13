# Copyright (c) Microsoft. All rights reserved.

"""Mock travel tools for demonstration purposes.

In a real application, these would call actual weather and events APIs.
"""

from typing import Annotated


def get_weather_forecast(
    destination: Annotated[str, "The destination city or location"],
    date: Annotated[str, 'The date for the forecast (e.g., "2025-01-15" or "next Monday")'],
) -> str:
    """Get the weather forecast for a destination on a specific date.

    Use this to provide weather-aware recommendations in the itinerary.

    Args:
        destination: The destination city or location.
        date: The date for the forecast.

    Returns:
        A weather forecast summary.
    """
    # Mock weather data based on destination for realistic responses
    weather_by_region = {
        "Tokyo": ("Partly cloudy with a chance of light rain", 58, 45),
        "Paris": ("Overcast with occasional drizzle", 52, 41),
        "New York": ("Clear and cold", 42, 28),
        "London": ("Foggy morning, clearing in afternoon", 48, 38),
        "Sydney": ("Sunny and warm", 82, 68),
        "Rome": ("Sunny with light breeze", 62, 48),
        "Barcelona": ("Partly sunny", 59, 47),
        "Amsterdam": ("Cloudy with light rain", 46, 38),
        "Dubai": ("Sunny and hot", 85, 72),
        "Singapore": ("Tropical thunderstorms in afternoon", 88, 77),
        "Bangkok": ("Hot and humid, afternoon showers", 91, 78),
        "Los Angeles": ("Sunny and pleasant", 72, 55),
        "San Francisco": ("Morning fog, afternoon sun", 62, 52),
        "Seattle": ("Rainy with breaks", 48, 40),
        "Miami": ("Warm and sunny", 78, 65),
        "Honolulu": ("Tropical paradise weather", 82, 72),
    }

    # Find a matching destination or use a default
    forecast = ("Partly cloudy", 65, 50)
    for city, weather in weather_by_region.items():
        if city.lower() in destination.lower():
            forecast = weather
            break

    condition, high_f, low_f = forecast
    high_c = (high_f - 32) * 5 // 9
    low_c = (low_f - 32) * 5 // 9

    recommendation = _get_weather_recommendation(condition)

    return f"""Weather forecast for {destination} on {date}:
Conditions: {condition}
High: {high_f}°F ({high_c}°C)
Low: {low_f}°F ({low_c}°C)

Recommendation: {recommendation}"""


def get_local_events(
    destination: Annotated[str, "The destination city or location"],
    date: Annotated[str, 'The date to search for events (e.g., "2025-01-15" or "next week")'],
) -> str:
    """Get local events and activities happening at a destination around a specific date.

    Use this to suggest timely activities and experiences.

    Args:
        destination: The destination city or location.
        date: The date to search for events.

    Returns:
        A list of local events and activities.
    """
    # Mock events data based on destination
    events_by_city = {
        "Tokyo": [
            "🎭 Kabuki Theater Performance at Kabukiza Theatre - Traditional Japanese drama",
            "🌸 Winter Illuminations at Yoyogi Park - Spectacular light displays",
            "🍜 Ramen Festival at Tokyo Station - Sample ramen from across Japan",
            "🎮 Gaming Expo at Tokyo Big Sight - Latest video games and technology",
        ],
        "Paris": [
            "🎨 Impressionist Exhibition at Musée d'Orsay - Extended evening hours",
            "🍷 Wine Tasting Tour in Le Marais - Local sommelier guided",
            "🎵 Jazz Night at Le Caveau de la Huchette - Historic jazz club",
            "🥐 French Pastry Workshop - Learn from master pâtissiers",
        ],
        "New York": [
            "🎭 Broadway Show: Hamilton - Limited engagement performances",
            "🏀 Knicks vs Lakers at Madison Square Garden",
            "🎨 Modern Art Exhibit at MoMA - New installations",
            "🍕 Pizza Walking Tour of Brooklyn - Artisan pizzerias",
        ],
        "London": [
            "👑 Royal Collection Exhibition at Buckingham Palace",
            "🎭 West End Musical: The Phantom of the Opera",
            "🍺 Craft Beer Festival at Brick Lane",
            "🎪 Winter Wonderland at Hyde Park - Rides and markets",
        ],
        "Sydney": [
            "🏄 Pro Surfing Competition at Bondi Beach",
            "🎵 Opera at Sydney Opera House - La Bohème",
            "🦘 Wildlife Night Safari at Taronga Zoo",
            "🍽️ Harbor Dinner Cruise with fireworks",
        ],
        "Rome": [
            "🏛️ After-Hours Vatican Tour - Skip the crowds",
            "🍝 Pasta Making Class in Trastevere",
            "🎵 Classical Concert at Borghese Gallery",
            "🍷 Wine Tasting in Roman Cellars",
        ],
    }

    # Find events for the destination or use generic events
    events = [
        "🎭 Local theater performance",
        "🍽️ Food and wine festival",
        "🎨 Art gallery opening",
        "🎵 Live music at local venues",
    ]

    for city, city_events in events_by_city.items():
        if city.lower() in destination.lower():
            events = city_events
            break

    event_list = "\n• ".join(events)
    return f"""Local events in {destination} around {date}:

• {event_list}

💡 Tip: Book popular events in advance as they may sell out quickly!"""


def _get_weather_recommendation(condition: str) -> str:
    """Get a recommendation based on weather conditions.

    Args:
        condition: The weather condition description.

    Returns:
        A recommendation string.
    """
    condition_lower = condition.lower()

    if "rain" in condition_lower or "drizzle" in condition_lower:
        return "Bring an umbrella and waterproof jacket. Consider indoor activities for backup."
    elif "fog" in condition_lower:
        return "Morning visibility may be limited. Plan outdoor sightseeing for afternoon."
    elif "cold" in condition_lower:
        return "Layer up with warm clothing. Hot drinks and cozy cafés recommended."
    elif "hot" in condition_lower or "warm" in condition_lower:
        return "Stay hydrated and use sunscreen. Plan strenuous activities for cooler morning hours."
    elif "thunder" in condition_lower or "storm" in condition_lower:
        return "Keep an eye on weather updates. Have indoor alternatives ready."
    else:
        return "Pleasant conditions expected. Great day for outdoor exploration!"
