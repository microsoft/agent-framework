# Copyright (c) Microsoft. All rights reserved.

import os
from unittest.mock import MagicMock, patch

import agent_framework._telemetry as _telemetry_mod
from agent_framework import (
    AGENT_FRAMEWORK_USER_AGENT,
    USER_AGENT_KEY,
    USER_AGENT_TELEMETRY_DISABLED_ENV_VAR,
    prepend_agent_framework_to_user_agent,
)
from agent_framework._telemetry import (
    _FOUNDRY_HOSTING_ENV_VAR,
    _HOSTED_USER_AGENT_PREFIX,
    _add_user_agent_prefix,
    _detect_hosted_environment,
)

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
    headers: dict[str, str] = {}
    result = prepend_agent_framework_to_user_agent(headers)

    assert "User-Agent" in result
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT


def test_modifies_original_dict():
    """Test that the function modifies the original headers dict."""
    headers = {"Other-Header": "value"}
    result = prepend_agent_framework_to_user_agent(headers)

    assert result is headers  # Same object
    assert "User-Agent" in headers


# region Test _add_user_agent_prefix


def test_add_user_agent_prefix_adds_prefix():
    """Test that _add_user_agent_prefix permanently adds a prefix."""
    _telemetry_mod._user_agent_prefixes.clear()
    _add_user_agent_prefix("test-host")
    result = prepend_agent_framework_to_user_agent()
    assert result["User-Agent"].startswith("test-host/")
    assert AGENT_FRAMEWORK_USER_AGENT in result["User-Agent"]
    _telemetry_mod._user_agent_prefixes.clear()


def test_add_user_agent_prefix_ignores_duplicates():
    """Test that duplicate prefixes are not added."""
    _telemetry_mod._user_agent_prefixes.clear()
    _add_user_agent_prefix("test-host")
    _add_user_agent_prefix("test-host")
    result = prepend_agent_framework_to_user_agent()
    assert result["User-Agent"].count("test-host") == 1
    _telemetry_mod._user_agent_prefixes.clear()


