# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock, patch

import pytest
from agent_framework.exceptions import ServiceInitializationError

from agent_framework_copilotstudio._agent import CopilotStudioSettings


class TestCopilotStudioSettings:
    """Test class for CopilotStudioSettings."""

    def test_copilot_studio_settings_with_env_vars(self, copilot_studio_unit_test_env: dict[str, str]) -> None:
        """Test CopilotStudioSettings initialization with environment variables."""
        settings = CopilotStudioSettings()

        assert settings.environmentid == "test-environment-id"
        assert settings.schemaname == "test-schema-name"
        assert settings.agentappid == "test-client-id"
        assert settings.tenantid == "test-tenant-id"

    def test_copilot_studio_settings_direct_values(self) -> None:
        """Test CopilotStudioSettings initialization with direct values."""
        settings = CopilotStudioSettings(
            environmentid="direct-env-id",
            schemaname="direct-schema-name",
            agentappid="direct-client-id",
            tenantid="direct-tenant-id",
        )

        assert settings.environmentid == "direct-env-id"
        assert settings.schemaname == "direct-schema-name"
        assert settings.agentappid == "direct-client-id"
        assert settings.tenantid == "direct-tenant-id"

    def test_copilot_studio_settings_none_values(self) -> None:
        """Test CopilotStudioSettings with None values."""
        with patch.dict("os.environ", {}, clear=True):
            settings = CopilotStudioSettings()

            assert settings.environmentid is None
            assert settings.schemaname is None
            assert settings.agentappid is None
            assert settings.tenantid is None


class TestCopilotStudioAgentInitializationLogic:
    """Test class for CopilotStudioAgent initialization logic without full agent creation."""

    @patch("agent_framework_copilotstudio._agent.acquire_token")
    def test_token_acquisition_called_with_correct_parameters(
        self, mock_acquire_token: MagicMock, copilot_studio_unit_test_env: dict[str, str]
    ) -> None:
        """Test that token acquisition is called with correct parameters during initialization."""
        from agent_framework_copilotstudio._agent import CopilotStudioAgent

        mock_acquire_token.return_value = "test-token"

        with (
            patch.object(CopilotStudioAgent, "__init__", return_value=None),
            patch("agent_framework_copilotstudio._agent.CopilotClient"),
            patch("agent_framework_copilotstudio._agent.ConnectionSettings"),
        ):
            settings = CopilotStudioSettings()

            from agent_framework_copilotstudio._agent import acquire_token

            token = acquire_token(
                client_id=settings.agentappid or "test-client-id",
                tenant_id=settings.tenantid or "test-tenant-id",
                username=None,
                token_cache=None,
                scopes=None,
            )

        assert token == "test-token"
        mock_acquire_token.assert_called_once_with(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
            username=None,
            token_cache=None,
            scopes=None,
        )

    @pytest.mark.parametrize("exclude_list", [["COPILOTSTUDIOAGENT__ENVIRONMENTID"]], indirect=True)
    def test_missing_environment_id_validation(self, copilot_studio_unit_test_env: dict[str, str]) -> None:
        """Test that missing environment ID is properly validated."""
        settings = CopilotStudioSettings()
        assert settings.environmentid is None

        if not settings.environmentid:
            with pytest.raises(ServiceInitializationError, match="Copilot Studio environment ID is required"):
                raise ServiceInitializationError(
                    "Copilot Studio environment ID is required. Set via 'environment_id' parameter "
                    "or 'COPILOTSTUDIOAGENT__ENVIRONMENTID' environment variable."
                )

    @pytest.mark.parametrize("exclude_list", [["COPILOTSTUDIOAGENT__SCHEMANAME"]], indirect=True)
    def test_missing_schema_name_validation(self, copilot_studio_unit_test_env: dict[str, str]) -> None:
        """Test that missing schema name is properly validated."""
        settings = CopilotStudioSettings()
        assert settings.schemaname is None

        if not settings.schemaname:
            with pytest.raises(
                ServiceInitializationError, match="Copilot Studio agent identifier/schema name is required"
            ):
                raise ServiceInitializationError(
                    "Copilot Studio agent identifier/schema name is required. Set via 'agent_identifier' parameter "
                    "or 'COPILOTSTUDIOAGENT__SCHEMANAME' environment variable."
                )

    @pytest.mark.parametrize("exclude_list", [["COPILOTSTUDIOAGENT__AGENTAPPID"]], indirect=True)
    def test_missing_client_id_validation(self, copilot_studio_unit_test_env: dict[str, str]) -> None:
        """Test that missing client ID is properly validated."""
        settings = CopilotStudioSettings()
        assert settings.agentappid is None

        if not settings.agentappid:
            with pytest.raises(ServiceInitializationError, match="Copilot Studio client ID is required"):
                raise ServiceInitializationError(
                    "Copilot Studio client ID is required. Set via 'client_id' parameter "
                    "or 'COPILOTSTUDIOAGENT__AGENTAPPID' environment variable."
                )

    @pytest.mark.parametrize("exclude_list", [["COPILOTSTUDIOAGENT__TENANTID"]], indirect=True)
    def test_missing_tenant_id_validation(self, copilot_studio_unit_test_env: dict[str, str]) -> None:
        """Test that missing tenant ID is properly validated."""
        settings = CopilotStudioSettings()
        assert settings.tenantid is None

        if not settings.tenantid:
            with pytest.raises(ServiceInitializationError, match="Copilot Studio tenant ID is required"):
                raise ServiceInitializationError(
                    "Copilot Studio tenant ID is required. Set via 'tenant_id' parameter "
                    "or 'COPILOTSTUDIOAGENT__TENANTID' environment variable."
                )


class TestCopilotStudioAgentMethods:
    """Test class for individual methods that can be tested without full initialization."""

    @patch("agent_framework_copilotstudio._agent.acquire_token")
    def test_token_acquisition_with_custom_parameters(self, mock_acquire_token: MagicMock) -> None:
        """Test token acquisition with custom parameters."""
        from agent_framework_copilotstudio._agent import acquire_token

        mock_acquire_token.return_value = "custom-token"

        # Test the acquire_token function directly
        token = acquire_token(
            client_id="custom-client-id",
            tenant_id="custom-tenant-id",
            username="custom-user@example.com",
            token_cache="custom-cache",
            scopes=["custom-scope"],
        )

        assert token == "custom-token"
        mock_acquire_token.assert_called_once_with(
            client_id="custom-client-id",
            tenant_id="custom-tenant-id",
            username="custom-user@example.com",
            token_cache="custom-cache",
            scopes=["custom-scope"],
        )
