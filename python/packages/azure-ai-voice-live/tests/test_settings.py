# Copyright (c) Microsoft. All rights reserved.

from agent_framework_azure_voice_live import AzureVoiceLiveSettings


def test_settings_defaults():
    """All fields default to None."""
    settings = AzureVoiceLiveSettings()
    assert settings.endpoint is None
    assert settings.api_key is None
    assert settings.model is None
    assert settings.api_version is None


def test_settings_from_constructor():
    """Constructor args populate fields."""
    settings = AzureVoiceLiveSettings(
        endpoint="https://test.services.ai.azure.com",
        api_key="test-key",
        model="gpt-4o-realtime-preview",
        api_version="2025-10-01",
    )
    assert settings.endpoint == "https://test.services.ai.azure.com"
    assert settings.api_key.get_secret_value() == "test-key"
    assert settings.model == "gpt-4o-realtime-preview"
    assert settings.api_version == "2025-10-01"


def test_settings_from_env_vars(monkeypatch):
    """Environment variables populate fields via AZURE_VOICELIVE_ prefix."""
    monkeypatch.setenv("AZURE_VOICELIVE_ENDPOINT", "https://env.services.ai.azure.com")
    monkeypatch.setenv("AZURE_VOICELIVE_API_KEY", "env-key")
    monkeypatch.setenv("AZURE_VOICELIVE_MODEL", "gpt-4o-realtime-env")
    monkeypatch.setenv("AZURE_VOICELIVE_API_VERSION", "2025-12-01")

    settings = AzureVoiceLiveSettings()
    assert settings.endpoint == "https://env.services.ai.azure.com"
    assert settings.api_key.get_secret_value() == "env-key"
    assert settings.model == "gpt-4o-realtime-env"
    assert settings.api_version == "2025-12-01"


def test_settings_constructor_overrides_env(monkeypatch):
    """Constructor args take priority over env vars."""
    monkeypatch.setenv("AZURE_VOICELIVE_ENDPOINT", "https://env.services.ai.azure.com")
    monkeypatch.setenv("AZURE_VOICELIVE_MODEL", "env-model")

    settings = AzureVoiceLiveSettings(
        endpoint="https://constructor.services.ai.azure.com",
        model="constructor-model",
    )
    assert settings.endpoint == "https://constructor.services.ai.azure.com"
    assert settings.model == "constructor-model"
