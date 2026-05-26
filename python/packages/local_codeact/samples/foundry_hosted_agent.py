# Copyright (c) Microsoft. All rights reserved.

"""This sample demonstrates wiring Local CodeAct into a Foundry hosted agent.

Local CodeAct executes LLM-generated Python in the local agent environment. Use
it only when the deployment environment supplies the real sandbox, such as a
Foundry hosted-agent container.
"""

from typing import Any

from agent_framework import Agent
from agent_framework_foundry_hosting import ResponsesHostServer

from agent_framework_local_codeact import LocalCodeActProvider, ProcessExecutionLimits


def create_model_client() -> Any:
    """Return the model client configured for your hosted agent."""
    raise RuntimeError("Configure and return your model client here.")


def create_server() -> ResponsesHostServer:
    """Create a Foundry Responses host server with Local CodeAct enabled."""
    # 1. Create the local agent and add Local CodeAct as a context provider.
    agent = Agent(
        client=create_model_client(),
        instructions="Use execute_code for Python calculations and controlled host-tool fan-out.",
        context_providers=[
            LocalCodeActProvider(
                execution_limits=ProcessExecutionLimits(timeout_seconds=5),
            )
        ],
    )

    # 2. Wrap the local agent for Foundry Agent Server hosting.
    return ResponsesHostServer(agent)


if __name__ == "__main__":
    create_server()

"""
Sample output:
Configure and return your model client here.
"""
