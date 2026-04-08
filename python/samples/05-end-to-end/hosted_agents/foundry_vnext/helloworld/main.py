# Copyright (c) Microsoft. All rights reserved.


import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, ResponsesHost
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    agent = Agent(
        client=client,
        name="HelloAgent",
        instructions="You are a friendly assistant. Keep your answers brief.",
    )

    server = ResponsesHost(agent)
    server.run()


if __name__ == "__main__":
    main()
