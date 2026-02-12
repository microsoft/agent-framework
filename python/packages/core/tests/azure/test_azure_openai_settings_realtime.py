# Copyright (c) Microsoft. All rights reserved.
"""Tests for AzureOpenAISettings realtime_deployment_name field."""

from agent_framework.azure._shared import AzureOpenAISettings


def test_realtime_deployment_name_default_none():
    """Test realtime_deployment_name defaults to None."""
    settings = AzureOpenAISettings()
    assert settings.realtime_deployment_name is None


def test_realtime_deployment_name_from_constructor():
    """Test realtime_deployment_name can be set via constructor."""
    settings = AzureOpenAISettings(realtime_deployment_name="gpt-4o-realtime")
    assert settings.realtime_deployment_name == "gpt-4o-realtime"


def test_realtime_deployment_name_from_env(monkeypatch):
    """Test realtime_deployment_name can be set via environment variable."""
    monkeypatch.setenv("AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME", "gpt-4o-realtime-env")
    settings = AzureOpenAISettings()
    assert settings.realtime_deployment_name == "gpt-4o-realtime-env"
