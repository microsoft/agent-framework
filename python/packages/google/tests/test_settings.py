# Copyright (c) Microsoft. All rights reserved.
import pytest

from agent_framework_google._chat_client import GoogleAISettings, VertexAISettings


# region GoogleAISettings Tests


def test_google_ai_settings_from_env(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings initialization from environment variables."""
    settings = GoogleAISettings()
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == google_ai_unit_test_env["GOOGLE_AI_API_KEY"]
    assert settings.model_id == google_ai_unit_test_env["GOOGLE_AI_MODEL_ID"]


def test_google_ai_settings_from_params() -> None:
    """Test GoogleAISettings initialization from parameters."""
    settings = GoogleAISettings(
        api_key="test-key",
        model_id="gemini-1.5-flash",
    )
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "test-key"
    assert settings.model_id == "gemini-1.5-flash"


@pytest.mark.parametrize("exclude_list", [["GOOGLE_AI_API_KEY"]], indirect=True)
def test_google_ai_settings_missing_api_key(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings when API key is missing."""
    settings = GoogleAISettings()
    assert settings.api_key is None
    assert settings.model_id == google_ai_unit_test_env["GOOGLE_AI_MODEL_ID"]


@pytest.mark.parametrize("exclude_list", [["GOOGLE_AI_MODEL_ID"]], indirect=True)
def test_google_ai_settings_missing_model_id(google_ai_unit_test_env: dict[str, str]) -> None:
    """Test GoogleAISettings when model ID is missing."""
    settings = GoogleAISettings()
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == google_ai_unit_test_env["GOOGLE_AI_API_KEY"]
    assert settings.model_id is None


def test_google_ai_settings_override_env() -> None:
    """Test GoogleAISettings parameter override of environment variables."""
    settings = GoogleAISettings(
        api_key="override-key",
        model_id="gemini-2.0-flash",
    )
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "override-key"
    assert settings.model_id == "gemini-2.0-flash"


# endregion


# region VertexAISettings Tests


def test_vertex_ai_settings_from_env(vertex_ai_unit_test_env: dict[str, str]) -> None:
    """Test VertexAISettings initialization from environment variables."""
    settings = VertexAISettings()
    assert settings.project_id == vertex_ai_unit_test_env["VERTEX_AI_PROJECT_ID"]
    assert settings.location == vertex_ai_unit_test_env["VERTEX_AI_LOCATION"]
    assert settings.model_id == vertex_ai_unit_test_env["VERTEX_AI_MODEL_ID"]


def test_vertex_ai_settings_from_params() -> None:
    """Test VertexAISettings initialization from parameters."""
    settings = VertexAISettings(
        project_id="my-project",
        location="europe-west4",
        model_id="gemini-1.5-pro",
        credentials_path="/path/to/creds.json",
    )
    assert settings.project_id == "my-project"
    assert settings.location == "europe-west4"
    assert settings.model_id == "gemini-1.5-pro"
    assert settings.credentials_path == "/path/to/creds.json"


@pytest.mark.parametrize("exclude_list", [["VERTEX_AI_PROJECT_ID"]], indirect=True)
def test_vertex_ai_settings_missing_project_id(vertex_ai_unit_test_env: dict[str, str]) -> None:
    """Test VertexAISettings when project ID is missing."""
    settings = VertexAISettings()
    assert settings.project_id is None
    assert settings.location == vertex_ai_unit_test_env["VERTEX_AI_LOCATION"]
    assert settings.model_id == vertex_ai_unit_test_env["VERTEX_AI_MODEL_ID"]


@pytest.mark.parametrize("exclude_list", [["VERTEX_AI_LOCATION"]], indirect=True)
def test_vertex_ai_settings_missing_location(vertex_ai_unit_test_env: dict[str, str]) -> None:
    """Test VertexAISettings when location is missing."""
    settings = VertexAISettings()
    assert settings.project_id == vertex_ai_unit_test_env["VERTEX_AI_PROJECT_ID"]
    assert settings.location is None
    assert settings.model_id == vertex_ai_unit_test_env["VERTEX_AI_MODEL_ID"]


@pytest.mark.parametrize("exclude_list", [["VERTEX_AI_MODEL_ID"]], indirect=True)
def test_vertex_ai_settings_missing_model_id(vertex_ai_unit_test_env: dict[str, str]) -> None:
    """Test VertexAISettings when model ID is missing."""
    settings = VertexAISettings()
    assert settings.project_id == vertex_ai_unit_test_env["VERTEX_AI_PROJECT_ID"]
    assert settings.location == vertex_ai_unit_test_env["VERTEX_AI_LOCATION"]
    assert settings.model_id is None


def test_vertex_ai_settings_override_env() -> None:
    """Test VertexAISettings parameter override of environment variables."""
    settings = VertexAISettings(
        project_id="override-project",
        location="asia-southeast1",
        model_id="gemini-2.0-flash",
    )
    assert settings.project_id == "override-project"
    assert settings.location == "asia-southeast1"
    assert settings.model_id == "gemini-2.0-flash"


def test_vertex_ai_settings_credentials_path() -> None:
    """Test VertexAISettings with credentials path."""
    settings = VertexAISettings(
        project_id="test-project",
        location="us-central1",
        model_id="gemini-1.5-pro",
        credentials_path="/custom/path/creds.json",
    )
    assert settings.credentials_path == "/custom/path/creds.json"


# endregion
