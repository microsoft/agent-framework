# Copyright (c) Microsoft. All rights reserved.

"""Example agent demonstrating Tool-based Generative UI (Feature 5)."""

from typing import Any

from agent_framework import AIFunction, ChatAgent
from agent_framework._clients import ChatClientProtocol

from agent_framework_ag_ui import AgentFrameworkAgent

# Declaration-only tools (func=None) - actual rendering happens on the client side
generate_haiku = AIFunction[Any, str](
    name="generate_haiku",
    description="""Generate a haiku with image and gradient background (FRONTEND_RENDER).

    This tool generates UI for displaying a haiku with an image and gradient background.
    The frontend should render this as a custom haiku component.""",
    func=None,  # Makes declaration_only=True so client renders the UI
    input_model={
        "type": "object",
        "properties": {
            "english": {
                "type": "array",
                "items": {"type": "string"},
                "description": "English haiku lines (exactly 3 lines)",
                "minItems": 3,
                "maxItems": 3,
            },
            "japanese": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Japanese haiku lines (exactly 3 lines)",
                "minItems": 3,
                "maxItems": 3,
            },
            "image_name": {
                "type": "string",
                "description": """Image filename for visual accompaniment. Must be one of:
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
            """,
            },
            "gradient": {
                "type": "string",
                "description": 'CSS gradient string for background (e.g., "linear-gradient(135deg, #667eea 0%, #764ba2 100%)")',
            },
        },
        "required": ["english", "japanese", "image_name", "gradient"],
    },
)

create_chart = AIFunction[Any, str](
    name="create_chart",
    description="""Create an interactive chart (FRONTEND_RENDER).

    This tool creates chart specifications for frontend rendering.
    The frontend should render this as an interactive chart component.""",
    func=None,  # Makes declaration_only=True so client renders the UI
    input_model={
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "description": "Type of chart (bar, line, pie, scatter)",
            },
            "data_points": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Data points for the chart",
            },
            "title": {
                "type": "string",
                "description": "Chart title",
            },
        },
        "required": ["chart_type", "data_points", "title"],
    },
)

display_timeline = AIFunction[Any, str](
    name="display_timeline",
    description="""Display an interactive timeline (FRONTEND_RENDER).

    This tool creates timeline specifications for frontend rendering.
    The frontend should render this as an interactive timeline component.""",
    func=None,  # Makes declaration_only=True so client renders the UI
    input_model={
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Events to display on the timeline",
            },
            "start_date": {
                "type": "string",
                "description": "Timeline start date",
            },
            "end_date": {
                "type": "string",
                "description": "Timeline end date",
            },
        },
        "required": ["events", "start_date", "end_date"],
    },
)

show_comparison_table = AIFunction[Any, str](
    name="show_comparison_table",
    description="""Show a comparison table (FRONTEND_RENDER).

    This tool creates table specifications for frontend rendering.
    The frontend should render this as an interactive comparison table.""",
    func=None,  # Makes declaration_only=True so client renders the UI
    input_model={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Items to compare",
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Column names",
            },
        },
        "required": ["items", "columns"],
    },
)


_UI_GENERATOR_INSTRUCTIONS = """You MUST use the provided tools to generate content. Never respond with plain text descriptions.

    For haiku requests:
    - Call generate_haiku tool with all 4 required parameters
    - English: 3 lines
    - Japanese: 3 lines
    - image_name: Choose from available images
    - gradient: CSS gradient string

    For other requests, use the appropriate tool (create_chart, display_timeline, show_comparison_table).
    """


def ui_generator_agent(chat_client: ChatClientProtocol) -> AgentFrameworkAgent:
    """Create a UI generator agent with frontend rendering tools.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A configured AgentFrameworkAgent instance with UI generation tools
    """
    agent = ChatAgent(
        name="ui_generator",
        instructions=_UI_GENERATOR_INSTRUCTIONS,
        chat_client=chat_client,
        tools=[generate_haiku, create_chart, display_timeline, show_comparison_table],
        # Force tool usage - the LLM MUST call a tool, cannot respond with plain text
        chat_options={"tool_choice": "required"},
    )

    return AgentFrameworkAgent(
        agent=agent,
        name="UIGenerator",
        description="Generates custom UI components through tool calls",
    )
