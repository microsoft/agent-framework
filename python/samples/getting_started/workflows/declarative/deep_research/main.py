# Copyright (c) Microsoft. All rights reserved.

"""
DeepResearch workflow sample.

This workflow coordinates multiple agents to address complex user requests
according to the "Magentic" orchestration pattern introduced by AutoGen.

The following agents are responsible for overseeing and coordinating the workflow:
- ResearchAgent: Analyze the current task and correlate relevant facts
- PlannerAgent: Analyze the current task and devise an overall plan
- ManagerAgent: Evaluates status and delegates tasks to other agents
- SummaryAgent: Synthesizes the final response

The following agents have capabilities that are utilized to address the input task:
- KnowledgeAgent: Performs generic web searches
- CoderAgent: Able to write and execute code
- WeatherAgent: Provides weather information

Usage:
    python main.py
"""

import asyncio
from pathlib import Path

from agent_framework import WorkflowOutputEvent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.declarative import WorkflowFactory
from azure.identity import AzureCliCredential
from pydantic import BaseModel, Field

# Agent Instructions

RESEARCH_INSTRUCTIONS = """In order to help begin addressing the user request, please answer the following pre-survey to the best of your ability.
Keep in mind that you are Ken Jennings-level with trivia, and Mensa-level with puzzles, so there should be a deep well to draw from.

Here is the pre-survey:

    1. Please list any specific facts or figures that are GIVEN in the request itself. It is possible that there are none.
    2. Please list any facts that may need to be looked up, and WHERE SPECIFICALLY they might be found. In some cases, authoritative sources are mentioned in the request itself.
    3. Please list any facts that may need to be derived (e.g., via logical deduction, simulation, or computation)
    4. Please list any facts that are recalled from memory, hunches, well-reasoned guesses, etc.

When answering this survey, keep in mind that 'facts' will typically be specific names, dates, statistics, etc. Your answer must only use the headings:

    1. GIVEN OR VERIFIED FACTS
    2. FACTS TO LOOK UP
    3. FACTS TO DERIVE
    4. EDUCATED GUESSES

DO NOT include any other headings or sections in your response. DO NOT list next steps or plans until asked to do so."""  # noqa: E501

PLANNER_INSTRUCTIONS = """Your only job is to devise an efficient plan that identifies (by name) how a team member may contribute to addressing the user request.

Only select the following team which is listed as "- [Name]: [Description]"

- WeatherAgent: Able to retrieve weather information
- CoderAgent: Able to write and execute Python code
- KnowledgeAgent: Able to perform generic websearches

The plan must be a bullet point list must be in the form "- [AgentName]: [Specific action or task for that agent to perform]"

Remember, there is no requirement to involve the entire team -- only select team member's whose particular expertise is required for this task."""  # noqa: E501

MANAGER_INSTRUCTIONS = """Recall we have assembled the following team:

- KnowledgeAgent: Able to perform generic websearches
- CoderAgent: Able to write and execute Python code
- WeatherAgent: Able to retrieve weather information

To make progress on the request, please answer the following questions, including necessary reasoning:
- Is the request fully satisfied? (True if complete, or False if the original request has yet to be SUCCESSFULLY and FULLY addressed)
- Are we in a loop where we are repeating the same requests and / or getting the same responses from an agent multiple times? Loops can span multiple turns, and can include repeated actions like scrolling up or down more than a handful of times.
- Are we making forward progress? (True if just starting, or recent messages are adding value. False if recent messages show evidence of being stuck in a loop or if there is evidence of significant barriers to success such as the inability to read from a required file)
- Who should speak next? (select from: KnowledgeAgent, CoderAgent, WeatherAgent)
- What instruction or question would you give this team member? (Phrase as if speaking directly to them, and include any specific information they may need)"""  # noqa: E501

SUMMARY_INSTRUCTIONS = """We have completed the task.

Based only on the conversation and without adding any new information,
synthesize the result of the conversation as a complete response to the user task.

The user will only ever see this last response and not the entire conversation,
so please ensure it is complete and self-contained."""

KNOWLEDGE_INSTRUCTIONS = """You are a knowledge agent that can perform web searches to find information."""

CODER_INSTRUCTIONS = """You solve problems by writing and executing code."""

WEATHER_INSTRUCTIONS = """You are a weather expert that can provide weather information."""


# Pydantic models for structured outputs


class ReasonedAnswer(BaseModel):
    """A response with reasoning and answer."""

    reason: str = Field(description="The reasoning behind the answer")
    answer: bool = Field(description="The boolean answer")


class ReasonedStringAnswer(BaseModel):
    """A response with reasoning and string answer."""

    reason: str = Field(description="The reasoning behind the answer")
    answer: str = Field(description="The string answer")


class ManagerResponse(BaseModel):
    """Response from manager agent evaluation."""

    is_request_satisfied: ReasonedAnswer = Field(description="Whether the request is fully satisfied")
    is_in_loop: ReasonedAnswer = Field(description="Whether we are in a loop repeating the same requests")
    is_progress_being_made: ReasonedAnswer = Field(description="Whether forward progress is being made")
    next_speaker: ReasonedStringAnswer = Field(description="Who should speak next")
    instruction_or_question: ReasonedStringAnswer = Field(
        description="What instruction or question to give the next speaker"
    )


async def main() -> None:
    """Run the deep research workflow."""
    # Create Azure OpenAI client
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents
    research_agent = chat_client.as_agent(
        name="ResearchAgent",
        instructions=RESEARCH_INSTRUCTIONS,
    )

    planner_agent = chat_client.as_agent(
        name="PlannerAgent",
        instructions=PLANNER_INSTRUCTIONS,
    )

    manager_agent = chat_client.as_agent(
        name="ManagerAgent",
        instructions=MANAGER_INSTRUCTIONS,
        default_options={"response_format": ManagerResponse},
    )

    summary_agent = chat_client.as_agent(
        name="SummaryAgent",
        instructions=SUMMARY_INSTRUCTIONS,
    )

    knowledge_agent = chat_client.as_agent(
        name="KnowledgeAgent",
        instructions=KNOWLEDGE_INSTRUCTIONS,
    )

    coder_agent = chat_client.as_agent(
        name="CoderAgent",
        instructions=CODER_INSTRUCTIONS,
    )

    weather_agent = chat_client.as_agent(
        name="WeatherAgent",
        instructions=WEATHER_INSTRUCTIONS,
    )

    # Create workflow factory
    factory = WorkflowFactory(
        agents={
            "ResearchAgent": research_agent,
            "PlannerAgent": planner_agent,
            "ManagerAgent": manager_agent,
            "SummaryAgent": summary_agent,
            "KnowledgeAgent": knowledge_agent,
            "CoderAgent": coder_agent,
            "WeatherAgent": weather_agent,
        },
    )

    # Load workflow from YAML
    samples_root = Path(__file__).parent.parent.parent.parent.parent.parent.parent
    workflow_path = samples_root / "workflow-samples" / "DeepResearch.yaml"
    if not workflow_path.exists():
        # Fall back to local copy if workflow-samples doesn't exist
        workflow_path = Path(__file__).parent / "workflow.yaml"

    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print(f"Loaded workflow: {workflow.name}")
    print("=" * 60)
    print("Deep Research Workflow (Magentic Pattern)")
    print("=" * 60)

    # Example input
    task = "What is the weather like in Seattle and how does it compare to the average for this time of year?"

    async for event in workflow.run_stream(task):
        if isinstance(event, WorkflowOutputEvent):
            print(f"{event.data}", end="", flush=True)

    print("\n" + "=" * 60)
    print("Research Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
