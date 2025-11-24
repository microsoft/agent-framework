# Copyright (c) Microsoft. All rights reserved.

import copy
import os
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pytest import MonkeyPatch, mark, param
from samples.getting_started.agents.azure_ai.azure_ai_with_function_tools import (
    mixed_tools_example as azure_ai_with_function_tools_mixed,
)
from samples.getting_started.agents.azure_ai.azure_ai_with_function_tools import (
    tools_on_agent_level as azure_ai_with_function_tools_agent,
)
from samples.getting_started.agents.azure_ai.azure_ai_with_function_tools import (
    tools_on_run_level as azure_ai_with_function_tools_run,
)
from samples.getting_started.agents.azure_ai.azure_ai_with_local_mcp import (
    main as azure_ai_with_local_mcp,
)

from samples.getting_started.agents.azure_ai.azure_ai_basic import (
    main as azure_ai_basic,
)
from samples.getting_started.agents.azure_ai.azure_ai_with_code_interpreter import (
    main as azure_ai_with_code_interpreter,
)
from samples.getting_started.agents.azure_ai.azure_ai_with_existing_agent import (
    main as azure_ai_with_existing_agent,
)
from samples.getting_started.agents.azure_ai.azure_ai_with_explicit_settings import (
    main as azure_ai_with_explicit_settings,
)
from samples.getting_started.agents.azure_ai.azure_ai_with_thread import (
    main as azure_ai_with_thread,
)
from samples.getting_started.agents.azure_openai.azure_assistants_basic import (
    main as azure_assistants_basic,
)
from samples.getting_started.agents.azure_openai.azure_assistants_with_code_interpreter import (
    main as azure_assistants_with_code_interpreter,
)
from samples.getting_started.agents.azure_openai.azure_assistants_with_existing_assistant import (
    main as azure_assistants_with_existing_assistant,
)
from samples.getting_started.agents.azure_openai.azure_assistants_with_explicit_settings import (
    main as azure_assistants_with_explicit_settings,
)
from samples.getting_started.agents.azure_openai.azure_assistants_with_function_tools import (
    main as azure_assistants_with_function_tools,
)
from samples.getting_started.agents.azure_openai.azure_assistants_with_thread import (
    main as azure_assistants_with_thread,
)
from samples.getting_started.agents.azure_openai.azure_chat_client_basic import (
    main as azure_chat_client_basic,
)
from samples.getting_started.agents.azure_openai.azure_chat_client_with_explicit_settings import (
    main as azure_chat_client_with_explicit_settings,
)
from samples.getting_started.agents.azure_openai.azure_chat_client_with_function_tools import (
    main as azure_chat_client_with_function_tools,
)
from samples.getting_started.agents.azure_openai.azure_chat_client_with_thread import (
    main as azure_chat_client_with_thread,
)
from samples.getting_started.agents.azure_openai.azure_responses_client_basic import (
    main as azure_responses_client_basic,
)
from samples.getting_started.agents.azure_openai.azure_responses_client_with_code_interpreter import (
    main as azure_responses_client_with_code_interpreter,
)
from samples.getting_started.agents.azure_openai.azure_responses_client_with_explicit_settings import (
    main as azure_responses_client_with_explicit_settings,
)
from samples.getting_started.agents.azure_openai.azure_responses_client_with_function_tools import (
    main as azure_responses_client_with_function_tools,
)
from samples.getting_started.agents.azure_openai.azure_responses_client_with_thread import (
    main as azure_responses_client_with_thread,
)
from samples.getting_started.agents.openai.openai_assistants_basic import (
    main as openai_assistants_basic,
)
from samples.getting_started.agents.openai.openai_assistants_with_code_interpreter import (
    main as openai_assistants_with_code_interpreter,
)
from samples.getting_started.agents.openai.openai_assistants_with_existing_assistant import (
    main as openai_assistants_with_existing_assistant,
)
from samples.getting_started.agents.openai.openai_assistants_with_explicit_settings import (
    main as openai_assistants_with_explicit_settings,
)
from samples.getting_started.agents.openai.openai_assistants_with_file_search import (
    main as openai_assistants_with_file_search,
)
from samples.getting_started.agents.openai.openai_assistants_with_function_tools import (
    main as openai_assistants_with_function_tools,
)
from samples.getting_started.agents.openai.openai_assistants_with_thread import (
    main as openai_assistants_with_thread,
)
from samples.getting_started.agents.openai.openai_chat_client_basic import (
    main as openai_chat_client_basic,
)
from samples.getting_started.agents.openai.openai_chat_client_with_explicit_settings import (
    main as openai_chat_client_with_explicit_settings,
)
from samples.getting_started.agents.openai.openai_chat_client_with_function_tools import (
    main as openai_chat_client_with_function_tools,
)
from samples.getting_started.agents.openai.openai_chat_client_with_local_mcp import (
    main as openai_chat_client_with_local_mcp,
)
from samples.getting_started.agents.openai.openai_chat_client_with_thread import (
    main as openai_chat_client_with_thread,
)
from samples.getting_started.agents.openai.openai_chat_client_with_web_search import (
    main as openai_chat_client_with_web_search,
)
from samples.getting_started.agents.openai.openai_responses_client_basic import (
    main as openai_responses_client_basic,
)
from samples.getting_started.agents.openai.openai_responses_client_reasoning import (
    main as openai_responses_client_reasoning,
)
from samples.getting_started.agents.openai.openai_responses_client_with_code_interpreter import (
    main as openai_responses_client_with_code_interpreter,
)
from samples.getting_started.agents.openai.openai_responses_client_with_explicit_settings import (
    main as openai_responses_client_with_explicit_settings,
)
from samples.getting_started.agents.openai.openai_responses_client_with_file_search import (
    main as openai_responses_client_with_file_search,
)
from samples.getting_started.agents.openai.openai_responses_client_with_function_tools import (
    main as openai_responses_client_with_function_tools,
)
from samples.getting_started.agents.openai.openai_responses_client_with_local_mcp import (
    main as openai_responses_client_with_local_mcp,
)
from samples.getting_started.agents.openai.openai_responses_client_with_thread import (
    main as openai_responses_client_with_thread,
)
from samples.getting_started.agents.openai.openai_responses_client_with_web_search import (
    main as openai_responses_client_with_web_search,
)

