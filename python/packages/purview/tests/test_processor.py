# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview processor."""

from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import ChatMessage, Role

from agent_framework_purview import PurviewAppLocation, PurviewLocationType, PurviewSettings
from agent_framework_purview._models import Activity, DlpAction, DlpActionInfo, ProcessContentResponse, RestrictionAction
from agent_framework_purview._processor import ScopedContentProcessor, _is_valid_guid


class TestGuidValidation:
    """Test GUID validation helper."""

    def test_valid_guid(self) -> None:
        """Test _is_valid_guid with valid GUIDs."""
        assert _is_valid_guid("12345678-1234-1234-1234-123456789012")
        assert _is_valid_guid("a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d")

    def test_invalid_guid(self) -> None:
        """Test _is_valid_guid with invalid GUIDs."""
        assert not _is_valid_guid("not-a-guid")
        assert not _is_valid_guid("")
        assert not _is_valid_guid(None)


class TestScopedContentProcessor:
    """Test ScopedContentProcessor functionality."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock Purview client."""
        client = AsyncMock()
        client.get_user_info_from_token = AsyncMock(
            return_value={"tenant_id": "12345678-1234-1234-1234-123456789012", "user_id": "12345678-1234-1234-1234-123456789012", "client_id": "12345678-1234-1234-1234-123456789012"}
        )
        return client

    @pytest.fixture
    def settings_with_defaults(self) -> PurviewSettings:
        """Create settings with default values."""
        app_location = PurviewAppLocation(location_type=PurviewLocationType.APPLICATION, location_value="12345678-1234-1234-1234-123456789012")
        return PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            default_user_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=app_location,
        )

    @pytest.fixture
    def settings_without_defaults(self) -> PurviewSettings:
        """Create settings without default values (requiring token info)."""
        return PurviewSettings(app_name="Test App")

    @pytest.fixture
    def processor(self, mock_client: AsyncMock, settings_with_defaults: PurviewSettings) -> ScopedContentProcessor:
        """Create a ScopedContentProcessor with mock client."""
        return ScopedContentProcessor(mock_client, settings_with_defaults)

    async def test_processor_initialization(
        self, mock_client: AsyncMock, settings_with_defaults: PurviewSettings
    ) -> None:
        """Test ScopedContentProcessor initialization."""
        processor = ScopedContentProcessor(mock_client, settings_with_defaults)

        assert processor._client == mock_client
        assert processor._settings == settings_with_defaults

    async def test_process_messages_with_defaults(self, processor: ScopedContentProcessor) -> None:
        """Test process_messages with settings that have defaults."""
        messages = [
            ChatMessage(role=Role.USER, text="Hello"),
            ChatMessage(role=Role.ASSISTANT, text="Hi there"),
        ]

        with patch.object(processor, "_map_messages", return_value=[]) as mock_map:
            result = await processor.process_messages(messages, Activity.UPLOAD_TEXT)

            assert result is False
            mock_map.assert_called_once_with(messages, Activity.UPLOAD_TEXT)

    async def test_process_messages_blocks_content(self, processor: ScopedContentProcessor, process_content_request_factory) -> None:
        """Test process_messages returns True when content should be blocked."""
        messages = [ChatMessage(role=Role.USER, text="Sensitive content")]

        mock_request = process_content_request_factory("Sensitive content")

        mock_response = ProcessContentResponse(**{
            "policyActions": [DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)]
        })

        with (
            patch.object(processor, "_map_messages", return_value=[mock_request]),
            patch.object(processor, "_process_with_scopes", return_value=mock_response),
        ):
            result = await processor.process_messages(messages, Activity.UPLOAD_TEXT)

            assert result is True

    async def test_map_messages_creates_requests(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock
    ) -> None:
        """Test _map_messages creates ProcessContentRequest objects."""
        messages = [
            ChatMessage(role=Role.USER, text="Test message", message_id="msg-123"),
        ]

        requests = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 1
        assert requests[0].user_id == "12345678-1234-1234-1234-123456789012"
        assert requests[0].tenant_id == "12345678-1234-1234-1234-123456789012"

    async def test_map_messages_without_defaults_gets_token_info(
        self, mock_client: AsyncMock
    ) -> None:
        """Test _map_messages gets token info when settings lack some defaults."""
        settings = PurviewSettings(app_name="Test App", tenant_id="12345678-1234-1234-1234-123456789012")
        processor = ScopedContentProcessor(mock_client, settings)
        messages = [ChatMessage(role=Role.USER, text="Test", message_id="msg-123")]

        requests = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        mock_client.get_user_info_from_token.assert_called_once()
        assert len(requests) == 1

    async def test_map_messages_raises_on_missing_tenant_id(self, mock_client: AsyncMock) -> None:
        """Test _map_messages raises ValueError when tenant_id cannot be determined."""
        settings = PurviewSettings(app_name="Test App")  # No tenant_id
        processor = ScopedContentProcessor(mock_client, settings)

        mock_client.get_user_info_from_token = AsyncMock(
            return_value={"user_id": "test-user", "client_id": "test-client"}
        )

        messages = [ChatMessage(role=Role.USER, text="Test", message_id="msg-123")]

        with pytest.raises(ValueError, match="Tenant id required"):
            await processor._map_messages(messages, Activity.UPLOAD_TEXT)

    async def test_check_applicable_scopes_no_scopes(self, processor: ScopedContentProcessor, process_content_request_factory) -> None:
        """Test _check_applicable_scopes when no scopes are returned."""
        from agent_framework_purview._models import ProtectionScopesResponse

        request = process_content_request_factory()
        response = ProtectionScopesResponse(**{"value": None})

        should_process, actions = processor._check_applicable_scopes(request, response)

        assert should_process is False
        assert actions == []

    async def test_check_applicable_scopes_with_block_action(self, processor: ScopedContentProcessor, process_content_request_factory) -> None:
        """Test _check_applicable_scopes identifies block actions."""
        from agent_framework_purview._models import (
            PolicyLocation,
            PolicyScope,
            ProtectionScopeActivities,
            ProtectionScopesResponse,
        )

        request = process_content_request_factory()

        block_action = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)
        scope_location = PolicyLocation(**{
            "@odata.type": "microsoft.graph.policyLocationApplication",
            "value": "app-id",
        })
        scope = PolicyScope(**{
            "policyActions": [block_action],
            "activities": ProtectionScopeActivities.UPLOAD_TEXT,
            "locations": [scope_location],
        })
        response = ProtectionScopesResponse(**{"value": [scope]})

        should_process, actions = processor._check_applicable_scopes(request, response)

        assert should_process is True
        assert len(actions) == 1
        assert actions[0].action == DlpAction.BLOCK_ACCESS

    async def test_combine_policy_actions(self, processor: ScopedContentProcessor) -> None:
        """Test _combine_policy_actions merges action lists."""
        action1 = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)
        action2 = DlpActionInfo(action=DlpAction.OTHER, restrictionAction=RestrictionAction.OTHER)

        combined = processor._combine_policy_actions([action1], [action2])

        assert len(combined) == 2
        assert action1 in combined
        assert action2 in combined

    async def test_process_with_scopes_calls_client_methods(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test _process_with_scopes calls get_protection_scopes and process_content."""
        from agent_framework_purview._models import (
            ContentActivitiesResponse,
            ProtectionScopesResponse,
        )

        request = process_content_request_factory()

        mock_client.get_protection_scopes = AsyncMock(return_value=ProtectionScopesResponse(**{"value": []}))
        mock_client.process_content = AsyncMock(
            return_value=ProcessContentResponse(**{"id": "response-123", "protectionScopeState": "notModified"})
        )
        mock_client.send_content_activities = AsyncMock(return_value=ContentActivitiesResponse(**{"error": None}))

        response = await processor._process_with_scopes(request)

        mock_client.get_protection_scopes.assert_called_once()
        mock_client.process_content.assert_not_called()
        mock_client.send_content_activities.assert_called_once()
        assert response.id is None
