# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
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
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )

    # When running in a hosted Foundry environment, ResponsesHostServer automatically
    # enables resilient_background=True for background requests. This means:
    # - If the server crashes mid-response, the handler is automatically re-invoked
    #   on the next process start without the client needing to retry.
    # - Persisted SSE events replay to clients that reconnect after a crash.
    #
    # To also enable steerable conversations, pass steerable_conversations=True.
    # With steering enabled, when a client sends a new turn while the current one is
    # still in progress, the platform queues the new input and cooperatively cancels
    # the current handler (via the cancellation_signal) instead of rejecting with
    # HTTP 409 conversation_locked. The cancelled turn emits response.completed with
    # partial output; the queued turn then runs with is_steered_turn=True.
    #
    #   server = ResponsesHostServer(
    #       agent,
    #       steerable_conversations=True,
    #   )
    #
    # To opt out of crash recovery entirely — for example when your agent makes
    # non-idempotent external calls that must not be repeated on crash, and you prefer
    # fail-fast semantics — pass explicit options with resilient_background=False:
    #
    #   from azure.ai.agentserver.responses import ResponsesServerOptions
    #
    #   server = ResponsesHostServer(
    #       agent,
    #       options=ResponsesServerOptions(resilient_background=False),
    #   )
    #
    # With resilient_background=False, a crash during a background request marks the
    # response as failed instead of re-invoking the handler. The client receives a
    # failed status and is responsible for retrying if desired.
    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
