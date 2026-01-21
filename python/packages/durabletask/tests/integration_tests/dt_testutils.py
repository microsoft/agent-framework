# Copyright (c) Microsoft. All rights reserved.

"""Test utilities for durabletask integration tests."""

import json
import time
from typing import Any

from durabletask.azuremanaged.client import DurableTaskSchedulerClient
from durabletask.client import OrchestrationStatus

from agent_framework_durabletask import DurableAIAgentClient


def create_dts_client(endpoint: str, taskhub: str) -> DurableTaskSchedulerClient:
    """
    Create a DurableTaskSchedulerClient with common configuration.

    Args:
        endpoint: The DTS endpoint address
        taskhub: The task hub name

    Returns:
        A configured DurableTaskSchedulerClient instance
    """
    return DurableTaskSchedulerClient(
        host_address=endpoint,
        secure_channel=False,
        taskhub=taskhub,
        token_credential=None,
    )


def create_agent_client(
    endpoint: str,
    taskhub: str,
    max_poll_retries: int = 90,
) -> tuple[DurableTaskSchedulerClient, DurableAIAgentClient]:
    """
    Create a DurableAIAgentClient with the underlying DTS client.

    Args:
        endpoint: The DTS endpoint address
        taskhub: The task hub name
        max_poll_retries: Max poll retries for the agent client

    Returns:
        A tuple of (DurableTaskSchedulerClient, DurableAIAgentClient)
    """
    dts_client = create_dts_client(endpoint, taskhub)
    agent_client = DurableAIAgentClient(dts_client, max_poll_retries=max_poll_retries)
    return dts_client, agent_client


class OrchestrationHelper:
    """Helper class for orchestration-related test operations."""

    def __init__(self, dts_client: DurableTaskSchedulerClient):
        """
        Initialize the orchestration helper.

        Args:
            dts_client: The DurableTaskSchedulerClient instance to use
        """
        self.client = dts_client

    def wait_for_orchestration(
        self,
        instance_id: str,
        timeout: float = 60.0,
    ) -> Any:
        """
        Wait for an orchestration to complete.

        Args:
            instance_id: The orchestration instance ID
            timeout: Maximum time to wait in seconds

        Returns:
            The final OrchestrationMetadata

        Raises:
            TimeoutError: If the orchestration doesn't complete within timeout
            RuntimeError: If the orchestration fails
        """
        # Use the built-in wait_for_orchestration_completion method
        metadata = self.client.wait_for_orchestration_completion(
            instance_id=instance_id,
            timeout=int(timeout),
        )

        if metadata is None:
            raise TimeoutError(f"Orchestration {instance_id} did not complete within {timeout} seconds")

        # Check if failed or terminated
        if metadata.runtime_status == OrchestrationStatus.FAILED:
            raise RuntimeError(f"Orchestration {instance_id} failed: {metadata.serialized_custom_status}")
        if metadata.runtime_status == OrchestrationStatus.TERMINATED:
            raise RuntimeError(f"Orchestration {instance_id} was terminated")

        return metadata

    def wait_for_orchestration_with_output(
        self,
        instance_id: str,
        timeout: float = 60.0,
    ) -> tuple[Any, Any]:
        """
        Wait for an orchestration to complete and return its output.

        Args:
            instance_id: The orchestration instance ID
            timeout: Maximum time to wait in seconds

        Returns:
            A tuple of (OrchestrationMetadata, output)

        Raises:
            TimeoutError: If the orchestration doesn't complete within timeout
            RuntimeError: If the orchestration fails
        """
        metadata = self.wait_for_orchestration(instance_id, timeout)

        # The output should be available in the metadata
        return metadata, metadata.serialized_output

    def get_orchestration_status(self, instance_id: str) -> Any | None:
        """
        Get the current status of an orchestration.

        Args:
            instance_id: The orchestration instance ID

        Returns:
            The OrchestrationMetadata or None if not found
        """
        try:
            # Try to wait with a short timeout to get current status
            return self.client.wait_for_orchestration_completion(
                instance_id=instance_id,
                timeout=1,  # Very short timeout, just checking status
            )
        except Exception:
            return None

    def raise_event(
        self,
        instance_id: str,
        event_name: str,
        event_data: Any = None,
    ) -> None:
        """
        Raise an external event to an orchestration.

        Args:
            instance_id: The orchestration instance ID
            event_name: The name of the event
            event_data: The event data payload
        """
        self.client.raise_orchestration_event(instance_id, event_name, data=event_data)

    def wait_for_notification(self, instance_id: str, timeout_seconds: int = 30) -> bool:
        """Wait for the orchestration to reach a notification point.

        Polls the orchestration status until it appears to be waiting for approval.

        Args:
            instance_id: The orchestration instance ID
            timeout_seconds: Maximum time to wait

        Returns:
            True if notification detected, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                metadata = self.client.get_orchestration_state(
                    instance_id=instance_id,
                )

                if metadata:
                    # Check if we're waiting for approval by examining custom status
                    if metadata.serialized_custom_status:
                        try:
                            custom_status = json.loads(metadata.serialized_custom_status)
                            # Handle both string and dict custom status
                            status_str = custom_status if isinstance(custom_status, str) else str(custom_status)
                            if status_str.lower().startswith("requesting human feedback"):
                                return True
                        except (json.JSONDecodeError, AttributeError):
                            # If it's not JSON, treat as plain string
                            if metadata.serialized_custom_status.lower().startswith("requesting human feedback"):
                                return True

                    # Check for terminal states
                    if metadata.runtime_status.name == "COMPLETED" or metadata.runtime_status.name == "FAILED":
                        return False
            except Exception:
                # Silently ignore transient errors during polling (e.g., network issues, service unavailable).
                # The loop will retry until timeout, allowing the service to recover.
                pass

            time.sleep(1)

        return False
