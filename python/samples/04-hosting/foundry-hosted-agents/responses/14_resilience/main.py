# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
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

    agent = Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        default_options={"store": False},
    )

    # resilient_background=True enables crash recovery for background requests:
    # - If the server crashes mid-response the handler is automatically
    #   re-invoked on the next process start without the client needing to retry.
    # - Persisted SSE events replay to clients that reconnect with starting_after=.
    #
    # Requires a persistent response store. In hosted Foundry environments the
    # Foundry storage API is automatically used. Locally the agentserver uses a
    # file-backed store under ~/.agentserver/responses/ by default.
    server = ResponsesHostServer(
        agent,
        options=ResponsesServerOptions(resilient_background=True),
    )
    server.run()


if __name__ == "__main__":
    main()
