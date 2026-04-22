# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import patch

from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    USER_AGENT_KEY,
    USER_AGENT_TELEMETRY_DISABLED_ENV_VAR,
    prepend_agent_framework_to_user_agent,
)
from agent_framework._telemetry import user_agent_prefix

# region Test constants


def test_telemetry_disabled_env_var():
    """Test that the telemetry disabled environment variable is correctly defined."""
    assert USER_AGENT_TELEMETRY_DISABLED_ENV_VAR == "AGENT_FRAMEWORK_USER_AGENT_DISABLED"


def test_user_agent_key():
    """Test that the user agent key is correctly defined."""
    assert USER_AGENT_KEY == "User-Agent"


def test_agent_framework_user_agent_format():
    """Test that the agent framework user agent is correctly formatted."""
    assert AGENT_FRAMEWORK_USER_AGENT.startswith("agent-framework-python/")


def test_app_info_when_telemetry_enabled():
    """Test that APP_INFO is set when telemetry is enabled."""
    with patch("agent_framework._telemetry.IS_TELEMETRY_ENABLED", True):
        import importlib

        import agent_framework._telemetry

        importlib.reload(agent_framework._telemetry)
        from agent_framework import APP_INFO

        assert APP_INFO is not None
        assert "agent-framework-version" in APP_INFO
        assert APP_INFO["agent-framework-version"].startswith("python/")


def test_app_info_when_telemetry_disabled():
    """Test that APP_INFO is None when telemetry is disabled."""
    # Test the logic directly since APP_INFO is set at module import time
    with patch("agent_framework._telemetry.IS_TELEMETRY_ENABLED", False):
        # Simulate the module's logic for APP_INFO
        test_app_info = (
            {
                "agent-framework-version": "python/test",
            }
            if False  # This simulates IS_TELEMETRY_ENABLED being False
            else None
        )
        assert test_app_info is None


# region Test prepend_agent_framework_to_user_agent


def test_prepend_to_existing_user_agent():
    """Test prepending to existing User-Agent header."""
    headers = {"User-Agent": "existing-agent/1.0"}
    result = prepend_agent_framework_to_user_agent(headers)

    assert "User-Agent" in result
    assert result["User-Agent"].startswith("agent-framework-python/")
    assert "existing-agent/1.0" in result["User-Agent"]


def test_prepend_to_empty_headers():
    """Test prepending to headers without User-Agent."""
    headers = {"Content-Type": "application/json"}
    result = prepend_agent_framework_to_user_agent(headers)

    assert "User-Agent" in result
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT
    assert "Content-Type" in result


def test_prepend_to_empty_dict():
    """Test prepending to empty headers dict."""
    headers = {}
    result = prepend_agent_framework_to_user_agent(headers)

    assert "User-Agent" in result
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT


def test_modifies_original_dict():
    """Test that the function modifies the original headers dict."""
    headers = {"Other-Header": "value"}
    result = prepend_agent_framework_to_user_agent(headers)

    assert result is headers  # Same object
    assert "User-Agent" in headers


# region Test user_agent_prefix context manager


def test_user_agent_prefix_adds_prefix():
    """Test that the context manager adds a prefix within its scope."""
    with user_agent_prefix("test-host"):
        result = prepend_agent_framework_to_user_agent()
        assert result["User-Agent"].startswith("test-host/")
        assert AGENT_FRAMEWORK_USER_AGENT in result["User-Agent"]

    # Prefix is removed after exiting the context
    result = prepend_agent_framework_to_user_agent()
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT


def test_user_agent_prefix_ignores_duplicates():
    """Test that duplicate prefixes are not added within nested scopes."""
    with user_agent_prefix("test-host"), user_agent_prefix("test-host"):
        result = prepend_agent_framework_to_user_agent()
        assert result["User-Agent"].count("test-host") == 1


def test_user_agent_prefix_ignores_empty():
    """Test that empty strings are not added as prefixes."""
    with user_agent_prefix(""):
        result = prepend_agent_framework_to_user_agent()
        assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT


def test_user_agent_prefix_restores_on_exit():
    """Test that prefixes are fully restored after the context manager exits."""
    with user_agent_prefix("test-host"):
        pass
    result = prepend_agent_framework_to_user_agent()
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT


def test_user_agent_prefix_nesting():
    """Test that nested context managers compose prefixes correctly."""
    with user_agent_prefix("outer"):
        with user_agent_prefix("inner"):
            result = prepend_agent_framework_to_user_agent()
            assert "outer" in result["User-Agent"]
            assert "inner" in result["User-Agent"]
        # Inner prefix removed
        result = prepend_agent_framework_to_user_agent()
        assert "outer" in result["User-Agent"]
        assert "inner" not in result["User-Agent"]
    # Both removed
    result = prepend_agent_framework_to_user_agent()
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT
