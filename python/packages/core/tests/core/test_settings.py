# Copyright (c) Microsoft. All rights reserved.

"""Tests for load_settings() function."""

import os
import tempfile
from typing import TypedDict

import pytest

from agent_framework import SecretString, load_settings


class SimpleSettings(TypedDict, total=False):
    api_key: str | None
    timeout: int | None
    enabled: bool | None
    rate_limit: float | None


class RequiredFieldSettings(TypedDict, total=False):
    name: str | None
    optional_field: str | None


class SecretSettings(TypedDict, total=False):
    api_key: SecretString | None
    username: str | None


class ExclusiveSettings(TypedDict, total=False):
    source_a: str | None
    source_b: str | None
    other: str | None


class TestLoadSettingsBasic:
    """Test basic load_settings functionality."""

    def test_fields_are_none_when_unset(self) -> None:
        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_")

        assert settings["api_key"] is None
        assert settings["timeout"] is None
        assert settings["enabled"] is None
        assert settings["rate_limit"] is None

    def test_overrides(self) -> None:
        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_", timeout=60, enabled=False)

        assert settings["timeout"] == 60
        assert settings["enabled"] is False

    def test_none_overrides_are_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_TIMEOUT", "120")

        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_", timeout=None)

        # timeout=None is filtered, so env var wins
        assert settings["timeout"] == 120

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_API_KEY", "test-key-123")
        monkeypatch.setenv("TEST_APP_TIMEOUT", "120")
        monkeypatch.setenv("TEST_APP_ENABLED", "false")

        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_")

        assert settings["api_key"] == "test-key-123"
        assert settings["timeout"] == 120
        assert settings["enabled"] is False

    def test_overrides_beat_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_TIMEOUT", "120")

        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_", timeout=60)

        assert settings["timeout"] == 60

    def test_no_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_KEY", "no-prefix-key")

        settings = load_settings(SimpleSettings, api_key=None)

        assert settings["api_key"] == "no-prefix-key"


class TestDotenvFile:
    """Test .env file loading."""

    def test_load_from_dotenv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_APP_API_KEY", raising=False)
        monkeypatch.delenv("TEST_APP_TIMEOUT", raising=False)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_APP_API_KEY=dotenv-key\n")
            f.write("TEST_APP_TIMEOUT=90\n")
            f.flush()
            env_path = f.name

        try:
            settings = load_settings(SimpleSettings, env_prefix="TEST_APP_", env_file_path=env_path)

            assert settings["api_key"] == "dotenv-key"
            assert settings["timeout"] == 90
        finally:
            os.unlink(env_path)

    def test_dotenv_overrides_env_vars_when_env_file_path_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_API_KEY", "real-env-key")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_APP_API_KEY=dotenv-key\n")
            f.flush()
            env_path = f.name

        try:
            settings = load_settings(SimpleSettings, env_prefix="TEST_APP_", env_file_path=env_path)

            assert settings["api_key"] == "dotenv-key"
        finally:
            os.unlink(env_path)

    def test_env_vars_are_used_when_env_file_path_is_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_API_KEY", "real-env-key")
        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_")

        assert settings["api_key"] == "real-env-key"

    def test_overrides_beat_dotenv_and_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_TIMEOUT", "120")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_APP_TIMEOUT=90\n")
            f.flush()
            env_path = f.name

        try:
            settings = load_settings(SimpleSettings, env_prefix="TEST_APP_", env_file_path=env_path, timeout=60)

            assert settings["timeout"] == 60
        finally:
            os.unlink(env_path)

    def test_missing_dotenv_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_settings(SimpleSettings, env_prefix="TEST_APP_", env_file_path="/nonexistent/.env")


class TestSecretString:
    """Test SecretString type handling."""

    def test_secretstring_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECRET_API_KEY", "secret-value")

        settings = load_settings(SecretSettings, env_prefix="SECRET_")

        assert isinstance(settings["api_key"], SecretString)
        assert settings["api_key"] == "secret-value"

    def test_secretstring_from_override(self) -> None:
        settings = load_settings(SecretSettings, env_prefix="SECRET_", api_key="kwarg-secret")

        assert isinstance(settings["api_key"], SecretString)
        assert settings["api_key"] == "kwarg-secret"

    def test_secretstring_masked_in_repr(self) -> None:
        s = SecretString("my-secret")
        assert "my-secret" not in repr(s)
        assert "**********" in repr(s)

    def test_get_secret_value_compat(self) -> None:
        s = SecretString("my-secret")

        assert s.get_secret_value() == "my-secret"
        assert isinstance(s.get_secret_value(), str)


