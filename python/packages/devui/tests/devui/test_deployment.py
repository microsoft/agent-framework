# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for DevUI deployment helpers."""

from pathlib import Path

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
