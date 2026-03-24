# Copyright (c) Microsoft. All rights reserved.
"""Pytest configuration and fixtures for durabletask integration tests."""

import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

import pytest
import redis.asyncio as aioredis
from dotenv import load_dotenv
from durabletask.azuremanaged.client import DurableTaskSchedulerClient
from durabletask.client import OrchestrationStatus

from agent_framework_durabletask import DurableAIAgentClient

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# Configure logging to reduce noise during tests
logging.basicConfig(level=logging.WARNING)


# =============================================================================
# Environment and Service Checks
# =============================================================================


def _get_dts_endpoint() -> str:
    """Get the DTS endpoint from environment or use default."""
    return os.getenv("ENDPOINT", "http://localhost:8080")


def _check_dts_available(endpoint: str | None = None) -> bool:
    """Check if DTS emulator is available at the given endpoint."""
    try:
        resolved_endpoint: str = _get_dts_endpoint() if endpoint is None else endpoint
        parsed = urlparse(resolved_endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8080

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


def _check_redis_available() -> bool:
    """Check if Redis is available at the default connection string."""
    try:

        async def test_connection() -> bool:
            redis_url = os.getenv("REDIS_CONNECTION_STRING", "redis://localhost:6379")
            try:
                client = aioredis.from_url(redis_url, socket_timeout=2)  # type: ignore[reportUnknownMemberType]
                await client.ping()  # type: ignore[reportUnknownMemberType]
                await client.aclose()  # type: ignore[reportUnknownMemberType]
                return True
            except Exception:
                return False

        return asyncio.run(test_connection())
    except Exception:
        return False


# =============================================================================
# Client Factory Functions
# =============================================================================


def create_dts_client(endpoint: str, taskhub: str) -> DurableTaskSchedulerClient:
    """Create a DurableTaskSchedulerClient with common configuration.

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
    """Create a DurableAIAgentClient with the underlying DTS client.

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


# =============================================================================
# Orchestration Helper Class
# =============================================================================


class OrchestrationHelper:
    """Helper class for orchestration-related test operations."""

    def __init__(self, dts_client: DurableTaskSchedulerClient):
        """Initialize the orchestration helper.

        Args:
            dts_client: The DurableTaskSchedulerClient instance to use
        """
        self.client = dts_client

    def wait_for_orchestration(
        self,
        instance_id: str,
        timeout: float = 60.0,
    ) -> Any:
        """Wait for an orchestration to complete.

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
        """Wait for an orchestration to complete and return its output.

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
        """Get the current status of an orchestration.

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
        """Raise an external event to an orchestration.

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


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "integration_test: mark test as integration test")
    config.addinivalue_line("markers", "requires_dts: mark test as requiring DTS emulator")
    config.addinivalue_line("markers", "requires_azure_openai: mark test as requiring Azure OpenAI")
    config.addinivalue_line("markers", "requires_redis: mark test as requiring Redis")
    config.addinivalue_line(
        "markers",
        "sample(path): specify the sample directory name for the test (e.g., @pytest.mark.sample('01_single_agent'))",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests based on markers and environment availability."""
    # Check Azure OpenAI environment variables
    azure_openai_vars = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
    azure_openai_available = all(os.getenv(var) for var in azure_openai_vars)
    skip_azure_openai = pytest.mark.skip(
        reason=f"Missing required environment variables: {', '.join(azure_openai_vars)}"
    )

    # Check DTS availability
    dts_available = _check_dts_available()
    skip_dts = pytest.mark.skip(reason=f"DTS emulator is not available at {_get_dts_endpoint()}")

    # Check Redis availability
    redis_available = _check_redis_available()
    skip_redis = pytest.mark.skip(reason="Redis is not available at redis://localhost:6379")

    for item in items:
        if "requires_azure_openai" in item.keywords and not azure_openai_available:
            item.add_marker(skip_azure_openai)
        if "requires_dts" in item.keywords and not dts_available:
            item.add_marker(skip_dts)
        if "requires_redis" in item.keywords and not redis_available:
            item.add_marker(skip_redis)


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def dts_endpoint() -> str:
    """Get the DTS endpoint from environment or use default."""
    return _get_dts_endpoint()


@pytest.fixture(scope="session")
def dts_available(dts_endpoint: str) -> bool:
    """Check if DTS emulator is available and responding."""
    if _check_dts_available(dts_endpoint):
        return True
    pytest.skip(f"DTS emulator is not available at {dts_endpoint}")
    return False


@pytest.fixture(scope="session")
def check_azure_openai_env() -> None:
    """Verify Azure OpenAI environment variables are set."""
    required_vars = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        pytest.skip(f"Missing required environment variables: {', '.join(missing)}")


@pytest.fixture(scope="module")
def unique_taskhub() -> str:
    """Generate a unique task hub name for test isolation."""
    # Use a shorter UUID to avoid naming issues
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def worker_process(
    dts_available: bool,
    check_azure_openai_env: None,
    dts_endpoint: str,
    unique_taskhub: str,
    request: pytest.FixtureRequest,
) -> Generator[dict[str, Any], None, None]:
    """Start a worker process for the current test module by running the sample worker.py.

    This fixture:
    1. Determines which sample to run from @pytest.mark.sample()
    2. Starts the sample's worker.py as a subprocess
    3. Waits for the worker to be ready
    4. Tears down the worker after tests complete

    Usage:
    @pytest.mark.sample("01_single_agent")
    class TestSingleAgent:
        ...
    """
    # Get sample path from marker
    sample_marker = request.node.get_closest_marker("sample")  # type: ignore[union-attr]
    if not sample_marker:
        pytest.fail("Test class must have @pytest.mark.sample() marker")

    sample_name: str = cast(str, sample_marker.args[0])  # type: ignore[union-attr]
    sample_path: Path = Path(__file__).parents[4] / "samples" / "04-hosting" / "durabletask" / sample_name
    worker_file: Path = sample_path / "worker.py"

    if not worker_file.exists():
        pytest.fail(f"Sample worker not found: {worker_file}")

    # Set up environment for worker subprocess
    env = os.environ.copy()
    env["ENDPOINT"] = dts_endpoint
    env["TASKHUB"] = unique_taskhub

    # Start worker subprocess
    try:
        # On Windows, use CREATE_NEW_PROCESS_GROUP to allow proper termination
        # shell=True only on Windows to handle PATH resolution
        if sys.platform == "win32":
            process = subprocess.Popen(
                [sys.executable, str(worker_file)],
                cwd=str(sample_path),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                shell=True,
                env=env,
                text=True,
            )
        # On Unix, don't use shell=True to avoid shell wrapper issues
        else:
            process = subprocess.Popen(
                [sys.executable, str(worker_file)],
                cwd=str(sample_path),
                env=env,
                text=True,
            )
    except Exception as e:
        pytest.fail(f"Failed to start worker subprocess: {e}")

    # Wait for worker to initialize
    # The worker needs time to:
    # 1. Start Python and import modules
    # 2. Create Azure OpenAI clients
    # 3. Register agents with the DTS worker
    # 4. Connect to DTS and be ready to receive signals
    #
    # We use a generous wait time because CI environments can be slow,
    # and the first test that runs depends on the worker being fully ready.
    time.sleep(8)

    # Check if process is still running
    if process.poll() is not None:
        stderr_output = process.stderr.read() if process.stderr else ""
        pytest.fail(f"Worker process exited prematurely. stderr: {stderr_output}")

    # Provide worker info to tests
    worker_info = {
        "process": process,
        "endpoint": dts_endpoint,
        "taskhub": unique_taskhub,
    }

    try:
        yield worker_info
    finally:
        # Cleanup: terminate worker subprocess
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except Exception as e:
            logging.warning(f"Error during worker process cleanup: {e}")


@pytest.fixture(scope="module")
def orchestration_helper(worker_process: dict[str, Any]) -> OrchestrationHelper:
    """Create an OrchestrationHelper for the current test module."""
    dts_client = create_dts_client(worker_process["endpoint"], worker_process["taskhub"])
    return OrchestrationHelper(dts_client)


@pytest.fixture(scope="module")
def agent_client_factory(worker_process: dict[str, Any]) -> type:
    """Return a factory class for creating agent clients.

    Usage in tests:
        def test_example(self, agent_client_factory):
            dts_client, agent_client = agent_client_factory.create(max_poll_retries=90)
    """

    class AgentClientFactory:
        """Factory for creating DTS and Agent client pairs."""

        endpoint = worker_process["endpoint"]
        taskhub = worker_process["taskhub"]

        @classmethod
        def create(cls, max_poll_retries: int = 90) -> tuple[DurableTaskSchedulerClient, DurableAIAgentClient]:
            """Create a DTS client and Agent client pair."""
            return create_agent_client(cls.endpoint, cls.taskhub, max_poll_retries)

    return AgentClientFactory