class TestTypeCoercion:
    """Test type coercion from string values."""

    def test_int_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_TIMEOUT", "42")

        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_")

        assert settings["timeout"] == 42
        assert isinstance(settings["timeout"], int)

    def test_float_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_APP_RATE_LIMIT", "2.5")

        settings = load_settings(SimpleSettings, env_prefix="TEST_APP_")

        assert settings["rate_limit"] == 2.5
        assert isinstance(settings["rate_limit"], float)

    def test_bool_coercion_true_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for true_val in ["true", "True", "TRUE", "1", "yes", "on"]:
            monkeypatch.setenv("TEST_APP_ENABLED", true_val)
            settings = load_settings(SimpleSettings, env_prefix="TEST_APP_")
            assert settings["enabled"] is True, f"Failed for {true_val}"

    def test_bool_coercion_false_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for false_val in ["false", "False", "FALSE", "0", "no", "off"]:
            monkeypatch.setenv("TEST_APP_ENABLED", false_val)
            settings = load_settings(SimpleSettings, env_prefix="TEST_APP_")
            assert settings["enabled"] is False, f"Failed for {false_val}"


class TestRequiredFields:
    """Test required field validation."""

    def test_required_field_provided(self) -> None:
        settings = load_settings(
            RequiredFieldSettings,
            env_prefix="TEST_",
            required_fields=["name"],
            name="my-app",
        )

        assert settings["name"] == "my-app"
        assert settings["optional_field"] is None

    def test_required_field_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_NAME", "env-app")

        settings = load_settings(RequiredFieldSettings, env_prefix="TEST_", required_fields=["name"])

        assert settings["name"] == "env-app"

    def test_required_field_missing_raises(self) -> None:
        from agent_framework.exceptions import SettingNotFoundError

        with pytest.raises(SettingNotFoundError, match="Required setting 'name'"):
            load_settings(RequiredFieldSettings, env_prefix="TEST_", required_fields=["name"])

    def test_without_required_fields_param_allows_none(self) -> None:
        settings = load_settings(RequiredFieldSettings, env_prefix="TEST_")

        assert settings["name"] is None


class TestOverrideTypeValidation:
    """Test override type validation."""

    def test_invalid_type_raises(self) -> None:

        with pytest.raises(ValueError, match="Invalid type for setting 'api_key'"):
            load_settings(SimpleSettings, env_prefix="TEST_", api_key={"bad": "type"})

    def test_valid_types_accepted(self) -> None:
        settings = load_settings(SimpleSettings, env_prefix="TEST_", timeout=42, enabled=True)

        assert settings["timeout"] == 42
        assert settings["enabled"] is True

    def test_str_accepted_for_secretstring(self) -> None:
        settings = load_settings(SecretSettings, env_prefix="TEST_", api_key="plain-string")

        assert isinstance(settings["api_key"], SecretString)
        assert settings["api_key"] == "plain-string"


class TestMutuallyExclusive:
    """Test mutually exclusive field validation via tuple entries in required_fields."""

    def test_exactly_one_set_passes(self) -> None:
        settings = load_settings(
            ExclusiveSettings,
            env_prefix="TEST_",
            required_fields=[("source_a", "source_b")],
            source_a="value-a",
        )

        assert settings["source_a"] == "value-a"
        assert settings["source_b"] is None

    def test_none_set_raises(self) -> None:
        from agent_framework.exceptions import SettingNotFoundError

        with pytest.raises(SettingNotFoundError, match="none was set"):
            load_settings(
                ExclusiveSettings,
                env_prefix="TEST_",
                required_fields=[("source_a", "source_b")],
            )

    def test_both_set_raises(self) -> None:
        from agent_framework.exceptions import SettingNotFoundError

        with pytest.raises(SettingNotFoundError, match="multiple were set"):
            load_settings(
                ExclusiveSettings,
                env_prefix="TEST_",
                required_fields=[("source_a", "source_b")],
                source_a="a",
                source_b="b",
            )

    def test_env_var_counts_as_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_SOURCE_B", "env-b")

        settings = load_settings(
            ExclusiveSettings,
            env_prefix="TEST_",
            required_fields=[("source_a", "source_b")],
        )

        assert settings["source_b"] == "env-b"

    def test_env_var_and_override_both_set_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from agent_framework.exceptions import SettingNotFoundError

        monkeypatch.setenv("TEST_SOURCE_B", "env-b")

        with pytest.raises(SettingNotFoundError, match="multiple were set"):
            load_settings(
                ExclusiveSettings,
                env_prefix="TEST_",
                required_fields=[("source_a", "source_b")],
                source_a="a",
            )

    def test_other_fields_unaffected(self) -> None:
        settings = load_settings(
            ExclusiveSettings,
            env_prefix="TEST_",
            required_fields=[("source_a", "source_b")],
            source_a="a",
            other="extra",
        )

        assert settings["source_a"] == "a"
        assert settings["other"] == "extra"

    def test_mixed_required_and_exclusive(self) -> None:
        settings = load_settings(
            ExclusiveSettings,
            env_prefix="TEST_",
            required_fields=["other", ("source_a", "source_b")],
            source_b="b",
            other="required-val",
        )

        assert settings["other"] == "required-val"
        assert settings["source_b"] == "b"
        assert settings["source_a"] is None
