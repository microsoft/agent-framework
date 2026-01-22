# Copyright (c) Microsoft. All rights reserved.

"""Tests for AFSettings base class."""

import os
import tempfile

import pytest
from pydantic import SecretStr

from agent_framework._settings import AFSettings, BackendConfig


class SimpleSettings(AFSettings):
    """Simple settings class for testing basic functionality."""

    env_prefix = "TEST_APP_"

    api_key: str | None = None
    timeout: int = 30
    enabled: bool = True
    rate_limit: float = 1.5


class BackendAwareSettings(AFSettings):
    """Settings class with backend support for testing."""

    env_prefix = "PROVIDER_"
    backend_env_var = "PROVIDER_BACKEND"
    backend_configs = {
        "primary": BackendConfig(
            env_prefix="PRIMARY_",
            precedence=1,
            detection_fields={"primary_key"},
        ),
        "secondary": BackendConfig(
            env_prefix="SECONDARY_",
            precedence=2,
            detection_fields={"secondary_key"},
        ),
    }

    api_key: str | None = None
    primary_key: str | None = None
    secondary_key: str | None = None
    base_url: str | None = None


class SecretSettings(AFSettings):
    """Settings class with SecretStr for testing."""

    env_prefix = "SECRET_"

    api_key: SecretStr | None = None
    username: str | None = None


class TestAFSettingsBasic:
    """Test basic AFSettings functionality."""

    def test_default_values(self) -> None:
        """Test that default values are used when no env vars or kwargs."""
        settings = SimpleSettings()

        assert settings.api_key is None
        assert settings.timeout == 30
        assert settings.enabled is True
        assert settings.rate_limit == 1.5

    def test_kwargs_override_defaults(self) -> None:
        """Test that kwargs override default values."""
        settings = SimpleSettings(timeout=60, enabled=False)

        assert settings.timeout == 60
        assert settings.enabled is False

    def test_none_kwargs_are_filtered(self) -> None:
        """Test that None kwargs don't override defaults."""
        settings = SimpleSettings(timeout=None)

        assert settings.timeout == 30

    def test_env_vars_override_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that environment variables override default values."""
        monkeypatch.setenv("TEST_APP_API_KEY", "test-key-123")
        monkeypatch.setenv("TEST_APP_TIMEOUT", "120")
        monkeypatch.setenv("TEST_APP_ENABLED", "false")

        settings = SimpleSettings()

        assert settings.api_key == "test-key-123"
        assert settings.timeout == 120
        assert settings.enabled is False

    def test_kwargs_override_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that kwargs override environment variables."""
        monkeypatch.setenv("TEST_APP_TIMEOUT", "120")

        settings = SimpleSettings(timeout=60)

        assert settings.timeout == 60