# Environment variable for controlling sample tests
RUN_SAMPLES_TESTS = "RUN_SAMPLES_TESTS"

# All agent samples across providers
agent_samples = [
    # Azure Assistants Agent samples
    param(
        azure_assistants_basic,
        [],  # Non-interactive sample
        id="azure_assistants_basic",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_assistants_with_code_interpreter,
        [],  # Non-interactive sample
        id="azure_assistants_with_code_interpreter",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_assistants_with_function_tools,
        [],  # Non-interactive sample
        id="azure_assistants_with_function_tools",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_assistants_with_existing_assistant,
        [],  # Non-interactive sample
        id="azure_assistants_with_existing_assistant",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_assistants_with_explicit_settings,
        [],  # Non-interactive sample
        id="azure_assistants_with_explicit_settings",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_assistants_with_thread,
        [],  # Non-interactive sample
        id="azure_assistants_with_thread",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # Azure Chat Client Agent samples
    param(
        azure_chat_client_basic,
        [],  # Non-interactive sample
        id="azure_chat_client_basic",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_chat_client_with_explicit_settings,
        [],  # Non-interactive sample
        id="azure_chat_client_with_explicit_settings",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_chat_client_with_function_tools,
        [],  # Non-interactive sample
        id="azure_chat_client_with_function_tools",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_chat_client_with_thread,
        [],  # Non-interactive sample
        id="azure_chat_client_with_thread",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # Azure Responses Client Agent samples
    param(
        azure_responses_client_basic,
        [],  # Non-interactive sample
        id="azure_responses_client_basic",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_responses_client_with_code_interpreter,
        [],  # Non-interactive sample
        id="azure_responses_client_with_code_interpreter",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_responses_client_with_explicit_settings,
        [],  # Non-interactive sample
        id="azure_responses_client_with_explicit_settings",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_responses_client_with_function_tools,
        [],  # Non-interactive sample
        id="azure_responses_client_with_function_tools",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_responses_client_with_thread,
        [],  # Non-interactive sample
        id="azure_responses_client_with_thread",
        marks=[
            pytest.mark.azure,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # Azure AI Agent samples
    param(
        azure_ai_basic,
        [],  # Non-interactive sample
        id="azure_ai_basic",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_code_interpreter,
        [],  # Non-interactive sample
        id="azure_ai_with_code_interpreter",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_existing_agent,
        [],  # Non-interactive sample
        id="azure_ai_with_existing_agent",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_explicit_settings,
        [],  # Non-interactive sample
        id="azure_ai_with_explicit_settings",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_function_tools_agent,
        [],  # Non-interactive sample
        id="azure_ai_with_function_tools",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_function_tools_run,
        [],  # Non-interactive sample
        id="azure_ai_with_function_tools",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_function_tools_mixed,
        [],  # Non-interactive sample
        id="azure_ai_with_function_tools",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_thread,
        [],  # Non-interactive sample
        id="azure_ai_with_thread",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        azure_ai_with_local_mcp,
        [],  # Non-interactive sample
        id="azure_ai_with_local_mcp",
        marks=[
            pytest.mark.azure_ai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # OpenAI Assistants Agent samples
    param(
        openai_assistants_basic,
        [],  # Non-interactive sample
        id="openai_assistants_basic",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_assistants_with_code_interpreter,
        [],  # Non-interactive sample
        id="openai_assistants_with_code_interpreter",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_assistants_with_existing_assistant,
        [],  # Non-interactive sample
        id="openai_assistants_with_existing_assistant",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_assistants_with_explicit_settings,
        [],  # Non-interactive sample
        id="openai_assistants_with_explicit_settings",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_assistants_with_file_search,
        [],  # Non-interactive sample
        id="openai_assistants_with_file_search",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
            pytest.mark.skip(reason="OpenAI file search functionality is currently broken - tracked in GitHub issue"),
        ],
    ),
    param(
        openai_assistants_with_function_tools,
        [],  # Non-interactive sample
        id="openai_assistants_with_function_tools",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_assistants_with_thread,
        [],  # Non-interactive sample
        id="openai_assistants_with_thread",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # OpenAI Chat Client Agent samples
    param(
        openai_chat_client_basic,
        [],  # Non-interactive sample
        id="openai_chat_client_basic",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_chat_client_with_explicit_settings,
        [],  # Non-interactive sample
        id="openai_chat_client_with_explicit_settings",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_chat_client_with_function_tools,
        [],  # Non-interactive sample
        id="openai_chat_client_with_function_tools",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_chat_client_with_local_mcp,
        [],  # Non-interactive sample
        id="openai_chat_client_with_local_mcp",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_chat_client_with_thread,
        [],  # Non-interactive sample
        id="openai_chat_client_with_thread",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_chat_client_with_web_search,
        [],  # Non-interactive sample
        id="openai_chat_client_with_web_search",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    # OpenAI Responses Client Agent samples
    param(
        openai_responses_client_basic,
        [],  # Non-interactive sample
        id="openai_responses_client_basic",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client_reasoning,
        [],  # Non-interactive sample
        id="openai_responses_client_reasoning",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client_with_code_interpreter,
        [],  # Non-interactive sample
        id="openai_responses_client_with_code_interpreter",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client_with_explicit_settings,
        [],  # Non-interactive sample
        id="openai_responses_client_with_explicit_settings",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client_with_file_search,
        [],  # Non-interactive sample
        id="openai_responses_client_with_file_search",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
            pytest.mark.skip(reason="OpenAI file search functionality is currently broken - tracked in GitHub issue"),
        ],
    ),
    param(
        openai_responses_client_with_function_tools,
        [],  # Non-interactive sample
        id="openai_responses_client_with_function_tools",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client_with_local_mcp,
        [],  # Non-interactive sample
        id="openai_responses_client_with_local_mcp",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client_with_thread,
        [],  # Non-interactive sample
        id="openai_responses_client_with_thread",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
    param(
        openai_responses_client_with_web_search,
        [],  # Non-interactive sample
        id="openai_responses_client_with_web_search",
        marks=[
            pytest.mark.openai,
            pytest.mark.skipif(os.getenv(RUN_SAMPLES_TESTS, None) is None, reason="Not running sample tests."),
        ],
    ),
]


@pytest.mark.flaky
@mark.parametrize("sample, responses", agent_samples)
async def test_agent_samples(sample: Callable[..., Awaitable[Any]], responses: list[str], monkeypatch: MonkeyPatch):
    """Test agent samples with input mocking and retry logic."""
    saved_responses = copy.deepcopy(responses)

    def reset():
        responses.clear()
        responses.extend(saved_responses)

    def mock_input(prompt: str = "") -> str:
        return responses.pop(0) if responses else "exit"

    monkeypatch.setattr("builtins.input", mock_input)
    await sample
