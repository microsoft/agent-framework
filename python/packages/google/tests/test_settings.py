# Copyright (c) Microsoft. All rights reserved.
import pytest

from agent_framework_google._chat_client import GoogleAISettings

# region GoogleAISettings Tests


def test_google_ai_settings_from_env(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings initialization from environment variables."""
    settings = GoogleAISettings()
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == google_ai_unit_test_env["GOOGLE_AI_API_KEY"]
    assert settings.chat_model_id == google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"]


def test_google_ai_settings_from_params() -> None:
    """Test GoogleAISettings initialization from parameters."""
    settings = GoogleAISettings(
        api_key="test-key",
        chat_model_id="gemini-1.5-flash",
    )
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "test-key"
    assert settings.chat_model_id == "gemini-1.5-flash"


@pytest.mark.parametrize("exclude_list", [["GOOGLE_AI_API_KEY"]], indirect=True)
def test_google_ai_settings_missing_api_key(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings when API key is missing."""
    settings = GoogleAISettings()
    assert settings.api_key is None
    assert settings.chat_model_id == google_ai_unit_test_env["GOOGLE_AI_CHAT_MODEL_ID"]


@pytest.mark.parametrize("exclude_list", [["GOOGLE_AI_CHAT_MODEL_ID"]], indirect=True)
def test_google_ai_settings_missing_model_id(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings when model ID is missing."""
    settings = GoogleAISettings()
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == google_ai_unit_test_env["GOOGLE_AI_API_KEY"]
    assert settings.chat_model_id is None


def test_google_ai_settings_override_env() -> None:
    """Test GoogleAISettings parameter override of environment variables."""
    settings = GoogleAISettings(
        api_key="override-key",
        chat_model_id="gemini-2.0-flash",
    )
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "override-key"
    assert settings.chat_model_id == "gemini-2.0-flash"


# endregion
