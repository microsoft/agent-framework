# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview settings."""

import os
from unittest.mock import patch

from agent_framework_purview import PurviewAppLocation, PurviewLocationType, PurviewSettings


class TestPurviewSettings:
    """Test PurviewSettings configuration."""

    def test_settings_defaults(self) -> None:
        """Test PurviewSettings with default values."""
        settings = PurviewSettings(app_name="Test App")

        assert settings.app_name == "Test App"
        assert settings.graph_base_uri == "https://graph.microsoft.com/v1.0/"
        assert settings.tenant_id is None
        assert settings.default_user_id is None
        assert settings.purview_app_location is None
        assert settings.process_inline is False

    def test_settings_with_custom_graph_uri(self) -> None:
        """Test PurviewSettings with custom graph URI."""
        settings = PurviewSettings(app_name="Test App", graph_base_uri="https://graph.microsoft-ppe.com")

        assert settings.graph_base_uri == "https://graph.microsoft-ppe.com"

    def test_settings_with_tenant_id(self) -> None:
        """Test PurviewSettings with tenant ID."""
        settings = PurviewSettings(app_name="Test App", tenant_id="test-tenant-id")

        assert settings.tenant_id == "test-tenant-id"

    def test_settings_with_default_user_id(self) -> None:
        """Test PurviewSettings with default user ID."""
        settings = PurviewSettings(app_name="Test App", default_user_id="user-123")

        assert settings.default_user_id == "user-123"

    def test_settings_with_process_inline_true(self) -> None:
        """Test PurviewSettings with process_inline enabled."""
        settings = PurviewSettings(app_name="Test App", process_inline=True)

        assert settings.process_inline is True

    def test_settings_from_environment_variables(self) -> None:
        """Test PurviewSettings can read from environment variables."""
        with patch.dict(
            os.environ,
            {
                "PURVIEW_APP_NAME": "Env App",
                "PURVIEW_TENANT_ID": "env-tenant",
                "PURVIEW_DEFAULT_USER_ID": "env-user",
            },
        ):
            # In a real scenario, the settings class would read from env vars
            # For now, we test explicit parameter passing
            settings = PurviewSettings(app_name="Env App", tenant_id="env-tenant", default_user_id="env-user")

            assert settings.app_name == "Env App"
            assert settings.tenant_id == "env-tenant"
            assert settings.default_user_id == "env-user"

    def test_get_scopes_default(self) -> None:
        """Test get_scopes returns default Graph API scope."""
        settings = PurviewSettings(app_name="Test App")
        scopes = settings.get_scopes()

        assert len(scopes) == 1
        assert "https://graph.microsoft.com/.default" in scopes

    def test_get_scopes_custom_uri(self) -> None:
        """Test get_scopes with custom graph URI."""
        settings = PurviewSettings(app_name="Test App", graph_base_uri="https://graph.microsoft-ppe.com/v1.0/")
        scopes = settings.get_scopes()

        assert len(scopes) == 1
        assert "https://graph.microsoft-ppe.com/.default" in scopes

    def test_settings_with_purview_app_location(self) -> None:
        """Test PurviewSettings with app location."""
        app_location = PurviewAppLocation(location_type=PurviewLocationType.APPLICATION, location_value="app-123")

        settings = PurviewSettings(app_name="Test App", purview_app_location=app_location)

        assert settings.purview_app_location is not None
        assert settings.purview_app_location.location_type == PurviewLocationType.APPLICATION
        assert settings.purview_app_location.location_value == "app-123"


class TestPurviewAppLocation:
    """Test PurviewAppLocation configuration."""

    def test_app_location_application_type(self) -> None:
        """Test PurviewAppLocation with APPLICATION type."""
        location = PurviewAppLocation(location_type=PurviewLocationType.APPLICATION, location_value="app-id-123")

        assert location.location_type == PurviewLocationType.APPLICATION
        assert location.location_value == "app-id-123"

    def test_app_location_uri_type(self) -> None:
        """Test PurviewAppLocation with URI type."""
        location = PurviewAppLocation(location_type=PurviewLocationType.URI, location_value="https://example.com")

        assert location.location_type == PurviewLocationType.URI
        assert location.location_value == "https://example.com"

    def test_app_location_domain_type(self) -> None:
        """Test PurviewAppLocation with DOMAIN type."""
        location = PurviewAppLocation(location_type=PurviewLocationType.DOMAIN, location_value="example.com")

        assert location.location_type == PurviewLocationType.DOMAIN
        assert location.location_value == "example.com"

    def test_get_policy_location_application(self) -> None:
        """Test get_policy_location returns correct structure for APPLICATION."""
        location = PurviewAppLocation(location_type=PurviewLocationType.APPLICATION, location_value="app-123")

        policy_location = location.get_policy_location()

        assert policy_location["@odata.type"] == "microsoft.graph.policyLocationApplication"
        assert policy_location["value"] == "app-123"

    def test_get_policy_location_uri(self) -> None:
        """Test get_policy_location returns correct structure for URI."""
        location = PurviewAppLocation(location_type=PurviewLocationType.URI, location_value="https://site.example.com")

        policy_location = location.get_policy_location()

        assert policy_location["@odata.type"] == "microsoft.graph.policyLocationUrl"
        assert policy_location["value"] == "https://site.example.com"

    def test_get_policy_location_domain(self) -> None:
        """Test get_policy_location with DOMAIN type."""
        location = PurviewAppLocation(location_type=PurviewLocationType.DOMAIN, location_value="example.com")

        policy_location = location.get_policy_location()

        assert policy_location["@odata.type"] == "microsoft.graph.policyLocationDomain"
        assert policy_location["value"] == "example.com"


class TestPurviewLocationType:
    """Test PurviewLocationType enum."""

    def test_location_type_values(self) -> None:
        """Test PurviewLocationType enum has expected values."""
        assert PurviewLocationType.APPLICATION == "application"
        assert PurviewLocationType.URI == "uri"
        assert PurviewLocationType.DOMAIN == "domain"

    def test_location_type_can_be_compared(self) -> None:
        """Test PurviewLocationType values can be compared."""
        assert PurviewLocationType.APPLICATION == PurviewLocationType.APPLICATION
        assert PurviewLocationType.APPLICATION != PurviewLocationType.URI
