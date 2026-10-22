# Copyright (c) Microsoft. All rights reserved.

"""Focused tests for DevUI deployment helpers."""

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_framework_devui import _deployment as deployment_module
from agent_framework_devui._deployment import DeploymentManager
from agent_framework_devui.models._discovery_models import DeploymentConfig

FAKE_TOKEN = "fake-test-token-ABC123xyz"

URL_LINE = "Your container app URL: https://test-app.kindfield-12345.eastus.azurecontainerapps.io"


def _make_config() -> DeploymentConfig:
    return DeploymentConfig(
        entity_id="test-agent",
        resource_group="test-rg",
        app_name="test-app",
        region="eastus",
        ui_mode="user",
    )


class _FakeStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""


class _FakeProcess:
    def __init__(self, lines: list[bytes], returncode: int = 0) -> None:
        self.stdout = _FakeStdout(lines)
        self.returncode = returncode
        self.killed = False

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


def _patch_subprocess(monkeypatch: pytest.MonkeyPatch, process: _FakeProcess, captured: list[tuple]) -> None:
    async def _fake_create_subprocess_exec(*args: object, **kwargs: object) -> _FakeProcess:
        captured.append(args)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)


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


@pytest.mark.parametrize("existing_env", ["existing-env", None])
async def test_deploy_to_azure_redacts_token_in_command_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, existing_env: str | None
) -> None:
    """Both env branches must redact the token in logs but pass the real token to az."""
    manager = DeploymentManager()
    config = _make_config()
    queue: asyncio.Queue = asyncio.Queue()
    process = _FakeProcess(lines=[f"{URL_LINE}\n".encode()], returncode=0)
    captured: list[tuple] = []
    _patch_subprocess(monkeypatch, process, captured)
    monkeypatch.setattr(DeploymentManager, "_discover_container_app_environment", AsyncMock(return_value=existing_env))

    with caplog.at_level(logging.INFO, logger=deployment_module.__name__):
        url = await manager._deploy_to_azure(config, tmp_path, FAKE_TOKEN, queue)

    assert url == "https://test-app.kindfield-12345.eastus.azurecontainerapps.io"
    logs = caplog.text
    assert FAKE_TOKEN not in logs
    assert "Running: az containerapp up" in logs
    assert "DEVUI_AUTH_TOKEN=[REDACTED]" in logs
    # Real argv still carries the exact token.
    assert captured
    argv = list(captured[0])
    assert f"DEVUI_AUTH_TOKEN={FAKE_TOKEN}" in argv
    assert not any("[REDACTED]" in str(a) for a in argv)


async def test_deploy_to_azure_redacts_cli_echoed_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI output echoing the token (multiple occurrences) must not leak into DEBUG logs."""
    manager = DeploymentManager()
    config = _make_config()
    queue: asyncio.Queue = asyncio.Queue()
    lines = [
        f"Using token {FAKE_TOKEN} for auth, again {FAKE_TOKEN}\n".encode(),
        f"{URL_LINE}\n".encode(),
    ]
    process = _FakeProcess(lines=lines, returncode=0)
    captured: list[tuple] = []
    _patch_subprocess(monkeypatch, process, captured)
    monkeypatch.setattr(
        DeploymentManager, "_discover_container_app_environment", AsyncMock(return_value="existing-env")
    )

    with caplog.at_level(logging.DEBUG, logger=deployment_module.__name__):
        url = await manager._deploy_to_azure(config, tmp_path, FAKE_TOKEN, queue)

    assert url == "https://test-app.kindfield-12345.eastus.azurecontainerapps.io"
    assert FAKE_TOKEN not in caplog.text
    assert "[REDACTED]" in caplog.text


async def test_deploy_to_azure_failure_redacts_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero exit: queued error events and the raised exception must be redacted."""
    manager = DeploymentManager()
    config = _make_config()
    queue: asyncio.Queue = asyncio.Queue()
    lines = [
        f"ERROR: failed with DEVUI_AUTH_TOKEN={FAKE_TOKEN}\n".encode(),
        f"ERROR: bare token {FAKE_TOKEN} leaked\n".encode(),
    ]
    process = _FakeProcess(lines=lines, returncode=1)
    captured: list[tuple] = []
    _patch_subprocess(monkeypatch, process, captured)
    monkeypatch.setattr(DeploymentManager, "_discover_container_app_environment", AsyncMock(return_value=None))

    with pytest.raises(ValueError, match="Azure deployment failed") as exc_info:
        await manager._deploy_to_azure(config, tmp_path, FAKE_TOKEN, queue)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert events
    for event in events:
        assert FAKE_TOKEN not in event.message
    assert FAKE_TOKEN not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


