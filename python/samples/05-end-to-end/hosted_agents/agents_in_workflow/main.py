# Copyright (c) Microsoft. All rights reserved.

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_orchestrations import ConcurrentBuilder
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity import DefaultAzureCredential  # pyright: ignore[reportUnknownVariableType]
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def main():
    # Create agents
    researcher = Agent(
        client=FoundryChatClient(credential=DefaultAzureCredential()),
        instructions=(
            "You're an expert market and product researcher. "
            "Given a prompt, provide concise, factual insights, opportunities, and risks."
        ),
        name="researcher",
    )
    marketer = Agent(
        client=FoundryChatClient(credential=DefaultAzureCredential()),
        instructions=(
            "You're a creative marketing strategist. "
            "Craft compelling value propositions and target messaging aligned to the prompt."
        ),
        name="marketer",
    )
    legal = Agent(
        client=FoundryChatClient(credential=DefaultAzureCredential()),
        instructions=(
            "You're a cautious legal/compliance reviewer. "
            "Highlight constraints, disclaimers, and policy concerns based on the prompt."
        ),
        name="legal",
    )

    # Build a concurrent workflow
    workflow = ConcurrentBuilder(participants=[researcher, marketer, legal]).build()

    # Convert the workflow to an agent
    workflow_agent = Agent(client=workflow)

    # Run the agent as a hosted agent
    from_agent_framework(workflow_agent).run()


if __name__ == "__main__":
    main()
