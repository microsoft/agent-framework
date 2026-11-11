# Copyright (c) Microsoft. All rights reserved.

"""Exercise the documented option hook through the real Responses host offline."""

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from agent_framework import Agent, ChatOptions

from agent_framework_foundry_hosting import ResponsesHostServer

from .options_helpers import OptionsClient


@pytest.fixture(scope="module")
def options_sample() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[4]
        / "samples"
        / "04-hosting"
        / "foundry-hosted-agents"
        / "responses"
        / "basic"
        / "options.py"
    )
    spec = importlib.util.spec_from_file_location("foundry_responses_options_sample", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch("dotenv.load_dotenv", return_value=False):
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("nested", [False, True])
async def test_sample_hook_preserves_developer_model_and_other_caller_options(
    options_sample: ModuleType, stream: bool, nested: bool
) -> None:
    model = OptionsClient()
    defaults: ChatOptions = {"model": "developer", "temperature": 0.4, "max_tokens": 256}
    agent = Agent(client=model, default_options=defaults)
    original_defaults = deepcopy(agent.default_options)
    host = ResponsesHostServer(agent, prepare_options=options_sample.prepare_options)
    payload: dict[str, Any] = {
        "input": "hi",
        "model": "caller",
        "temperature": 0.8,
        "max_output_tokens": 300,
        "max_tokens": 200,
        "stream": stream,
        "store": False,
    }
    if nested:
        payload["extra_body"] = {"model": "nested-caller", "temperature": 0.6, "max_tokens": 150}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="http://test") as client:
        response = await client.post("/responses", json=payload)

    assert response.status_code == 200
    assert "response.failed" not in response.text
    if stream:
        assert "event: response.completed" in response.text
    else:
        assert response.json()["status"] == "completed"
    assert len(model.calls) == 1
    assert model.calls[0]["model"] == "developer"
    assert model.calls[0]["temperature"] == (0.6 if nested else 0.8)
    assert model.calls[0]["max_tokens"] == (150 if nested else 200)
    assert agent.default_options == original_defaults
    assert defaults == {"model": "developer", "temperature": 0.4, "max_tokens": 256}
