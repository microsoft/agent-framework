# Copyright (c) Microsoft. All rights reserved.

"""Client wrapper for Durable Task Agent Framework.

This module provides the DurableAIAgentClient class for external clients to interact
with durable agents via gRPC.
"""

from __future__ import annotations

from agent_framework import AgentResponse, get_logger
from durabletask.client import TaskHubGrpcClient

from ._constants import DEFAULT_MAX_POLL_RETRIES, DEFAULT_POLL_INTERVAL_SECONDS
from ._executors import ClientAgentExecutor
from ._shim import DurableAgentProvider, DurableAIAgent

logger = get_logger("agent_framework.durabletask.client")


class DurableAIAgentClient(DurableAgentProvider[AgentResponse]):
    """Client wrapper for interacting with durable agents externally.

    This class wraps a durabletask TaskHubGrpcClient and provides a convenient
    interface for retrieving and executing durable agents from external contexts.

    Example:
        ```python
        from durabletask import TaskHubGrpcClient
        from agent_framework.azure import DurableAIAgentClient

        # Create the underlying client
        client = TaskHubGrpcClient(host_address="localhost:4001")

        # Wrap it with the agent client
        agent_client = DurableAIAgentClient(client)

        # Get an agent reference
        agent = agent_client.get_agent("assistant")

        # Run the agent (synchronous call that waits for completion)
        response = agent.run("Hello, how are you?")
        print(response.text)
        ```
    """

    def __init__(
        self,
        client: TaskHubGrpcClient,
        max_poll_retries: int = DEFAULT_MAX_POLL_RETRIES,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ):
        """Initialize the client wrapper.

        Args:
            client: The durabletask client instance to wrap
            max_poll_retries: Maximum polling attempts when waiting for responses
            poll_interval_seconds: Delay in seconds between polling attempts
        """
        self._client = client

        # Validate and set polling parameters
        self.max_poll_retries = max(1, max_poll_retries)
        self.poll_interval_seconds = (
            poll_interval_seconds if poll_interval_seconds > 0 else DEFAULT_POLL_INTERVAL_SECONDS
        )

        self._executor = ClientAgentExecutor(self._client, self.max_poll_retries, self.poll_interval_seconds)
        logger.debug("[DurableAIAgentClient] Initialized with client type: %s", type(client).__name__)

    def get_agent(self, agent_name: str) -> DurableAIAgent[AgentResponse]:
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

        return DurableAIAgent(self._executor, agent_name)