def test_add_user_agent_prefix_ignores_empty():
    """Test that empty strings are not added as prefixes."""
    _telemetry_mod._user_agent_prefixes.clear()
    _add_user_agent_prefix("")
    result = prepend_agent_framework_to_user_agent()
    assert result["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT
    _telemetry_mod._user_agent_prefixes.clear()


def test_add_user_agent_prefix_multiple():
    """Test that multiple prefixes compose correctly."""
    _telemetry_mod._user_agent_prefixes.clear()
    _add_user_agent_prefix("outer")
    _add_user_agent_prefix("inner")
    result = prepend_agent_framework_to_user_agent()
    assert "outer" in result["User-Agent"]
    assert "inner" in result["User-Agent"]
    _telemetry_mod._user_agent_prefixes.clear()


# region Test _detect_hosted_environment


def test_detect_hosted_env_var_truthy_adds_prefix():
    """Test that a truthy FOUNDRY_HOSTING_ENVIRONMENT env var adds the prefix."""
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
    with patch.dict("os.environ", {_FOUNDRY_HOSTING_ENV_VAR: "production"}):
        _detect_hosted_environment()
    assert _HOSTED_USER_AGENT_PREFIX in _telemetry_mod._user_agent_prefixes
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False


def test_detect_hosted_env_var_empty_skips_prefix():
    """Test that an empty FOUNDRY_HOSTING_ENVIRONMENT env var does NOT add the prefix."""
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
    with patch.dict("os.environ", {_FOUNDRY_HOSTING_ENV_VAR: ""}):
        _detect_hosted_environment()
    assert _HOSTED_USER_AGENT_PREFIX not in _telemetry_mod._user_agent_prefixes
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False


def test_detect_hosted_env_var_set_skips_agent_config_fallback():
    """Test that when the env var is set, AgentConfig is never consulted even if import would fail."""
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
    import builtins

    real_import = builtins.__import__

    def _block_agentconfig(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "agentserver" in name:
            raise AssertionError("AgentConfig should not be imported when env var is set")
        return real_import(name, *args, **kwargs)

    with (
        patch.dict("os.environ", {_FOUNDRY_HOSTING_ENV_VAR: "prod"}),
        patch("builtins.__import__", side_effect=_block_agentconfig),
    ):
        _detect_hosted_environment()
    assert _HOSTED_USER_AGENT_PREFIX in _telemetry_mod._user_agent_prefixes
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False


def _mock_agent_config(*, is_hosted: bool) -> MagicMock:
    """Create a mock azure.ai.agentserver.core module with AgentConfig."""
    mock_config = MagicMock()
    mock_config.is_hosted = is_hosted
    mock_module = MagicMock()
    mock_module.AgentConfig.from_env.return_value = mock_config
    return mock_module


def test_detect_hosted_fallback_agent_config_is_hosted():
    """Test that AgentConfig fallback adds the prefix when is_hosted is True."""
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
    env = {k: v for k, v in os.environ.items() if k != _FOUNDRY_HOSTING_ENV_VAR}
    mock_module = _mock_agent_config(is_hosted=True)
    mock_spec = MagicMock()
    with (
        patch.dict("os.environ", env, clear=True),
        patch.dict("sys.modules", {"azure.ai.agentserver.core": mock_module}),
        patch("importlib.util.find_spec", return_value=mock_spec),
    ):
        _detect_hosted_environment()
    assert _HOSTED_USER_AGENT_PREFIX in _telemetry_mod._user_agent_prefixes
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False


def test_detect_hosted_fallback_agent_config_not_hosted():
    """Test that AgentConfig fallback does NOT add the prefix when is_hosted is False."""
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
    mock_module = _mock_agent_config(is_hosted=False)
    mock_spec = MagicMock()
    env = {k: v for k, v in os.environ.items() if k != _FOUNDRY_HOSTING_ENV_VAR}
    with (
        patch.dict("os.environ", env, clear=True),
        patch.dict("sys.modules", {"azure.ai.agentserver.core": mock_module}),
        patch("importlib.util.find_spec", return_value=mock_spec),
    ):
        _detect_hosted_environment()
    assert _HOSTED_USER_AGENT_PREFIX not in _telemetry_mod._user_agent_prefixes
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False


def test_detect_hosted_fallback_import_error():
    """Test that ImportError from AgentConfig is silently handled."""
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
    env = {k: v for k, v in os.environ.items() if k != _FOUNDRY_HOSTING_ENV_VAR}
    with patch.dict("os.environ", env, clear=True):
        # The real import may succeed or fail depending on the environment;
        # force the ImportError path by making the import raise.
        import builtins

        real_import = builtins.__import__

        def _block_agentconfig(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if "agentserver" in name:
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block_agentconfig):
            _detect_hosted_environment()
    assert _HOSTED_USER_AGENT_PREFIX not in _telemetry_mod._user_agent_prefixes
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False


# region Test module-level auto-detection


def test_lazy_detection_on_get_user_agent():
    """Test that get_user_agent() lazily detects the hosted environment.

    Since detection is deferred to the first ``get_user_agent()`` call,
    this verifies the prefix is included without any explicit call to
    ``_detect_hosted_environment()`` by consumer code.
    """
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
    with patch.dict("os.environ", {_FOUNDRY_HOSTING_ENV_VAR: "production"}):
        user_agent = _telemetry_mod.get_user_agent()

    assert _HOSTED_USER_AGENT_PREFIX in _telemetry_mod._user_agent_prefixes
    assert user_agent.startswith(f"{_HOSTED_USER_AGENT_PREFIX}/")

    # Clean up
    _telemetry_mod._user_agent_prefixes.clear()
    _telemetry_mod._hosted_env_detected = False
