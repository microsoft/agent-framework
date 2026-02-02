# Copyright (c) Microsoft. All rights reserved.
"""Pytest configuration and fixtures for durabletask integration tests."""

import asyncio
import logging
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest
import redis.asyncio as aioredis
from dotenv import load_dotenv
from durabletask.azuremanaged.client import DurableTaskSchedulerClient

# Add the integration_tests directory to the path so testutils can be imported
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

# Configure logging to reduce noise during tests
logging.basicConfig(level=logging.WARNING)


def _get_dts_endpoint() -> str:
    """Get the DTS endpoint from environment or use default."""
    return os.getenv("ENDPOINT", "http://localhost:8080")


def _check_dts_available(endpoint: str | None = None) -> bool:
    """Check if DTS emulator is available at the given endpoint."""
    try:
        resolved_endpoint: str = _get_dts_endpoint() if endpoint is None else endpoint
        DurableTaskSchedulerClient(
            host_address=resolved_endpoint,
            secure_channel=False,
            taskhub="test",
            token_credential=None,
        )
        return True
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
    run_integration = os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    skip_integration = pytest.mark.skip(reason="RUN_INTEGRATION_TESTS not set to 'true'")

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
        if "integration_test" in item.keywords and not run_integration:
            item.add_marker(skip_integration)
        if "requires_azure_openai" in item.keywords and not azure_openai_available:
            item.add_marker(skip_azure_openai)
        if "requires_dts" in item.keywords and not dts_available:
            item.add_marker(skip_dts)
        if "requires_redis" in item.keywords and not redis_available:
            item.add_marker(skip_redis)


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
    """
    Start a worker process for the current test module by running the sample worker.py.

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
    sample_path: Path = Path(__file__).parents[4] / "samples" / "getting_started" / "durabletask" / sample_name
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
    time.sleep(2)

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
