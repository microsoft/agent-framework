# Copyright (c) Microsoft. All rights reserved.

"""Weather widget rendering for ChatKit integration sample."""

import base64
from dataclasses import dataclass

from chatkit.actions import ActionConfig
from chatkit.widgets import Box, Button, Card, Col, Image, Row, Text, Title, WidgetRoot

WEATHER_ICON_COLOR = "#1D4ED8"
WEATHER_ICON_ACCENT = "#DBEAFE"

# Popular cities for the selector
POPULAR_CITIES = [
    {"value": "seattle", "label": "Seattle, WA", "description": "Pacific Northwest"},
    {"value": "new_york", "label": "New York, NY", "description": "East Coast"},
    {"value": "san_francisco", "label": "San Francisco, CA", "description": "Bay Area"},
    {"value": "chicago", "label": "Chicago, IL", "description": "Midwest"},
    {"value": "miami", "label": "Miami, FL", "description": "Southeast"},
    {"value": "austin", "label": "Austin, TX", "description": "Southwest"},
    {"value": "boston", "label": "Boston, MA", "description": "New England"},
    {"value": "denver", "label": "Denver, CO", "description": "Mountain West"},
    {"value": "portland", "label": "Portland, OR", "description": "Pacific Northwest"},
    {"value": "atlanta", "label": "Atlanta, GA", "description": "Southeast"},
]

# Mapping from city values to display names for weather queries
CITY_VALUE_TO_NAME = {city["value"]: city["label"] for city in POPULAR_CITIES}


def _sun_svg() -> str:
    """Generate SVG for sunny weather icon."""
    color = WEATHER_ICON_COLOR
    accent = WEATHER_ICON_ACCENT
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        f'<circle cx="32" cy="32" r="13" fill="{accent}" stroke="{color}" stroke-width="3"/>'
        f'<g stroke="{color}" stroke-width="3" stroke-linecap="round">'
        '<line x1="32" y1="8" x2="32" y2="16"/>'
        '<line x1="32" y1="48" x2="32" y2="56"/>'
        '<line x1="8" y1="32" x2="16" y2="32"/>'
        '<line x1="48" y1="32" x2="56" y2="32"/>'
        '<line x1="14.93" y1="14.93" x2="20.55" y2="20.55"/>'
        '<line x1="43.45" y1="43.45" x2="49.07" y2="49.07"/>'
        '<line x1="14.93" y1="49.07" x2="20.55" y2="43.45"/>'
        '<line x1="43.45" y1="20.55" x2="49.07" y2="14.93"/>'
        "</g>"
        "</svg>"
    )


def _cloud_svg() -> str:
    """Generate SVG for cloudy weather icon."""
    color = WEATHER_ICON_COLOR
    accent = WEATHER_ICON_ACCENT
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        f'<path d="M22 46H44C50.075 46 55 41.075 55 35S50.075 24 44 24H42.7C41.2 16.2 34.7 10 26.5 10 18 10 11.6 16.1 11 24.3 6.5 25.6 3 29.8 3 35s4.925 11 11 11h8Z" '
        f'fill="{accent}" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>'
        "</svg>"
    )


def _rain_svg() -> str:
    """Generate SVG for rainy weather icon."""
    color = WEATHER_ICON_COLOR
    accent = WEATHER_ICON_ACCENT
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        f'<path d="M22 40H44C50.075 40 55 35.075 55 29S50.075 18 44 18H42.7C41.2 10.2 34.7 4 26.5 4 18 4 11.6 10.1 11 18.3 6.5 19.6 3 23.8 3 29s4.925 11 11 11h8Z" '
        f'fill="{accent}" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>'
        f'<g stroke="{color}" stroke-width="3" stroke-linecap="round">'
        '<line x1="20" y1="48" x2="24" y2="56"/>'
        '<line x1="30" y1="50" x2="34" y2="58"/>'
        '<line x1="40" y1="48" x2="44" y2="56"/>'
        "</g>"
        "</svg>"
    )


def _storm_svg() -> str:
    """Generate SVG for stormy weather icon."""
    color = WEATHER_ICON_COLOR
    accent = WEATHER_ICON_ACCENT
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        f'<path d="M22 40H44C50.075 40 55 35.075 55 29S50.075 18 44 18H42.7C41.2 10.2 34.7 4 26.5 4 18 4 11.6 10.1 11 18.3 6.5 19.6 3 23.8 3 29s4.925 11 11 11h8Z" '
        f'fill="{accent}" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>'
        f'<path d="M34 46L28 56H34L30 64L42 50H36L40 46Z" '
        f'fill="{color}" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
        "</svg>"
    )


