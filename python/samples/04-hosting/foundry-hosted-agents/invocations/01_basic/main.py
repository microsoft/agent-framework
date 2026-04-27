# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import InvocationsHostServer
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

    agent = Agent(
        client=client,
        instructions="You are a friendly assistant. Keep your answers brief.",
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    server = InvocationsHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
