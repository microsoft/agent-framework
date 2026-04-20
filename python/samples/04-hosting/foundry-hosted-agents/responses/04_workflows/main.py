# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import Agent, AgentExecutor, WorkflowBuilder
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    writer_agent = Agent(
        client=client,
        instructions=("You are an excellent slogan writer. You create new slogans based on the given topic."),
        name="writer",
    )

    legal_agent = Agent(
        client=client,
        instructions=(
            "You are an excellent legal reviewer. "
            "Make necessary corrections to the slogan so that it is legally compliant."
        ),
        name="legal_reviewer",
    )

    format_agent = Agent(
        client=client,
        instructions=(
            "You are an excellent content formatter. "
            "You take the slogan and format it in a cool retro style when printing to a terminal."
        ),
        name="formatter",
    )

    # Set the context mode to `last_agent` so that each agent only sees the output of the
    # previous agent instead of the full conversation history
    writer_executor = AgentExecutor(writer_agent, context_mode="last_agent")
    legal_executor = AgentExecutor(legal_agent, context_mode="last_agent")
    format_executor = AgentExecutor(format_agent, context_mode="last_agent")

    workflow_agent = (
        WorkflowBuilder(
            start_executor=writer_executor,
            # Limiting the output to only the final formatted result.
            # If this is not set, all intermediate results will be included in the output.
            output_executors=[format_executor],
        )
        .add_edge(writer_executor, legal_executor)
        .add_edge(legal_executor, format_executor)
        .build()
        .as_agent()
    )

    server = ResponsesHostServer(workflow_agent)
    server.run()


if __name__ == "__main__":
    main()