def _snow_svg() -> str:
    """Generate SVG for snowy weather icon."""
    color = WEATHER_ICON_COLOR
    accent = WEATHER_ICON_ACCENT
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        f'<path d="M22 40H44C50.075 40 55 35.075 55 29S50.075 18 44 18H42.7C41.2 10.2 34.7 4 26.5 4 18 4 11.6 10.1 11 18.3 6.5 19.6 3 23.8 3 29s4.925 11 11 11h8Z" '
        f'fill="{accent}" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>'
        f'<g stroke="{color}" stroke-width="2" stroke-linecap="round">'
        '<line x1="20" y1="48" x2="20" y2="56"/>'
        '<line x1="17" y1="51" x2="23" y2="53"/>'
        '<line x1="17" y1="53" x2="23" y2="51"/>'
        '<line x1="36" y1="48" x2="36" y2="56"/>'
        '<line x1="33" y1="51" x2="39" y2="53"/>'
        '<line x1="33" y1="53" x2="39" y2="51"/>'
        "</g>"
        "</svg>"
    )


def _fog_svg() -> str:
    """Generate SVG for foggy weather icon."""
    color = WEATHER_ICON_COLOR
    accent = WEATHER_ICON_ACCENT
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        f'<path d="M22 40H44C50.075 40 55 35.075 55 29S50.075 18 44 18H42.7C41.2 10.2 34.7 4 26.5 4 18 4 11.6 10.1 11 18.3 6.5 19.6 3 23.8 3 29s4.925 11 11 11h8Z" '
        f'fill="{accent}" stroke="{color}" stroke-width="3" stroke-linejoin="round"/>'
        f'<g stroke="{color}" stroke-width="3" stroke-linecap="round">'
        '<line x1="18" y1="50" x2="42" y2="50"/>'
        '<line x1="24" y1="56" x2="48" y2="56"/>'
        "</g>"
        "</svg>"
    )


def _encode_svg(svg: str) -> str:
    """Encode SVG as base64 data URI."""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


# Weather condition to icon mapping
WEATHER_ICONS = {
    "sunny": _encode_svg(_sun_svg()),
    "cloudy": _encode_svg(_cloud_svg()),
    "rainy": _encode_svg(_rain_svg()),
    "stormy": _encode_svg(_storm_svg()),
    "snowy": _encode_svg(_snow_svg()),
    "foggy": _encode_svg(_fog_svg()),
}

DEFAULT_WEATHER_ICON = _encode_svg(_cloud_svg())


@dataclass
class WeatherData:
    """Weather data container."""

    location: str
    condition: str
    temperature: int
    humidity: int
    wind_speed: int


