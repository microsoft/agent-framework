# Copyright (c) Microsoft. All rights reserved.
"""
Shared test helper utilities for sample integration tests.

This module provides common utilities for testing Azure Functions samples.
"""

import os
import socket
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
import requests

# Configuration
TIMEOUT = 30  # seconds
ORCHESTRATION_TIMEOUT = 180  # seconds for orchestrations
_DEFAULT_HOST = "localhost"


class FunctionAppStartupError(RuntimeError):
    """Raised when the Azure Functions host fails to start reliably."""

    pass


def _load_env_file_if_present() -> None:
    """Load environment variables from the local .env file when available."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
    except ImportError:
        # python-dotenv not available; rely on existing environment
        pass


def _should_skip_azure_functions_integration_tests() -> tuple[bool, str]:
    """Determine whether Azure Functions integration tests should be skipped."""
    _load_env_file_if_present()

    run_integration_tests = os.getenv("RUN_INTEGRATION_TESTS", "false").lower() == "true"
    if not run_integration_tests:
        return (
            True,
            "Integration tests are disabled. Set RUN_INTEGRATION_TESTS=true to enable Azure Functions sample tests.",
        )

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    if not endpoint or endpoint == "https://your-resource.openai.azure.com/":
        return True, "No real AZURE_OPENAI_ENDPOINT provided; skipping integration tests."

    deployment_name = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "").strip()
    if not deployment_name or deployment_name == "your-deployment-name":
        return True, "No real AZURE_OPENAI_CHAT_DEPLOYMENT_NAME provided; skipping integration tests."

    return False, "Integration tests enabled."


_SKIP_AZURE_FUNCTIONS_INTEGRATION_TESTS, _AZURE_FUNCTIONS_SKIP_REASON = _should_skip_azure_functions_integration_tests()

skip_if_azure_functions_integration_tests_disabled = pytest.mark.skipif(
    _SKIP_AZURE_FUNCTIONS_INTEGRATION_TESTS,
    reason=_AZURE_FUNCTIONS_SKIP_REASON,
)


class SampleTestHelper:
    """Helper class for testing samples."""

    @staticmethod
    def post_json(url: str, data: dict[str, Any], timeout: int = TIMEOUT) -> requests.Response:
        """POST JSON data to a URL."""
        return requests.post(url, json=data, headers={"Content-Type": "application/json"}, timeout=timeout)

    @staticmethod
    def post_text(url: str, text: str, timeout: int = TIMEOUT) -> requests.Response:
        """POST plain text to a URL."""
        return requests.post(url, data=text, headers={"Content-Type": "text/plain"}, timeout=timeout)

    @staticmethod
    def get(url: str, timeout: int = TIMEOUT) -> requests.Response:
        """GET request to a URL."""
        return requests.get(url, timeout=timeout)

    @staticmethod
    def wait_for_orchestration(
        status_url: str, max_wait: int = ORCHESTRATION_TIMEOUT, poll_interval: int = 2
    ) -> dict[str, Any]:
        """
        Wait for an orchestration to complete.

        Args:
            status_url: URL to poll for orchestration status
            max_wait: Maximum seconds to wait
            poll_interval: Seconds between polls

        Returns:
            Final orchestration status

        Raises:
            TimeoutError: If orchestration doesn't complete in time
        """
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = requests.get(status_url, timeout=TIMEOUT)
            response.raise_for_status()
            status = response.json()

            runtime_status = status.get("runtimeStatus", "")
            if runtime_status in ["Completed", "Failed", "Terminated"]:
                return status

            time.sleep(poll_interval)

        raise TimeoutError(f"Orchestration did not complete within {max_wait} seconds")

    @staticmethod
    def wait_for_orchestration_with_output(
        status_url: str, max_wait: int = ORCHESTRATION_TIMEOUT, poll_interval: int = 2
    ) -> dict[str, Any]:
        """
        Wait for an orchestration to complete and have output available.

        This is a specialized version of wait_for_orchestration that also
        ensures the output field is present, handling timing race conditions.

        Args:
            status_url: URL to poll for orchestration status
            max_wait: Maximum seconds to wait
            poll_interval: Seconds between polls

        Returns:
            Final orchestration status with output

        Raises:
            TimeoutError: If orchestration doesn't complete with output in time
        """
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = requests.get(status_url, timeout=TIMEOUT)
            response.raise_for_status()
            status = response.json()

            runtime_status = status.get("runtimeStatus", "")
            if runtime_status in ["Failed", "Terminated"]:
                return status
            if runtime_status == "Completed" and status.get("output"):
                return status
            # If completed but no output, continue polling for a bit more to
            # handle the race condition where output has not been persisted yet.

            time.sleep(poll_interval)

        # Provide detailed error message based on final status
        final_response = requests.get(status_url, timeout=TIMEOUT)
        final_response.raise_for_status()
        final_status = final_response.json()
        final_runtime_status = final_status.get("runtimeStatus", "Unknown")

        if final_runtime_status == "Completed":
            if "output" not in final_status:
                raise TimeoutError(
                    "Orchestration completed but 'output' field is missing after "
                    f"{max_wait} seconds. Final status: {final_status}"
                )
            if not final_status["output"]:
                raise TimeoutError(
                    "Orchestration completed but output is empty after "
                    f"{max_wait} seconds. Final status: {final_status}"
                )
            raise TimeoutError(
                "Orchestration completed with output but validation failed after "
                f"{max_wait} seconds. Final status: {final_status}"
            )
        raise TimeoutError(
            "Orchestration did not complete within "
            f"{max_wait} seconds. Final status: {final_runtime_status}, "
            f"Full status: {final_status}"
        )


# Function App Lifecycle Management Helpers


def _resolve_repo_root() -> Path:
    """Resolve the repository root, preferring GITHUB_WORKSPACE when available."""
    workspace = os.getenv("GITHUB_WORKSPACE")
    if workspace:
        candidate = Path(workspace).expanduser()
        if not (candidate / "samples").exists() and (candidate / "python" / "samples").exists():
            return (candidate / "python").resolve()
        return candidate.resolve()

    # If `GITHUB_WORKSPACE` is not set,
    # go up from testutils.py -> integration_tests -> tests -> azurefunctions -> packages -> python
    return Path(__file__).resolve().parents[4]


def get_sample_path_from_marker(request) -> tuple[Path | None, str | None]:
    """
    Get sample path from @pytest.mark.sample() marker.

    Returns a tuple of (sample_path, error_message).
    If successful, error_message is None.
    If failed, sample_path is None and error_message contains the reason.
    """
    marker = request.node.get_closest_marker("sample")

    if not marker:
        return (
            None,
            (
                "No @pytest.mark.sample() marker found on test. Add pytestmark with "
                "@pytest.mark.sample('sample_name') to the test module."
            ),
        )

    if not marker.args:
        return (
            None,
            "@pytest.mark.sample() marker found but no sample name provided. Use @pytest.mark.sample('sample_name').",
        )

    sample_name = marker.args[0]
    repo_root = _resolve_repo_root()
    sample_path = repo_root / "samples" / "getting_started" / "azure_functions" / sample_name

    if not sample_path.exists():
        return None, f"Sample directory does not exist: {sample_path}"

    return sample_path, None


def find_available_port(host: str = _DEFAULT_HOST) -> int:
    """Find an available TCP port on the given host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def build_base_url(port: int, host: str = _DEFAULT_HOST) -> str:
    """Construct a base URL for the Azure Functions host."""
    return f"http://{host}:{port}"


