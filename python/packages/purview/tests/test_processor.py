# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview processor."""

from unittest.mock import AsyncMock, patch

import pytest
from agent_framework import ChatMessage, Role

from agent_framework_purview import PurviewAppLocation, PurviewLocationType, PurviewSettings
from agent_framework_purview._models import Activity, DlpAction, DlpActionInfo, RestrictionAction
from agent_framework_purview._processor import ScopedContentProcessor, _is_valid_guid


class TestGuidValidation:
    """Test GUID validation helper."""

    def test_valid_guid(self) -> None:
        """Test _is_valid_guid with valid GUIDs."""
        assert _is_valid_guid("12345678-1234-1234-1234-123456789012")
        assert _is_valid_guid("a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d")
        assert _is_valid_guid("00000000-0000-0000-0000-000000000000")

    def test_invalid_guid(self) -> None:
        """Test _is_valid_guid with invalid GUIDs."""
        assert not _is_valid_guid("not-a-guid")
        assert not _is_valid_guid("12345678")
        assert not _is_valid_guid("")
        assert not _is_valid_guid(None)
        assert not _is_valid_guid("12345678-1234-1234-1234")  # Too short

    def test_guid_without_hyphens(self) -> None:
        """Test _is_valid_guid with GUID without hyphens."""
        # uuid.UUID can parse GUIDs without hyphens
        assert _is_valid_guid("12345678123412341234123456789012")


