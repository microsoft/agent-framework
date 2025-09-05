# Copyright (c) Microsoft. All rights reserved.

import copy
import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pytest import MonkeyPatch, mark, param

from samples.getting_started.telemetry.agent import main as telemetry_agent
from samples.getting_started.telemetry.interactive import main as telemetry_interactive
from samples.getting_started.telemetry.scenarios import main as telemetry_scenarios
from samples.getting_started.telemetry.workflow import main as telemetry_workflow
from tests.sample_utils import retry

# Environment variable for controlling sample tests
RUN_SAMPLES_TESTS = "RUN_SAMPLES_TESTS"

# All telemetry samples
telemetry_samples = [
    param(
        telemetry_agent,
        ["What's the weather in Seattle?", "exit"],  # Interactive sample - ask question then exit
        id="telemetry_agent",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        telemetry_interactive,
        ["What's the weather in London?", "exit"],  # Interactive sample - ask question then exit
        id="telemetry_interactive",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        telemetry_scenarios,
        [],  # Non-interactive sample
        id="telemetry_scenarios",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        telemetry_workflow,
        [],  # Non-interactive sample
        id="telemetry_workflow",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
]


@mark.parametrize("sample, responses", telemetry_samples)
async def test_telemetry_samples(sample: Callable[..., Awaitable[Any]], responses: list[str], monkeypatch: MonkeyPatch):
    """Test telemetry samples with input mocking and retry logic."""
    saved_responses = copy.deepcopy(responses)

    def reset():
        responses.clear()
        responses.extend(saved_responses)

    def mock_input(prompt: str = "") -> str:
        return responses.pop(0) if responses else "exit"

    monkeypatch.setattr("builtins.input", mock_input)
    await retry(sample, retries=3, reset=reset)
