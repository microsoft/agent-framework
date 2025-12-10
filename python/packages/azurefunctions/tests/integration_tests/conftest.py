# Copyright (c) Microsoft. All rights reserved.
"""
Pytest configuration for Durable Agent Framework tests.

This module provides fixtures and configuration for pytest.
"""

import subprocess
from collections.abc import Iterator, Mapping
from typing import Any

import pytest
import requests

from .testutils import (
    FunctionAppStartupError,
    build_base_url,
    cleanup_function_app,
    find_available_port,
    get_sample_path_from_marker,
    load_and_validate_env,
    start_function_app,
    wait_for_function_app_ready,
)


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "orchestration: marks tests that use orchestrations (require Azurite)")
    config.addinivalue_line(
        "markers",
        "sample(path): specify the sample directory path for the test (e.g., @pytest.mark.sample('01_single_agent'))",
    )


@pytest.fixture(scope="session")
def function_app_running() -> bool:
    """
    Check if the function app is running on localhost:7071.

    This fixture can be used to skip tests if the function app is not available.
    """
    try:
        response = requests.get("http://localhost:7071/api/health", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


@pytest.fixture(scope="session")
def skip_if_no_function_app(function_app_running: bool) -> None:
    """Skip test if function app is not running."""
    if not function_app_running:
        pytest.skip("Function app is not running on http://localhost:7071")


@pytest.fixture(scope="module")
def function_app_for_test(request: pytest.FixtureRequest) -> Iterator[dict[str, int | str]]:
    """
    Start the function app for the corresponding sample based on marker.

    This fixture:
    1. Determines which sample to run from @pytest.mark.sample()
    2. Validates environment variables
    3. Starts the function app using 'func start'
    4. Waits for the app to be ready
    5. Tears down the app after tests complete

    Usage:
    @pytest.mark.sample("01_single_agent")
    @pytest.mark.usefixtures("function_app_for_test")
    class TestSample01SingleAgent:
        ...
    """
    # Get sample path from marker
    sample_path, error_message = get_sample_path_from_marker(request)
    if error_message:
        pytest.fail(error_message)

    assert sample_path is not None, "Sample path must be resolved before starting the function app"

    # Load .env file if it exists and validate required env vars
    load_and_validate_env()

    max_attempts = 3
    last_error: Exception | None = None
    func_process: subprocess.Popen[Any] | None = None
    base_url = ""
    port = 0

    for _ in range(max_attempts):
        port = find_available_port()
        base_url = build_base_url(port)
        func_process = start_function_app(sample_path, port)

        try:
            wait_for_function_app_ready(func_process, port)
            last_error = None
            break
        except FunctionAppStartupError as exc:
            last_error = exc
            cleanup_function_app(func_process)
            func_process = None

    if func_process is None:
        error_message = f"Function app failed to start after {max_attempts} attempt(s)."
        if last_error is not None:
            error_message += f" Last error: {last_error}"
        pytest.fail(error_message)

    try:
        yield {"base_url": base_url, "port": port}
    finally:
        if func_process is not None:
            cleanup_function_app(func_process)


@pytest.fixture(scope="module")
def base_url(function_app_for_test: Mapping[str, int | str]) -> str:
    """Expose the function app's base URL to tests."""
    return str(function_app_for_test["base_url"])
