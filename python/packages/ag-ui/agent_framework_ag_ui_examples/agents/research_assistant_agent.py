# Copyright (c) Microsoft. All rights reserved.

"""Example agent demonstrating agentic generative UI with custom events during execution."""

import asyncio

from agent_framework import ChatAgent, ai_function
from agent_framework._clients import ChatClientProtocol

from agent_framework_ag_ui import AgentFrameworkAgent


@ai_function
async def research_topic(topic: str) -> str:
    """Research a topic and generate a comprehensive report.

    Args:
        topic: The topic to research

    Returns:
        Research report
    """
    # Simulate multi-step research process
    steps = [
        ("Searching databases", 1.0),
        ("Analyzing sources", 1.5),
        ("Synthesizing information", 1.0),
        ("Generating report", 0.5),
    ]

    results: list[str] = []
    for step_name, duration in steps:
        await asyncio.sleep(duration)
        results.append(f"- {step_name}: completed")

    return f"Research report on '{topic}':\n" + "\n".join(results)


@ai_function
async def create_presentation(title: str, num_slides: int) -> str:
    """Create a presentation with multiple slides.

    Args:
        title: Presentation title
        num_slides: Number of slides to create

    Returns:
        Presentation summary
    """
    # Simulate slide generation
    slides: list[str] = []
    for i in range(num_slides):
        await asyncio.sleep(0.5)
        slides.append(f"Slide {i + 1}: Content for {title}")

    return f"Created presentation '{title}' with {num_slides} slides:\n" + "\n".join(slides)


@ai_function
async def analyze_data(dataset: str) -> str:
    """Analyze a dataset and produce insights.

    Args:
        dataset: The dataset name to analyze

    Returns:
        Analysis results
    """
    # Simulate data analysis phases
    phases = [
        ("Loading data", 0.8),
        ("Cleaning data", 1.0),
        ("Running statistical analysis", 1.2),
        ("Generating visualizations", 0.7),
    ]

    insights: list[str] = []
    for phase_name, duration in phases:
        await asyncio.sleep(duration)
        insights.append(f"- {phase_name}: done")

    return f"Analysis of '{dataset}':\n" + "\n".join(insights)


_RESEARCH_ASSISTANT_INSTRUCTIONS = (
    "You are a research and analysis assistant. "
    "You can research topics, create presentations, and analyze data. "
    "Use the available tools to help users with their research needs."
)


def research_assistant_agent(chat_client: ChatClientProtocol) -> AgentFrameworkAgent:
    """Create a research assistant agent with progress events.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A configured AgentFrameworkAgent instance with research capabilities
    """
    agent = ChatAgent(
        name="research_assistant",
        instructions=_RESEARCH_ASSISTANT_INSTRUCTIONS,
        chat_client=chat_client,
        tools=[research_topic, create_presentation, analyze_data],
    )

    return AgentFrameworkAgent(
        agent=agent,
        name="ResearchAssistant",
        description="Research assistant that emits progress events during task execution",
    )