class TestScopedContentProcessor:
    """Test ScopedContentProcessor functionality."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock Purview client."""
        client = AsyncMock()
        client.get_user_info_from_token = AsyncMock(
            return_value={"tenant_id": "test-tenant", "user_id": "test-user", "client_id": "test-client"}
        )
        return client

    @pytest.fixture
    def settings_with_defaults(self) -> PurviewSettings:
        """Create settings with default values."""
        app_location = PurviewAppLocation(location_type=PurviewLocationType.APPLICATION, location_value="test-app-id")
        return PurviewSettings(
            app_name="Test App",
            tenant_id="test-tenant",
            default_user_id="test-user",
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

        # Mock the processor methods
        with patch.object(processor, "_map_messages", return_value=[]) as mock_map:
            result = await processor.process_messages(messages, Activity.UPLOAD_TEXT)

            assert result is False
            mock_map.assert_called_once_with(messages, Activity.UPLOAD_TEXT)

    async def test_process_messages_blocks_content(self, processor: ScopedContentProcessor) -> None:
        """Test process_messages returns True when content should be blocked."""
        messages = [ChatMessage(role=Role.USER, text="Sensitive content")]

        # Create a mock request that will trigger blocking
        from agent_framework_purview._models import (
            ActivityMetadata,
            ContentToProcess,
            DeviceMetadata,
            IntegratedAppMetadata,
            OperatingSystemSpecifications,
            PolicyLocation,
            ProcessContentRequest,
            ProcessContentResponse,
            ProcessConversationMetadata,
            ProtectedAppMetadata,
            PurviewTextContent,
        )

        text_content = PurviewTextContent(data="Sensitive content")
        metadata = ProcessConversationMetadata(**{
            "@odata.type": "microsoft.graph.processConversationMetadata",
            "identifier": "msg-1",
            "content": text_content,
            "name": "Test",
            "isTruncated": False,
        })
        activity_meta = ActivityMetadata(activity=Activity.UPLOAD_TEXT)
        device_meta = DeviceMetadata(
            operatingSystemSpecifications=OperatingSystemSpecifications(
                operatingSystemPlatform="Windows", operatingSystemVersion="10"
            )
        )
        integrated_app = IntegratedAppMetadata(name="App", version="1.0")
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        protected_app = ProtectedAppMetadata(name="Protected", version="1.0", applicationLocation=location)
        content = ContentToProcess(**{
            "contentEntries": [metadata],
            "activityMetadata": activity_meta,
            "deviceMetadata": device_meta,
            "integratedAppMetadata": integrated_app,
            "protectedAppMetadata": protected_app,
        })
        mock_request = ProcessContentRequest(**{
            "contentToProcess": content,
            "user_id": "user-123",
            "tenant_id": "tenant-456",
        })

        # Mock response with block action
        mock_response = ProcessContentResponse(**{
            "policyActions": [DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)]
        })

        with (
            patch.object(processor, "_map_messages", return_value=[mock_request]),
            patch.object(processor, "_process_with_scopes", return_value=mock_response),
        ):
            result = await processor.process_messages(messages, Activity.UPLOAD_TEXT)

            assert result is True  # Should block

    async def test_map_messages_creates_requests(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock
    ) -> None:
        """Test _map_messages creates ProcessContentRequest objects."""
        messages = [
            ChatMessage(role=Role.USER, text="Test message", message_id="msg-123"),
        ]

        requests = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 1
        assert requests[0].user_id == "test-user"
        assert requests[0].tenant_id == "test-tenant"

    async def test_map_messages_without_defaults_gets_token_info(
        self, mock_client: AsyncMock, settings_without_defaults: PurviewSettings
    ) -> None:
        """Test _map_messages gets token info when settings lack defaults."""
        processor = ScopedContentProcessor(mock_client, settings_without_defaults)
        messages = [ChatMessage(role=Role.USER, text="Test", message_id="msg-123")]

        requests = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        # Should have called get_user_info_from_token
        mock_client.get_user_info_from_token.assert_called_once()
        assert len(requests) == 1

    async def test_map_messages_uses_message_author_as_user_id(self, processor: ScopedContentProcessor) -> None:
        """Test _map_messages uses message author_name as user_id if it's a valid GUID."""
        valid_guid = "12345678-1234-1234-1234-123456789012"
        messages = [
            ChatMessage(role=Role.USER, text="Test", message_id="msg-123", author_name=valid_guid),
        ]

        requests = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 1
        assert requests[0].user_id == valid_guid

    async def test_map_messages_ignores_invalid_author_guid(self, processor: ScopedContentProcessor) -> None:
        """Test _map_messages ignores author_name if not a valid GUID."""
        messages = [
            ChatMessage(role=Role.USER, text="Test", message_id="msg-123", author_name="Not A GUID"),
        ]

        requests = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 1
        # Should use default_user_id from settings
        assert requests[0].user_id == "test-user"

    async def test_map_messages_raises_on_missing_user_id(self, mock_client: AsyncMock) -> None:
        """Test _map_messages raises ValueError when user_id cannot be determined."""
        settings = PurviewSettings(app_name="Test App", tenant_id="test-tenant")
        processor = ScopedContentProcessor(mock_client, settings)

        # Mock token info without user_id
        mock_client.get_user_info_from_token = AsyncMock(
            return_value={"tenant_id": "test-tenant", "client_id": "test-client"}
        )

        messages = [ChatMessage(role=Role.USER, text="Test", message_id="msg-123")]

        with pytest.raises(ValueError, match="User id required"):
            await processor._map_messages(messages, Activity.UPLOAD_TEXT)

    async def test_check_applicable_scopes_no_scopes(self, processor: ScopedContentProcessor) -> None:
        """Test _check_applicable_scopes when no scopes are returned."""
        from agent_framework_purview._models import (
            ActivityMetadata,
            ContentToProcess,
            DeviceMetadata,
            IntegratedAppMetadata,
            OperatingSystemSpecifications,
            PolicyLocation,
            ProcessContentRequest,
            ProcessConversationMetadata,
            ProtectedAppMetadata,
            ProtectionScopesResponse,
            PurviewTextContent,
        )

        text_content = PurviewTextContent(data="Test")
        metadata = ProcessConversationMetadata(**{
            "@odata.type": "microsoft.graph.processConversationMetadata",
            "identifier": "msg-1",
            "content": text_content,
            "name": "Test",
            "isTruncated": False,
        })
        activity_meta = ActivityMetadata(activity=Activity.UPLOAD_TEXT)
        device_meta = DeviceMetadata(
            operatingSystemSpecifications=OperatingSystemSpecifications(
                operatingSystemPlatform="Windows", operatingSystemVersion="10"
            )
        )
        integrated_app = IntegratedAppMetadata(name="App", version="1.0")
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        protected_app = ProtectedAppMetadata(name="Protected", version="1.0", applicationLocation=location)
        content = ContentToProcess(**{
            "contentEntries": [metadata],
            "activityMetadata": activity_meta,
            "deviceMetadata": device_meta,
            "integratedAppMetadata": integrated_app,
            "protectedAppMetadata": protected_app,
        })
        request = ProcessContentRequest(**{
            "contentToProcess": content,
            "user_id": "user-123",
            "tenant_id": "tenant-456",
        })

        response = ProtectionScopesResponse(**{"value": None})

        should_process, actions = processor._check_applicable_scopes(request, response)

        assert should_process is False  # No scopes means no matching policy
        assert actions == []

    async def test_check_applicable_scopes_with_block_action(self, processor: ScopedContentProcessor) -> None:
        """Test _check_applicable_scopes identifies block actions."""
        from agent_framework_purview._models import (
            ActivityMetadata,
            ContentToProcess,
            DeviceMetadata,
            IntegratedAppMetadata,
            OperatingSystemSpecifications,
            PolicyLocation,
            PolicyScope,
            ProcessContentRequest,
            ProcessConversationMetadata,
            ProtectedAppMetadata,
            ProtectionScopeActivities,
            ProtectionScopesResponse,
            PurviewTextContent,
        )

        text_content = PurviewTextContent(data="Test")
        metadata = ProcessConversationMetadata(**{
            "@odata.type": "microsoft.graph.processConversationMetadata",
            "identifier": "msg-1",
            "content": text_content,
            "name": "Test",
            "isTruncated": False,
        })
        activity_meta = ActivityMetadata(activity=Activity.UPLOAD_TEXT)
        device_meta = DeviceMetadata(
            operatingSystemSpecifications=OperatingSystemSpecifications(
                operatingSystemPlatform="Windows", operatingSystemVersion="10"
            )
        )
        integrated_app = IntegratedAppMetadata(name="App", version="1.0")
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        protected_app = ProtectedAppMetadata(name="Protected", version="1.0", applicationLocation=location)
        content = ContentToProcess(**{
            "contentEntries": [metadata],
            "activityMetadata": activity_meta,
            "deviceMetadata": device_meta,
            "integratedAppMetadata": integrated_app,
            "protectedAppMetadata": protected_app,
        })
        request = ProcessContentRequest(**{
            "contentToProcess": content,
            "user_id": "user-123",
            "tenant_id": "tenant-456",
        })

        # Create response with block action
        # Scope needs both activities and matching location to be applicable
        block_action = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)
        # Create location that matches the request
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

        assert should_process is True  # Matching scope found
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

    async def test_combine_policy_actions_with_none(self, processor: ScopedContentProcessor) -> None:
        """Test _combine_policy_actions handles None values."""
        action = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)

        # None + list = list
        result1 = processor._combine_policy_actions(None, [action])
        assert result1 == [action]

        # list + empty list = list (None is treated as empty list by implementation)
        result2 = processor._combine_policy_actions([action], [])
        assert result2 == [action]

        # None + empty list = empty list
        result3 = processor._combine_policy_actions(None, [])
        assert result3 == []

    async def test_process_with_scopes_calls_client_methods(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock
    ) -> None:
        """Test _process_with_scopes calls get_protection_scopes and process_content."""
        from agent_framework_purview._models import (
            ActivityMetadata,
            ContentToProcess,
            DeviceMetadata,
            IntegratedAppMetadata,
            OperatingSystemSpecifications,
            PolicyLocation,
            ProcessContentRequest,
            ProcessContentResponse,
            ProcessConversationMetadata,
            ProtectedAppMetadata,
            ProtectionScopesResponse,
            PurviewTextContent,
        )

        text_content = PurviewTextContent(data="Test")
        metadata = ProcessConversationMetadata(**{
            "@odata.type": "microsoft.graph.processConversationMetadata",
            "identifier": "msg-1",
            "content": text_content,
            "name": "Test",
            "isTruncated": False,
        })
        activity_meta = ActivityMetadata(activity=Activity.UPLOAD_TEXT)
        device_meta = DeviceMetadata(
            operatingSystemSpecifications=OperatingSystemSpecifications(
                operatingSystemPlatform="Windows", operatingSystemVersion="10"
            )
        )
        integrated_app = IntegratedAppMetadata(name="App", version="1.0")
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        protected_app = ProtectedAppMetadata(name="Protected", version="1.0", applicationLocation=location)
        content = ContentToProcess(**{
            "contentEntries": [metadata],
            "activityMetadata": activity_meta,
            "deviceMetadata": device_meta,
            "integratedAppMetadata": integrated_app,
            "protectedAppMetadata": protected_app,
        })
        request = ProcessContentRequest(**{
            "contentToProcess": content,
            "user_id": "user-123",
            "tenant_id": "tenant-456",
        })

        # Mock responses
        mock_client.get_protection_scopes = AsyncMock(return_value=ProtectionScopesResponse(**{"value": []}))
        mock_client.process_content = AsyncMock(
            return_value=ProcessContentResponse(**{"id": "response-123", "protectionScopeState": "notModified"})
        )
        # Mock send_content_activities for the fallback path
        from agent_framework_purview._models import ContentActivitiesResponse

        mock_client.send_content_activities = AsyncMock(return_value=ContentActivitiesResponse(**{"error": None}))

        response = await processor._process_with_scopes(request)

        # Verify get_protection_scopes was called
        mock_client.get_protection_scopes.assert_called_once()
        # process_content should NOT be called when no scopes match
        mock_client.process_content.assert_not_called()
        # send_content_activities should be called as fallback
        mock_client.send_content_activities.assert_called_once()
        # Response should be default empty response (not from process_content)
        assert response.id is None  # Empty response has no ID
