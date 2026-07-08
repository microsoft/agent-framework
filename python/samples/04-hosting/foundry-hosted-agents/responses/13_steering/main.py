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

    # steerable_conversations=True allows a client to send a new turn while
    # the current one is still in progress. The new turn is queued and the
    # running handler is cooperatively cancelled (via cancellation_signal)
    # rather than the client receiving HTTP 409 conversation_locked.
    # Once the current turn reaches a terminal event the queued turn runs.
    server = ResponsesHostServer(
        agent,
        options=ResponsesServerOptions(steerable_conversations=True),
    )
    server.run()


if __name__ == "__main__":
    main()
