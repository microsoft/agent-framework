# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview settings."""

import pytest

from agent_framework_purview import PurviewAppLocation, PurviewLocationType, PurviewSettings


class TestPurviewSettings:
    """Test PurviewSettings configuration."""

    def test_settings_defaults(self) -> None:
        """Test PurviewSettings with default values."""
        settings = PurviewSettings(app_name="Test App")

        assert settings.app_name == "Test App"
        assert settings.graph_base_uri == "https://graph.microsoft.com/v1.0/"
        assert settings.tenant_id is None
        assert settings.purview_app_location is None

    def test_settings_with_custom_values(self) -> None:
        """Test PurviewSettings with custom values."""
        app_location = PurviewAppLocation(location_type=PurviewLocationType.APPLICATION, location_value="app-123")

        settings = PurviewSettings(
            app_name="Test App",
            graph_base_uri="https://graph.microsoft-ppe.com",
            tenant_id="test-tenant-id",
            purview_app_location=app_location,
        )

        assert settings.graph_base_uri == "https://graph.microsoft-ppe.com"
        assert settings.tenant_id == "test-tenant-id"
        assert settings.purview_app_location.location_value == "app-123"

    @pytest.mark.parametrize(
        "graph_uri,expected_scope",
        [
            ("https://graph.microsoft.com/v1.0/", "https://graph.microsoft.com/.default"),
            ("https://graph.microsoft-ppe.com/v1.0/", "https://graph.microsoft-ppe.com/.default"),
        ],
    )
    def test_get_scopes(self, graph_uri: str, expected_scope: str) -> None:
        """Test get_scopes returns correct scope for different URIs."""
        settings = PurviewSettings(app_name="Test App", graph_base_uri=graph_uri)
        scopes = settings.get_scopes()

        assert len(scopes) == 1
        assert expected_scope in scopes


class TestPurviewAppLocation:
    """Test PurviewAppLocation configuration."""

    @pytest.mark.parametrize(
        "location_type,location_value,expected_odata_type",
        [
            (PurviewLocationType.APPLICATION, "app-123", "microsoft.graph.policyLocationApplication"),
            (PurviewLocationType.URI, "https://example.com", "microsoft.graph.policyLocationUrl"),
            (PurviewLocationType.DOMAIN, "example.com", "microsoft.graph.policyLocationDomain"),
        ],
    )
    def test_get_policy_location(
        self, location_type: PurviewLocationType, location_value: str, expected_odata_type: str
    ) -> None:
        """Test get_policy_location returns correct structure for all location types."""
        location = PurviewAppLocation(location_type=location_type, location_value=location_value)
        policy_location = location.get_policy_location()

        assert policy_location["@odata.type"] == expected_odata_type
        assert policy_location["value"] == location_value


class TestPurviewLocationType:
    """Test PurviewLocationType enum."""

    def test_location_type_values(self) -> None:
        """Test PurviewLocationType enum has expected values."""
        assert PurviewLocationType.APPLICATION == "application"
        assert PurviewLocationType.URI == "uri"
        assert PurviewLocationType.DOMAIN == "domain"
