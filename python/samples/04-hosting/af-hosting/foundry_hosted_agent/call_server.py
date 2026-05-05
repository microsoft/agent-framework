# Copyright (c) Microsoft. All rights reserved.

"""Call the foundry_hosted_agent server three ways.

The foundry_hosted_agent host exposes ``POST /responses`` (OpenAI Responses-shaped) and
``POST /invocations/invoke`` (host-native), and that minimal contract is
**runtime-compatible with the Foundry Hosted Agents platform** — so the same
agent code that calls the local server also calls the same image deployed
as a Hosted Agent.

Modes
-----
``--via openai``  (default)
    Plain ``openai`` SDK against the local ``/responses``. Uses
    ``api_key="not-needed"`` because the local sample has no auth.

``--via af``
    Agent Framework ``Agent`` wrapping ``OpenAIChatClient`` pointed at the
    local ``BASE_URL``. ``OpenAIChatClient`` already speaks the Responses
    surface natively.

``--via foundry``
    Agent Framework ``FoundryAgent`` against a Hosted Agent that this image
    has been deployed as. Requires::

        FOUNDRY_PROJECT_ENDPOINT=https://<project>.services.ai.azure.com
        FOUNDRY_HOSTED_AGENT_NAME=<hosted-agent-name>

    Auth uses ``AzureCliCredential`` (run ``az login`` first).

Start the server first (in another shell)::

    uv run python app.py

Then::

    uv run python call_server.py "Who are you?"
    uv run python call_server.py --via af "What's the weather in Seattle?"
    FOUNDRY_PROJECT_ENDPOINT=... FOUNDRY_HOSTED_AGENT_NAME=... \\
        uv run python call_server.py --via foundry "Who are you?"
"""

from __future__ import annotations

import argparse
import asyncio

from agent_framework import Agent
from agent_framework_foundry import FoundryAgent
from agent_framework_openai import OpenAIChatClient
from azure.identity.aio import AzureCliCredential
from openai import OpenAI

# Bare server origin — the OpenAI SDK / OpenAIChatClient append ``/responses`` themselves.
BASE_URL = "http://127.0.0.1:8000"


def call_via_openai_sdk(prompt: str) -> None:
    client = OpenAI(base_url=BASE_URL, api_key="not-needed")
    response = client.responses.create(model="agent", input=prompt)
    print(f"User:  {prompt}")
    print(f"Agent: {response.output_text}")


async def call_via_agent_framework(prompt: str) -> None:
    # Agent + OpenAIChatClient(base_url=...) is the Agent Framework way to
    # talk to any Responses-shaped endpoint — including foundry_hosted_agent's `/responses`.
    chat_client = OpenAIChatClient(base_url=BASE_URL, api_key="not-needed", model_id="agent")
    agent = Agent(client=chat_client)
    result = await agent.run(prompt)
    print(f"User:  {prompt}")
    print(f"Agent: {result.text}")


async def call_via_foundry_hosted_agent(prompt: str) -> None:
    # Once foundry_hosted_agent's image is deployed as a Foundry Hosted Agent, FoundryAgent
    # keyed on ``agent_name`` is the AF-native client. The agent's runtime is
    # the very same Responses + Invocations contract — Foundry just hosts it.
    async with AzureCliCredential() as credential:
        agent = FoundryAgent(
            project_endpoint="https://edvan-foundry-sw.services.ai.azure.com/api/projects/agents",
            agent_name="agent-framework-hosting-sample",
            credential=credential,
            allow_preview=True,
        )
        session = agent.get_session(service_session_id="resp_7c86d98980df4f409045e71609c50ce4")
        result = await agent.run(prompt, session=session)
    print(f"User:  {prompt}")
    print(f"Agent: {result.text}")
    print(f"Session ID (for history continuity): {result.response_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--via",
        choices=("openai", "af", "foundry"),
        default="openai",
        help="Calling client to use.",
    )
    parser.add_argument("prompt", nargs="*")
    args = parser.parse_args()
    prompt = " ".join(args.prompt) or "Who are you?"

    if args.via == "openai":
        call_via_openai_sdk(prompt)
    elif args.via == "af":
        asyncio.run(call_via_agent_framework(prompt))
    else:
        asyncio.run(call_via_foundry_hosted_agent(prompt))


if __name__ == "__main__":
    main()
