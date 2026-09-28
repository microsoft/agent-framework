# Copyright (c) Microsoft. All rights reserved.

"""Command routing checks shared by the polling and webhook samples."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(params=["polling_app", "app"])
def sample(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.com/telegram")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    path = Path(__file__).parents[1] / f"{request.param}.py"
    spec = importlib.util.spec_from_file_location(f"telegram_sample_{request.param}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("text", "handled"),
    [("/new@otherbot", False), ("/new@MyBot", True), ("/new", True)],
)
async def test_command_target_controls_dispatch(
    sample: Any,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    handled: bool,
) -> None:
    bot = SimpleNamespace(id=123456, me=AsyncMock(return_value=SimpleNamespace(username="mybot")))
    monkeypatch.setattr(sample, "bot", bot, raising=False)
    handle_command = AsyncMock(return_value=True)
    to_run = AsyncMock()
    monkeypatch.setattr(sample, "handle_command", handle_command)
    monkeypatch.setattr(sample, "telegram_to_run", to_run)
    update = {
        "update_id": 1,
        "message": {
            "message_id": 2,
            "from": {"id": 42},
            "chat": {"id": -123, "type": "supergroup"},
            "text": text,
        },
    }

    if sample.__name__.endswith("polling_app"):
        await sample.handle_update(bot, update)
    else:
        await sample.handle_update(update)

    if handled:
        handle_command.assert_awaited_once()
    else:
        handle_command.assert_not_awaited()
    to_run.assert_not_awaited()
