# Copyright (c) Microsoft. All rights reserved.

import copy
import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pytest import MonkeyPatch, mark, param

from samples.getting_started.chat_client.azure_ai_chat_client import (
    main as azure_ai_chat_client,
)
from samples.getting_started.chat_client.azure_assistants_client import (
    main as azure_assistants_client,
)
from samples.getting_started.chat_client.azure_chat_client import (
    main as azure_chat_client,
)
from samples.getting_started.chat_client.azure_responses_client import (
    main as azure_responses_client,
)
from samples.getting_started.chat_client.chat_response_cancellation import (
    main as chat_response_cancellation,
)
from samples.getting_started.chat_client.openai_assistants_client import (
    main as openai_assistants_client,
)
from samples.getting_started.chat_client.openai_chat_client import (
    main as openai_chat_client,
)
from samples.getting_started.chat_client.openai_responses_client import (
    main as openai_responses_client,
)

# Environment variable for controlling sample tests
RUN_SAMPLES_TESTS = "RUN_SAMPLES_TESTS"

# All chat client samples across providers
chat_client_samples = [
    # Azure Chat Client samples
    param(
        azure_assistants_client,
        [],  # Non-interactive sample
        id="azure_assistants_client",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_chat_client,
        [],  # Non-interactive sample
        id="azure_chat_client",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_responses_client,
        [],  # Non-interactive sample
        id="azure_responses_client",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # Azure AI Chat Client samples
    param(
        azure_ai_chat_client,
        [],  # Non-interactive sample
        id="azure_ai_chat_client",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # OpenAI Chat Client samples
    param(
        openai_assistants_client,
        [],  # Non-interactive sample
        id="openai_assistants_client",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_chat_client,
        [],  # Non-interactive sample
        id="openai_chat_client",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client,
        [],  # Non-interactive sample
        id="openai_responses_client",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # General Chat Client samples (no provider-specific environment variable)
    param(
        chat_response_cancellation,
        [],  # Non-interactive sample
        id="chat_response_cancellation",
        marks=pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
    ),
]


@mark.parametrize("sample, responses", chat_client_samples)
async def test_chat_client_samples(
    sample: Callable[..., Awaitable[Any]],
    responses: list[str],
    monkeypatch: MonkeyPatch,
):
    """Test chat client samples with input mocking and retry logic."""
    saved_responses = copy.deepcopy(responses)

    def reset():
        responses.clear()
        responses.extend(saved_responses)

    def mock_input(prompt: str = "") -> str:
        return responses.pop(0) if responses else "exit"

    monkeypatch.setattr("builtins.input", mock_input)
    await sample
