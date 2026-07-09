# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_orchestrations import MagenticBuilder
from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    researcher_agent = Agent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        client=client,
    )

    # Create code interpreter tool using instance method
    code_interpreter_tool = client.get_code_interpreter_tool()
    coder_agent = Agent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        client=client,
        tools=code_interpreter_tool,
    )

    # Create a manager agent for orchestration
    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that coordinates the research and coding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        client=client,
    )

    # Mark participant responses as intermediate so the stream shows the
    # conversation as it unfolds while the manager's final answer remains the
    # terminal workflow output.
    workflow = MagenticBuilder(
        participants=[researcher_agent, coder_agent],
        intermediate_output_from=[researcher_agent, coder_agent],
        manager_agent=manager_agent,
        max_round_count=10,
        max_stall_count=3,
        max_reset_count=2,
    ).build()

    # resilient_background=True enables crash recovery for background requests:
    # - If the server crashes mid-response the handler is automatically
    #   re-invoked on the next process start without the client needing to retry.
    # - Persisted SSE events replay to clients that reconnect with starting_after=.
    #
    # Requires a persistent response store. In hosted Foundry environments the
    # Foundry storage API is automatically used. Locally the agentserver uses a
    # file-backed store under ~/.agentserver/responses/ by default.
    server = ResponsesHostServer(
        workflow.as_agent(),
        options=ResponsesServerOptions(resilient_background=True),
    )
    server.run()


if __name__ == "__main__":
    main()