def render_weather_widget(data: WeatherData) -> WidgetRoot:
    """Render a weather widget from weather data.

    Args:
        data: WeatherData containing weather information

    Returns:
        A ChatKit WidgetRoot (Card) displaying the weather information
    """
    # Get weather icon
    weather_icon_src = WEATHER_ICONS.get(data.condition.lower(), DEFAULT_WEATHER_ICON)

    # Build the widget
    header = Box(
        padding=5,
        background="surface-tertiary",
        children=[
            Row(
                justify="between",
                align="center",
                children=[
                    Col(
                        align="start",
                        gap=1,
                        children=[
                            Text(
                                value=data.location,
                                size="lg",
                                weight="semibold",
                            ),
                            Text(
                                value="Current conditions",
                                color="tertiary",
                                size="xs",
                            ),
                        ],
                    ),
                    Box(
                        padding=3,
                        radius="full",
                        background="blue-100",
                        children=[
                            Image(
                                src=weather_icon_src,
                                alt=data.condition,
                                size=28,
                                fit="contain",
                            )
                        ],
                    ),
                ],
            ),
            Row(
                align="start",
                gap=4,
                children=[
                    Title(
                        value=f"{data.temperature}°C",
                        size="lg",
                        weight="semibold",
                    ),
                    Col(
                        align="start",
                        gap=1,
                        children=[
                            Text(
                                value=data.condition.title(),
                                color="secondary",
                                size="sm",
                                weight="medium",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    # Details section
    details = Box(
        padding=5,
        gap=4,
        children=[
            Text(value="Weather details", weight="semibold", size="sm"),
            Row(
                gap=3,
                wrap="wrap",
                children=[
                    _detail_chip("Humidity", f"{data.humidity}%"),
                    _detail_chip("Wind", f"{data.wind_speed} km/h"),
                ],
            ),
        ],
    )

    return Card(
        key="weather",
        padding=0,
        children=[header, details],
    )


def _detail_chip(label: str, value: str) -> Box:
    """Create a detail chip widget component."""
    return Box(
        padding=3,
        radius="xl",
        background="surface-tertiary",
        width=150,
        minWidth=150,
        maxWidth=150,
        minHeight=80,
        maxHeight=80,
        flex="0 0 auto",
        children=[
            Col(
                align="stretch",
                gap=2,
                children=[
                    Text(value=label, size="xs", weight="medium", color="tertiary"),
                    Row(
                        justify="center",
                        margin={"top": 2},
                        children=[Text(value=value, weight="semibold", size="lg")],
                    ),
                ],
            )
        ],
    )


def weather_widget_copy_text(data: WeatherData) -> str:
    """Generate plain text representation of weather data.

    Args:
        data: WeatherData containing weather information

    Returns:
        Plain text description for copy/paste functionality
    """
    return (
        f"Weather in {data.location}:\n"
        f"• Condition: {data.condition.title()}\n"
        f"• Temperature: {data.temperature}°C\n"
        f"• Humidity: {data.humidity}%\n"
        f"• Wind: {data.wind_speed} km/h"
    )


def render_city_selector_widget() -> WidgetRoot:
    """Render an interactive city selector widget.

    This widget displays popular cities as a visual selection interface.
    Users can click or ask about any city to get weather information.

    Returns:
        A ChatKit WidgetRoot (Card) with city selection display
    """
    # Create location icon SVG
    location_icon = _encode_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">'
        f'<path d="M32 8c-8.837 0-16 7.163-16 16 0 12 16 32 16 32s16-20 16-32c0-8.837-7.163-16-16-16z" '
        f'fill="{WEATHER_ICON_ACCENT}" stroke="{WEATHER_ICON_COLOR}" stroke-width="3" stroke-linejoin="round"/>'
        f'<circle cx="32" cy="24" r="6" fill="{WEATHER_ICON_COLOR}"/>'
        "</svg>"
    )

    # Header section
    header = Box(
        padding=5,
        background="surface-tertiary",
        children=[
            Row(
                gap=3,
                align="center",
                children=[
                    Box(
                        padding=3,
                        radius="full",
                        background="blue-100",
                        children=[
                            Image(
                                src=location_icon,
                                alt="Location",
                                size=28,
                                fit="contain",
                            )
                        ],
                    ),
                    Col(
                        align="start",
                        gap=1,
                        children=[
                            Title(
                                value="Popular Cities",
                                size="md",
                                weight="semibold",
                            ),
                            Text(
                                value="Select a city or ask about any location",
                                color="tertiary",
                                size="xs",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    # Create city chips in a grid layout
    city_chips: list[Button] = []
    for city in POPULAR_CITIES:
        # Create a button that sends an action to query weather for the selected city
        chip = Button(
            label=city["label"],
            variant="outline",
            size="md",
            onClickAction=ActionConfig(
                type="city_selected",
                payload={"city_value": city["value"], "city_label": city["label"]},
                handler="server",  # Handle on server-side
            ),
        )
        city_chips.append(chip)

    # Arrange in rows of 3
    city_rows: list[Row] = []
    for i in range(0, len(city_chips), 3):
        row_chips: list[Button] = city_chips[i : i + 3]
        city_rows.append(
            Row(
                gap=3,
                wrap="wrap",
                justify="start",
                children=list(row_chips),  # Convert to generic list
            )
        )

    # Cities display section
    cities_section = Box(
        padding=5,
        gap=3,
        children=[
            *city_rows,
            Box(
                padding=3,
                radius="md",
                background="blue-50",
                children=[
                    Text(
                        value="💡 Click any city to get its weather, or ask about any other location!",
                        size="xs",
                        color="secondary",
                    ),
                ],
            ),
        ],
    )

    return Card(
        key="city_selector",
        padding=0,
        children=[header, cities_section],
    )


def city_selector_copy_text() -> str:
    """Generate plain text representation of city selector.

    Returns:
        Plain text description for copy/paste functionality
    """
    cities_list = "\n".join([f"• {city['label']}" for city in POPULAR_CITIES])
    return f"Popular cities (click to get weather):\n{cities_list}\n\nYou can also ask about weather in any other location!"