class TestDotenvFile:
    """Test .env file loading."""

    def test_load_from_dotenv(self) -> None:
        """Test loading settings from a .env file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_APP_API_KEY=dotenv-key\n")
            f.write("TEST_APP_TIMEOUT=90\n")
            f.flush()
            env_path = f.name

        try:
            settings = SimpleSettings(env_file_path=env_path)

            assert settings.api_key == "dotenv-key"
            assert settings.timeout == 90
        finally:
            os.unlink(env_path)

    def test_dotenv_with_quotes(self) -> None:
        """Test loading settings with quoted values from .env file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('TEST_APP_API_KEY="quoted-key"\n')
            f.write("TEST_APP_BASE_URL='single-quoted'\n")
            f.flush()
            env_path = f.name

        try:
            # Use a class with base_url field
            settings = SimpleSettings(env_file_path=env_path)

            assert settings.api_key == "quoted-key"
        finally:
            os.unlink(env_path)

    def test_dotenv_with_comments(self) -> None:
        """Test that comments in .env file are ignored."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# This is a comment\n")
            f.write("TEST_APP_API_KEY=key-value\n")
            f.write("# Another comment\n")
            f.flush()
            env_path = f.name

        try:
            settings = SimpleSettings(env_file_path=env_path)

            assert settings.api_key == "key-value"
        finally:
            os.unlink(env_path)

    def test_dotenv_with_export_prefix(self) -> None:
        """Test that 'export' prefix in .env file is handled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("export TEST_APP_API_KEY=export-key\n")
            f.flush()
            env_path = f.name

        try:
            settings = SimpleSettings(env_file_path=env_path)

            assert settings.api_key == "export-key"
        finally:
            os.unlink(env_path)

    def test_env_vars_override_dotenv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that real env vars override dotenv values."""
        monkeypatch.setenv("TEST_APP_API_KEY", "real-env-key")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_APP_API_KEY=dotenv-key\n")
            f.flush()
            env_path = f.name

        try:
            settings = SimpleSettings(env_file_path=env_path)

            assert settings.api_key == "real-env-key"
        finally:
            os.unlink(env_path)

    def test_missing_dotenv_file(self) -> None:
        """Test that missing .env file is handled gracefully."""
        settings = SimpleSettings(env_file_path="/nonexistent/.env")

        assert settings.api_key is None


class TestSecretStr:
    """Test SecretStr type handling."""

    def test_secretstr_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that SecretStr values are properly loaded from env."""
        monkeypatch.setenv("SECRET_API_KEY", "secret-value")

        settings = SecretSettings()

        assert isinstance(settings.api_key, SecretStr)
        assert settings.api_key.get_secret_value() == "secret-value"

    def test_secretstr_from_kwargs(self) -> None:
        """Test that string kwargs are converted to SecretStr."""
        settings = SecretSettings(api_key="kwarg-secret")

        # String kwargs are coerced to SecretStr
        assert isinstance(settings.api_key, SecretStr)
        assert settings.api_key.get_secret_value() == "kwarg-secret"

    def test_secretstr_masked_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that SecretStr values are masked in repr."""
        monkeypatch.setenv("SECRET_API_KEY", "secret-value")
        monkeypatch.setenv("SECRET_USERNAME", "test-user")

        settings = SecretSettings()
        repr_str = repr(settings)

        assert "secret-value" not in repr_str
        assert "**********" in repr_str
        assert "test-user" in repr_str


class TestBackendAwareSettings:
    """Test backend-aware settings functionality."""

    def test_explicit_backend_parameter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test explicit backend selection via parameter."""
        monkeypatch.setenv("PRIMARY_PRIMARY_KEY", "primary-value")
        monkeypatch.setenv("SECONDARY_SECONDARY_KEY", "secondary-value")

        settings = BackendAwareSettings(backend="secondary")

        assert settings.backend == "secondary"

    def test_backend_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test backend selection via environment variable."""
        monkeypatch.setenv("PROVIDER_BACKEND", "secondary")
        monkeypatch.setenv("SECONDARY_SECONDARY_KEY", "secondary-value")

        settings = BackendAwareSettings()

        assert settings.backend == "secondary"

    def test_invalid_backend_raises_error(self) -> None:
        """Test that invalid backend name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid backend 'invalid'"):
            BackendAwareSettings(backend="invalid")

    def test_invalid_backend_from_env_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid backend from env var raises ValueError."""
        monkeypatch.setenv("PROVIDER_BACKEND", "invalid")

        with pytest.raises(ValueError, match="Invalid backend 'invalid'"):
            BackendAwareSettings()

    def test_auto_detect_primary_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test auto-detection of primary backend."""
        monkeypatch.setenv("PRIMARY_PRIMARY_KEY", "primary-value")

        settings = BackendAwareSettings()

        assert settings.backend == "primary"
        assert settings.primary_key == "primary-value"

    def test_auto_detect_secondary_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test auto-detection of secondary backend."""
        monkeypatch.setenv("SECONDARY_SECONDARY_KEY", "secondary-value")

        settings = BackendAwareSettings()

        assert settings.backend == "secondary"
        assert settings.secondary_key == "secondary-value"

    def test_precedence_when_both_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that precedence is respected when multiple backends detected."""
        monkeypatch.setenv("PRIMARY_PRIMARY_KEY", "primary-value")
        monkeypatch.setenv("SECONDARY_SECONDARY_KEY", "secondary-value")

        settings = BackendAwareSettings()

        assert settings.backend == "primary"  # Lower precedence number wins

    def test_explicit_backend_overrides_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that explicit backend overrides auto-detection."""
        monkeypatch.setenv("PRIMARY_PRIMARY_KEY", "primary-value")
        monkeypatch.setenv("SECONDARY_SECONDARY_KEY", "secondary-value")

        settings = BackendAwareSettings(backend="secondary")

        assert settings.backend == "secondary"

    def test_env_var_backend_overrides_detection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that env var backend overrides auto-detection."""
        monkeypatch.setenv("PROVIDER_BACKEND", "secondary")
        monkeypatch.setenv("PRIMARY_PRIMARY_KEY", "primary-value")
        monkeypatch.setenv("SECONDARY_SECONDARY_KEY", "secondary-value")

        settings = BackendAwareSettings()

        assert settings.backend == "secondary"

    def test_no_backend_when_no_detection_fields(self) -> None:
        """Test that no backend is selected when no detection fields are satisfied."""
        settings = BackendAwareSettings()

        assert settings.backend is None


class TestFieldEnvVarMapping:
    """Test custom field to env var mappings."""

    def test_custom_field_mapping(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test custom field to env var name mapping."""

        class CustomMappingSettings(AFSettings):
            env_prefix = "CUSTOM_"
            backend_configs = {
                "test": BackendConfig(
                    env_prefix="TEST_",
                    precedence=1,
                    detection_fields={"api_key"},
                    field_env_vars={"api_key": "KEY", "model_id": "MODEL"},
                ),
            }

            api_key: str | None = None
            model_id: str | None = None

        monkeypatch.setenv("TEST_KEY", "test-key")
        monkeypatch.setenv("TEST_MODEL", "gpt-4")

        settings = CustomMappingSettings(backend="test")

        assert settings.api_key == "test-key"
        assert settings.model_id == "gpt-4"


class TestTypeCoercion:
    """Test type coercion from string values."""

    def test_int_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test integer type coercion."""
        monkeypatch.setenv("TEST_APP_TIMEOUT", "42")

        settings = SimpleSettings()

        assert settings.timeout == 42
        assert isinstance(settings.timeout, int)

    def test_float_coercion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test float type coercion."""
        monkeypatch.setenv("TEST_APP_RATE_LIMIT", "2.5")

        settings = SimpleSettings()

        assert settings.rate_limit == 2.5
        assert isinstance(settings.rate_limit, float)

    def test_bool_coercion_true_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test boolean coercion for true values."""
        for true_val in ["true", "True", "TRUE", "1", "yes", "on"]:
            monkeypatch.setenv("TEST_APP_ENABLED", true_val)
            settings = SimpleSettings()
            assert settings.enabled is True, f"Failed for {true_val}"

    def test_bool_coercion_false_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test boolean coercion for false values."""
        for false_val in ["false", "False", "FALSE", "0", "no", "off"]:
            monkeypatch.setenv("TEST_APP_ENABLED", false_val)
            settings = SimpleSettings()
            assert settings.enabled is False, f"Failed for {false_val}"