def is_port_in_use(port: int, host: str = _DEFAULT_HOST) -> bool:
    """
    Check if a port is already in use.

    Returns True if the port is in use, False otherwise.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0


def load_and_validate_env() -> None:
    """
    Load .env file from current directory if it exists,
    then validate that required environment variables are present.

    Raises pytest.fail if required environment variables are missing.
    """
    _load_env_file_if_present()

    # Required environment variables for Azure Functions samples
    # These match the variables defined in .env.example
    required_env_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
        "AzureWebJobsStorage",
        "DURABLE_TASK_SCHEDULER_CONNECTION_STRING",
        "FUNCTIONS_WORKER_RUNTIME",
    ]

    # Check if required env vars are set
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]

    if missing_vars:
        pytest.fail(
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            "Please create a .env file in tests/integration_tests/ based on .env.example or "
            "set these variables in your environment."
        )


def start_function_app(sample_path: Path, port: int) -> subprocess.Popen:
    """
    Start a function app in the specified sample directory.

    Returns the subprocess.Popen object for the running process.
    """
    env = os.environ.copy()
    # Use a unique TASKHUB_NAME for each test run to ensure test isolation.
    # This prevents conflicts between parallel or repeated test runs, as Durable Functions
    # use the task hub name to separate orchestration state.
    env["TASKHUB_NAME"] = f"test{uuid.uuid4().hex[:8]}"

    # On Windows, use CREATE_NEW_PROCESS_GROUP to allow proper termination
    # shell=True only on Windows to handle PATH resolution
    if sys.platform == "win32":
        return subprocess.Popen(
            ["func", "start", "--port", str(port)],
            cwd=str(sample_path),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            shell=True,
            env=env,
        )
    # On Unix, don't use shell=True to avoid shell wrapper issues
    return subprocess.Popen(["func", "start", "--port", str(port)], cwd=str(sample_path), env=env)


def wait_for_function_app_ready(func_process: subprocess.Popen, port: int, max_wait: int = 60) -> None:
    """Block until the Azure Functions host responds healthy or fail fast."""
    start_time = time.time()
    health_url = f"{build_base_url(port)}/api/health"
    last_error: Exception | None = None

    while time.time() - start_time < max_wait:
        # If the process exited early, capture any previously seen error and fail fast.
        if func_process.poll() is not None:
            raise FunctionAppStartupError(
                f"Function app process exited with code {func_process.returncode} before becoming healthy"
            ) from last_error

        if is_port_in_use(port):
            try:
                response = requests.get(health_url, timeout=5)
                if response.status_code == 200:
                    return
                last_error = RuntimeError(f"Health check returned {response.status_code}")
            except requests.RequestException as exc:
                last_error = exc

        time.sleep(1)

    raise FunctionAppStartupError(
        f"Function app did not become healthy on port {port} within {max_wait} seconds"
    ) from last_error


def cleanup_function_app(func_process: subprocess.Popen) -> None:
    """
    Clean up the function app process and all its children.

    Uses psutil if available for more thorough cleanup, falls back to basic termination.
    """
    try:
        import psutil

        if func_process.poll() is None:  # Process still running
            # Get parent process
            parent = psutil.Process(func_process.pid)

            # Get all child processes recursively
            children = parent.children(recursive=True)

            # Kill children first
            for child in children:
                with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    child.kill()

            # Kill parent
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                parent.kill()

            # Wait for all to terminate
            _gone, alive = psutil.wait_procs(children + [parent], timeout=3)

            # Force kill any remaining
            for proc in alive:
                with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    proc.kill()
    except ImportError:
        # Fallback if psutil not available
        try:
            if func_process.poll() is None:
                func_process.kill()
                func_process.wait()
        except Exception:
            # Ignore all exceptions during fallback cleanup; best effort to terminate process.
            pass
    except Exception:
        pass  # Best effort cleanup

    # Give the port time to be released
    time.sleep(2)
