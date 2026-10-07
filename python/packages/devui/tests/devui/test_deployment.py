# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for DevUI deployment helpers."""

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_framework_devui._deployment import DeploymentManager
from agent_framework_devui.models._discovery_models import DeploymentConfig


async def test_generate_dockerfile_omits_auth_flag_from_cmd(tmp_path: Path) -> None:
    """Dockerfile generation must not emit the removed `--auth` CLI flag."""
    manager = DeploymentManager()
    config = DeploymentConfig(
        entity_id="test-agent",
        resource_group="test-rg",
        app_name="test-app",
        region="eastus",
        ui_mode="user",
    )

    dockerfile_path = await manager._generate_dockerfile(tmp_path, config)
    dockerfile_content = dockerfile_path.read_text()

    assert 'CMD ["devui", "/app/entity", "--mode", "user", "--host", "0.0.0.0", "--port", "8080"]' in dockerfile_content
    assert '"--auth"' not in dockerfile_content
    assert "DEVUI_AUTH_TOKEN" not in dockerfile_content


async def test_deploy_to_azure_redacts_auth_token_in_logs(caplog, tmp_path: Path) -> None:
    """Azure deployment command logging must redact DEVUI_AUTH_TOKEN."""
    manager = DeploymentManager()
    config = DeploymentConfig(
        entity_id="test-agent",
        resource_group="test-rg",
        app_name="test-app",
        region="eastus",
        ui_mode="user",
    )

    # Use a deterministic fake token for testing
    fake_token = "SECRET-TOKEN-VALUE-123"
    event_queue = asyncio.Queue()

    # Mock subprocess to avoid real Azure deployment
    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.stdout = AsyncMock()
    # Return empty bytes to break the read loop
    mock_process.stdout.readline = AsyncMock(side_effect=[b""])
    mock_process.wait = AsyncMock(return_value=0)
    mock_process.communicate = AsyncMock(return_value=(b"", b""))

    actual_cmd = None

    def capture_subprocess_exec(*args, **kwargs):
        nonlocal actual_cmd
        # Only capture the deployment command (not the environment discovery command)
        if "containerapp" in args and "up" in args:
            actual_cmd = args
        return mock_process

    # Also mock the environment discovery and FQDN extraction to avoid subprocess calls
    with (
        patch.object(manager, "_discover_container_app_environment", return_value=None),
        patch.object(
            manager, "_extract_fqdn_from_output", return_value="https://test-app.eastus.azurecontainerapps.io"
        ),
        patch("asyncio.create_subprocess_exec", side_effect=capture_subprocess_exec),
        caplog.at_level(logging.INFO, logger="agent_framework_devui._deployment"),
    ):
        await manager._deploy_to_azure(config, tmp_path, fake_token, event_queue)

    # Verify the real token does NOT appear in logs
    assert fake_token not in caplog.text, "Real auth token must not appear in logs"

    # Verify the redacted representation DOES appear in logs
    assert "DEVUI_AUTH_TOKEN=***" in caplog.text, "Redacted token should appear in logs"

    # Verify the actual command passed to subprocess still contains the real token
    # This ensures the deployment itself still works
    assert actual_cmd is not None, "Subprocess should have been called"
    token_arg = f"DEVUI_AUTH_TOKEN={fake_token}"
    assert token_arg in actual_cmd, "Real token must be in the actual command for deployment"
    # Check that the redacted version is NOT in the actual command
    assert "DEVUI_AUTH_TOKEN=***" not in actual_cmd, "Redacted token must not be in the actual command"
