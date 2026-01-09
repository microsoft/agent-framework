# Copyright (c) Microsoft. All rights reserved.

from .._agents import AgentProtocol


def resolve_agent_id(agent: AgentProtocol) -> str:
    """Resolve the unique identifier for an agent.

    Prefers the `.name` attribute if set; otherwise falls back to `.id`.

    Args:
        agent: The agent whose identifier is to be resolved.

    Returns:
        The resolved unique identifier for the agent.
    """
    return agent.name if agent.name else agent.id
