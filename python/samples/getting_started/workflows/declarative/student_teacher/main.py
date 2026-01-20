# Copyright (c) Microsoft. All rights reserved.

"""
Run the student-teacher (MathChat) workflow sample.

Usage:
    python main.py

Demonstrates iterative conversation between two agents:
- StudentAgent: Attempts to solve math problems
- TeacherAgent: Reviews and coaches the student's approach

The workflow loops until the teacher gives congratulations or max turns reached.

Prerequisites:
    - Azure OpenAI deployment with chat completion capability
    - Environment variables:
        AZURE_OPENAI_ENDPOINT: Your Azure OpenAI endpoint
        AZURE_OPENAI_DEPLOYMENT_NAME: Your deployment name (optional, defaults to gpt-4o)
"""

import asyncio
from pathlib import Path

from agent_framework import WorkflowOutputEvent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.declarative import WorkflowFactory
from azure.identity import AzureCliCredential

STUDENT_INSTRUCTIONS = """You are a curious math student working on understanding mathematical concepts.
When given a problem:
1. Think through it step by step
2. Make reasonable attempts, but it's okay to make mistakes
3. Show your work and reasoning
4. Ask clarifying questions when confused
5. Build on feedback from your teacher

Be authentic - you're learning, so don't pretend to know everything."""

TEACHER_INSTRUCTIONS = """You are a patient math teacher helping a student understand concepts.
When reviewing student work:
1. Acknowledge what they did correctly
2. Gently point out errors without giving away the answer
3. Ask guiding questions to help them discover mistakes
4. Provide hints that lead toward understanding
5. When the student demonstrates clear understanding, respond with "CONGRATULATIONS" 
   followed by a summary of what they learned

Focus on building understanding, not just getting the right answer."""


async def main() -> None:
    """Run the student-teacher workflow with real Azure AI agents."""
    # Create chat client
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create student and teacher agents
    student_agent = chat_client.as_agent(
        name="StudentAgent",
        instructions=STUDENT_INSTRUCTIONS,
    )

    teacher_agent = chat_client.as_agent(
        name="TeacherAgent",
        instructions=TEACHER_INSTRUCTIONS,
    )

    # Create factory with agents
    factory = WorkflowFactory(
        agents={
            "StudentAgent": student_agent,
            "TeacherAgent": teacher_agent,
        }
    )

    workflow_path = Path(__file__).parent / "workflow.yaml"
    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print(f"Loaded workflow: {workflow.name}")
    print("=" * 50)
    print("Student-Teacher Math Coaching Session")
    print("=" * 50)

    async for event in workflow.run_stream("How would you compute the value of PI?"):
        if isinstance(event, WorkflowOutputEvent):
            print(f"{event.data}", flush=True, end="")

    print("\n" + "=" * 50)
    print("Session Complete")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
