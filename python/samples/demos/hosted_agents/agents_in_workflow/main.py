# Copyright (c) Microsoft. All rights reserved.

from agent_framework import ConcurrentBuilder
from agent_framework.openai import OpenAIChatClient
from azure.ai.agentserver.agentframework import from_agent_framework  # pyright: ignore[reportUnknownVariableType]


def main():
    # Create agents
    researcher = OpenAIChatClient().create_agent(
        instructions=(
            "You're an expert market and product researcher. "
            "Given a prompt, provide concise, factual insights, opportunities, and risks."
        ),
        name="researcher",
    )
    marketer = OpenAIChatClient().create_agent(
        instructions=(
            "You're a creative marketing strategist. "
            "Craft compelling value propositions and target messaging aligned to the prompt."
        ),
        name="marketer",
    )
    legal = OpenAIChatClient().create_agent(
        instructions=(
            "You're a cautious legal/compliance reviewer. "
            "Highlight constraints, disclaimers, and policy concerns based on the prompt."
        ),
        name="legal",
    )

    # Build a concurrent workflow
    workflow = ConcurrentBuilder().participants([researcher, marketer, legal]).build()

    # Convert the workflow to an agent
    workflow_agent = workflow.as_agent()

    # Run the agent as a hosted agent
    from_agent_framework(workflow_agent).run()


if __name__ == "__main__":
    main()
