# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import pytest
from agent_framework import ChatMessage, Role
from agent_framework.redis import RedisProvider


def test_redis_provider_import() -> None:
    """Ensure RedisProvider can be imported from agent_framework.redis aggregator."""
    assert RedisProvider is not None


@pytest.fixture
def sample_messages() -> list[ChatMessage]:
    return [
        ChatMessage(role=Role.USER, text="Hello, how are you?"),
        ChatMessage(role=Role.ASSISTANT, text="I'm doing well, thank you!"),
        ChatMessage(role=Role.SYSTEM, text="You are a helpful assistant"),
    ]
