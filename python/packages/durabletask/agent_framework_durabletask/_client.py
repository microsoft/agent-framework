# Copyright (c) Microsoft. All rights reserved.

"""Client wrapper for Durable Task Agent Framework.

This module provides the DurableAIAgentClient class for external clients to interact
with durable agents via gRPC.
"""

from __future__ import annotations

from agent_framework import get_logger
from durabletask.client import TaskHubGrpcClient

from ._executors import ClientAgentExecutor
from ._shim import DurableAgentProvider, DurableAIAgent

logger = get_logger("agent_framework.durabletask.client")


class DurableAIAgentClient(DurableAgentProvider):
    """Client wrapper for interacting with durable agents externally.

    This class wraps a durabletask TaskHubGrpcClient and provides a convenient
    interface for retrieving and executing durable agents from external contexts
    (e.g., FastAPI endpoints, CLI tools, etc.).

    Example:
        ```python
        from durabletask import TaskHubGrpcClient
        from agent_framework_durabletask import DurableAIAgentClient

        # Create the underlying client
        client = TaskHubGrpcClient(host_address="localhost:4001")

        # Wrap it with the agent client
        agent_client = DurableAIAgentClient(client)

        # Get an agent reference
        agent = await agent_client.get_agent("assistant")

        # Run the agent
        response = await agent.run("Hello, how are you?")
        print(response.text)
        ```
    """

    def __init__(self, client: TaskHubGrpcClient):
        """Initialize the client wrapper.

        Args:
            client: The durabletask client instance to wrap
        """
        self._client = client
        self._executor = ClientAgentExecutor(self._client)
        logger.debug("[DurableAIAgentClient] Initialized with client type: %s", type(client).__name__)

    def get_agent(self, agent_name: str) -> DurableAIAgent:
        """Retrieve a DurableAIAgent shim for the specified agent.

        This method returns a proxy object that can be used to execute the agent.
        The actual agent must be registered on a worker with the same name.

        Args:
            agent_name: Name of the agent to retrieve (without the dafx- prefix)

        Returns:
            DurableAIAgent instance that can be used to run the agent

        Note:
            This method does not validate that the agent exists. Validation
            will occur when the agent is executed. If the entity doesn't exist,
            the execution will fail with an appropriate error.
        """
        logger.debug("[DurableAIAgentClient] Creating agent proxy for: %s", agent_name)

        # Note: Validation would require async, so we defer it to execution time
        # The entity name will be f"dafx-{agent_name}"

        return DurableAIAgent(self._executor, agent_name)
