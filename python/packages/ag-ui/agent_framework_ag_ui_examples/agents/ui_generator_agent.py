# Copyright (c) Microsoft. All rights reserved.

"""Example agent demonstrating Tool-based Generative UI (Feature 5)."""

from typing import Any

from agent_framework import ChatAgent, ai_function
from agent_framework.azure import AzureOpenAIChatClient

from agent_framework_ag_ui import AgentFrameworkAgent


@ai_function
def generate_haiku(english: list[str], japanese: list[str], image_name: str | None, gradient: str) -> str:
    """Generate a haiku with image and gradient background (FRONTEND_RENDER).

    This tool generates UI for displaying a haiku with an image and gradient background.
    The frontend should render this as a custom haiku component.

    Args:
        english: English haiku lines (exactly 3 lines)
        japanese: Japanese haiku lines (exactly 3 lines)
        image_name: Image filename for visual accompaniment. Must be one of:
            - "Osaka_Castle_Turret_Stone_Wall_Pine_Trees_Daytime.jpg"
            - "Tokyo_Skyline_Night_Tokyo_Tower_Mount_Fuji_View.jpg"
            - "Itsukushima_Shrine_Miyajima_Floating_Torii_Gate_Sunset_Long_Exposure.jpg"
            - "Takachiho_Gorge_Waterfall_River_Lush_Greenery_Japan.jpg"
            - "Bonsai_Tree_Potted_Japanese_Art_Green_Foliage.jpeg"
            - "Shirakawa-go_Gassho-zukuri_Thatched_Roof_Village_Aerial_View.jpg"
            - "Ginkaku-ji_Silver_Pavilion_Kyoto_Japanese_Garden_Pond_Reflection.jpg"
            - "Senso-ji_Temple_Asakusa_Cherry_Blossoms_Kimono_Umbrella.jpg"
            - "Cherry_Blossoms_Sakura_Night_View_City_Lights_Japan.jpg"
            - "Mount_Fuji_Lake_Reflection_Cherry_Blossoms_Sakura_Spring.jpg"
        gradient: CSS gradient string for background (e.g., "linear-gradient(135deg, #667eea 0%, #764ba2 100%)")

    Returns:
        Haiku metadata for frontend rendering
    """
    return f"Haiku generated with image: {image_name}"


@ai_function
def create_chart(chart_type: str, data_points: list[dict[str, Any]], title: str) -> str:
    """Create an interactive chart (FRONTEND_RENDER).

    This tool creates chart specifications for frontend rendering.
    The frontend should render this as an interactive chart component.

    Args:
        chart_type: Type of chart (bar, line, pie, scatter)
        data_points: Data points for the chart
        title: Chart title

    Returns:
        Chart specification for frontend rendering
    """
    return f"Chart '{title}' created with {len(data_points)} data points"


@ai_function
def display_timeline(events: list[dict[str, Any]], start_date: str, end_date: str) -> str:
    """Display an interactive timeline (FRONTEND_RENDER).

    This tool creates timeline specifications for frontend rendering.
    The frontend should render this as an interactive timeline component.

    Args:
        events: Events to display on the timeline
        start_date: Timeline start date
        end_date: Timeline end date

    Returns:
        Timeline specification for frontend rendering
    """
    return f"Timeline created with {len(events)} events from {start_date} to {end_date}"


@ai_function
def show_comparison_table(items: list[dict[str, Any]], columns: list[str]) -> str:
    """Show a comparison table (FRONTEND_RENDER).

    This tool creates table specifications for frontend rendering.
    The frontend should render this as an interactive comparison table.

    Args:
        items: Items to compare
        columns: Column names

    Returns:
        Table specification for frontend rendering
    """
    return f"Comparison table created with {len(items)} items and {len(columns)} columns"


# Create the UI generator agent using tool-based approach with forced tool usage
agent = ChatAgent(
    name="ui_generator",
    instructions="""You MUST use the provided tools to generate content. Never respond with plain text descriptions.

    For haiku requests:
    - Call generate_haiku tool with all 4 required parameters
    - English: 3 lines
    - Japanese: 3 lines
    - image_name: Choose from available images
    - gradient: CSS gradient string

    For other requests, use the appropriate tool (create_chart, display_timeline, show_comparison_table).
    """,
    chat_client=AzureOpenAIChatClient(),
    tools=[generate_haiku, create_chart, display_timeline, show_comparison_table],
    # Force tool usage - the LLM MUST call a tool, cannot respond with plain text
    chat_options={"tool_choice": "required"},
)

ui_generator_agent = AgentFrameworkAgent(
    agent=agent,
    name="UIGenerator",
    description="Generates custom UI components through tool calls",
)