async def test_deploy_failure_flow_redacts_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Public deploy() failure path: deploy.failed event, stored record, and logs stay redacted."""
    manager = DeploymentManager()
    config = _make_config()
    monkeypatch.setattr(DeploymentManager, "_validate_prerequisites", AsyncMock(return_value=None))
    monkeypatch.setattr(DeploymentManager, "_generate_dockerfile", AsyncMock(return_value=tmp_path / "Dockerfile"))
    monkeypatch.setattr(
        DeploymentManager, "_discover_container_app_environment", AsyncMock(return_value="existing-env")
    )
    lines = [f"ERROR: deploy blew up on {FAKE_TOKEN}\n".encode()]
    process = _FakeProcess(lines=lines, returncode=1)
    captured: list[tuple] = []
    _patch_subprocess(monkeypatch, process, captured)

    with (
        patch.object(deployment_module.secrets, "token_urlsafe", return_value=FAKE_TOKEN),
        caplog.at_level(logging.DEBUG, logger=deployment_module.__name__),
    ):
        events = [event async for event in manager.deploy(config, tmp_path)]

    failed = [e for e in events if e.type == "deploy.failed"]
    assert failed
    assert FAKE_TOKEN not in failed[0].message
    assert FAKE_TOKEN not in caplog.text
    stored = list(manager._deployments.values())
    assert stored and stored[0].status == "failed"
    assert FAKE_TOKEN not in (stored[0].error or "")


async def test_deploy_to_azure_missing_fqdn_redacts_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful exit without a valid URL: FQDN ERROR log must not contain the token."""
    manager = DeploymentManager()
    config = _make_config()
    queue: asyncio.Queue = asyncio.Queue()
    lines = [f"done, token was {FAKE_TOKEN} but no url here\n".encode()]
    process = _FakeProcess(lines=lines, returncode=0)
    captured: list[tuple] = []
    _patch_subprocess(monkeypatch, process, captured)
    monkeypatch.setattr(
        DeploymentManager, "_discover_container_app_environment", AsyncMock(return_value="existing-env")
    )

    with (
        caplog.at_level(logging.DEBUG, logger=deployment_module.__name__),
        pytest.raises(ValueError, match="Could not extract deployment URL"),
    ):
        await manager._deploy_to_azure(config, tmp_path, FAKE_TOKEN, queue)

    assert FAKE_TOKEN not in caplog.text


async def test_deploy_success_keeps_real_auth_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Public deploy() success must still return the real token to the user."""
    manager = DeploymentManager()
    config = _make_config()
    monkeypatch.setattr(DeploymentManager, "_validate_prerequisites", AsyncMock(return_value=None))
    monkeypatch.setattr(DeploymentManager, "_generate_dockerfile", AsyncMock(return_value=tmp_path / "Dockerfile"))
    monkeypatch.setattr(
        DeploymentManager, "_discover_container_app_environment", AsyncMock(return_value="existing-env")
    )
    process = _FakeProcess(lines=[f"{URL_LINE}\n".encode()], returncode=0)
    captured: list[tuple] = []
    _patch_subprocess(monkeypatch, process, captured)

    with patch.object(deployment_module.secrets, "token_urlsafe", return_value=FAKE_TOKEN):
        events = [event async for event in manager.deploy(config, tmp_path)]

    completed = [e for e in events if e.type == "deploy.completed"]
    assert completed
    assert completed[0].auth_token == FAKE_TOKEN
    assert completed[0].url == "https://test-app.kindfield-12345.eastus.azurecontainerapps.io"


async def test_redact_helper_handles_empty_token() -> None:
    """Empty token must leave text untouched (no str.replace('', ...) disaster)."""
    assert deployment_module._redact_auth_token(f"abc {FAKE_TOKEN} def", "") == f"abc {FAKE_TOKEN} def"
