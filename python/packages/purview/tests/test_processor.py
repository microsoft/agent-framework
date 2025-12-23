# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview processor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import ChatMessage, Role

from agent_framework_purview import PurviewAppLocation, PurviewLocationType, PurviewSettings
from agent_framework_purview._models import (
    Activity,
    DlpAction,
    DlpActionInfo,
    ProcessContentResponse,
    RestrictionAction,
)
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
            return_value={
                "tenant_id": "12345678-1234-1234-1234-123456789012",
                "user_id": "12345678-1234-1234-1234-123456789012",
                "client_id": "12345678-1234-1234-1234-123456789012",
            }
        )
        return client

    @pytest.fixture
    def settings_with_defaults(self) -> PurviewSettings:
        """Create settings with default values."""
        app_location = PurviewAppLocation(
            location_type=PurviewLocationType.APPLICATION, location_value="12345678-1234-1234-1234-123456789012"
        )
        return PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
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

        with patch.object(processor, "_map_messages", return_value=([], None)) as mock_map:
            should_block, user_id = await processor.process_messages(messages, Activity.UPLOAD_TEXT)

            assert should_block is False
            assert user_id is None
            mock_map.assert_called_once_with(messages, Activity.UPLOAD_TEXT, None)

    async def test_process_messages_blocks_content(
        self, processor: ScopedContentProcessor, process_content_request_factory
    ) -> None:
        """Test process_messages returns True when content should be blocked."""
        messages = [ChatMessage(role=Role.USER, text="Sensitive content")]

        mock_request = process_content_request_factory("Sensitive content")

        mock_response = ProcessContentResponse(**{
            "policyActions": [DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)]
        })

        with (
            patch.object(processor, "_map_messages", return_value=([mock_request], "user-123")),
            patch.object(processor, "_process_with_scopes", return_value=mock_response),
        ):
            should_block, user_id = await processor.process_messages(messages, Activity.UPLOAD_TEXT)

            assert should_block is True
            assert user_id == "user-123"

    async def test_map_messages_creates_requests(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock
    ) -> None:
        """Test _map_messages creates ProcessContentRequest objects."""
        messages = [
            ChatMessage(
                role=Role.USER,
                text="Test message",
                message_id="msg-123",
                author_name="12345678-1234-1234-1234-123456789012",
            ),
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 1
        assert requests[0].user_id == "12345678-1234-1234-1234-123456789012"
        assert requests[0].tenant_id == "12345678-1234-1234-1234-123456789012"
        assert user_id == "12345678-1234-1234-1234-123456789012"

    async def test_map_messages_without_defaults_gets_token_info(self, mock_client: AsyncMock) -> None:
        """Test _map_messages gets token info when settings lack some defaults."""
        settings = PurviewSettings(app_name="Test App", tenant_id="12345678-1234-1234-1234-123456789012")
        processor = ScopedContentProcessor(mock_client, settings)
        messages = [ChatMessage(role=Role.USER, text="Test", message_id="msg-123")]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        mock_client.get_user_info_from_token.assert_called_once()
        assert len(requests) == 1
        assert user_id is not None

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

    async def test_check_applicable_scopes_no_scopes(
        self, processor: ScopedContentProcessor, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes when no scopes are returned."""
        from agent_framework_purview._models import ProtectionScopesResponse

        request = process_content_request_factory()
        response = ProtectionScopesResponse(**{"value": None})

        should_process, actions, execution_mode = processor._check_applicable_scopes(request, response)

        assert should_process is False
        assert actions == []

    async def test_check_applicable_scopes_with_block_action(
        self, processor: ScopedContentProcessor, process_content_request_factory
    ) -> None:
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

        should_process, actions, execution_mode = processor._check_applicable_scopes(request, response)

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
        """Test _process_with_scopes calls get_protection_scopes when scopes response is empty."""
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
        # When no scopes apply, process_content is not called (activities are sent in background)
        mock_client.process_content.assert_not_called()
        # The response should have id=204 (No Content) when no scopes apply
        assert response.id == "204"

    async def test_map_messages_with_user_id_in_additional_properties(self, mock_client: AsyncMock) -> None:
        """Test user_id extraction from message additional_properties."""
        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [
            ChatMessage(
                role=Role.USER,
                text="Test message",
                additional_properties={"user_id": "22345678-1234-1234-1234-123456789012"},
            ),
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 1
        assert user_id == "22345678-1234-1234-1234-123456789012"
        assert requests[0].user_id == "22345678-1234-1234-1234-123456789012"

    async def test_map_messages_with_provided_user_id_fallback(self, mock_client: AsyncMock) -> None:
        """Test using provided_user_id when no other source is available."""
        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [ChatMessage(role=Role.USER, text="Test message")]

        requests, user_id = await processor._map_messages(
            messages, Activity.UPLOAD_TEXT, provided_user_id="32345678-1234-1234-1234-123456789012"
        )

        assert len(requests) == 1
        assert user_id == "32345678-1234-1234-1234-123456789012"
        assert requests[0].user_id == "32345678-1234-1234-1234-123456789012"

    async def test_map_messages_returns_empty_when_no_user_id(self, mock_client: AsyncMock) -> None:
        """Test that empty results are returned when user_id cannot be resolved."""
        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [ChatMessage(role=Role.USER, text="Test message")]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 0
        assert user_id is None

    async def test_process_content_sends_activities_when_not_applicable(
        self, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test that response is returned when scopes don't apply (activities sent in background)."""
        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)

        pc_request = process_content_request_factory()

        # Mock get_protection_scopes to return no applicable scopes
        mock_ps_response = MagicMock()
        mock_ps_response.scopes = []
        mock_client.get_protection_scopes.return_value = mock_ps_response

        # Mock send_content_activities to return success (called in background)
        mock_ca_response = MagicMock()
        mock_ca_response.error = None
        mock_client.send_content_activities.return_value = mock_ca_response

        response = await processor._process_with_scopes(pc_request)

        mock_client.get_protection_scopes.assert_called_once()
        mock_client.process_content.assert_not_called()
        # Response should have id=204 when no scopes apply
        assert response.id == "204"

    async def test_process_content_handles_activities_error(
        self, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test that errors in background activities don't affect the response."""
        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)

        pc_request = process_content_request_factory()

        # Mock get_protection_scopes to return no applicable scopes
        mock_ps_response = MagicMock()
        mock_ps_response.scopes = []
        mock_client.get_protection_scopes.return_value = mock_ps_response

        # Mock send_content_activities to return error (called in background task)
        mock_ca_response = MagicMock()
        mock_ca_response.error = "Test error message"
        mock_client.send_content_activities.return_value = mock_ca_response

        response = await processor._process_with_scopes(pc_request)

        # Since activities are sent in background, errors don't affect the response
        # Response should have id=204 when no scopes apply
        assert response.id == "204"


class TestUserIdResolution:
    """Test user ID resolution from various sources."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock Purview client."""
        client = AsyncMock()
        client.get_user_info_from_token = AsyncMock(
            return_value={
                "tenant_id": "12345678-1234-1234-1234-123456789012",
                "user_id": "11111111-1111-1111-1111-111111111111",
                "client_id": "12345678-1234-1234-1234-123456789012",
            }
        )
        return client

    @pytest.fixture
    def settings(self) -> PurviewSettings:
        """Create settings."""
        return PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )

    async def test_user_id_from_token_when_no_other_source(self, mock_client: AsyncMock) -> None:
        """Test user_id is extracted from token when no other source available."""
        settings = PurviewSettings(app_name="Test App")  # No tenant_id or app_location
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [ChatMessage(role=Role.USER, text="Test")]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        mock_client.get_user_info_from_token.assert_called_once()
        assert user_id == "11111111-1111-1111-1111-111111111111"

    async def test_user_id_from_additional_properties_takes_priority(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test user_id from additional_properties takes priority over token."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [
            ChatMessage(
                role=Role.USER,
                text="Test",
                additional_properties={"user_id": "22222222-2222-2222-2222-222222222222"},
            )
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        # Token info should not be called since we have user_id in message
        mock_client.get_user_info_from_token.assert_not_called()
        assert user_id == "22222222-2222-2222-2222-222222222222"

    async def test_user_id_from_author_name_as_fallback(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test user_id is extracted from author_name when it's a valid GUID."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [
            ChatMessage(
                role=Role.USER,
                text="Test",
                author_name="33333333-3333-3333-3333-333333333333",
            )
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert user_id == "33333333-3333-3333-3333-333333333333"

    async def test_author_name_ignored_if_not_valid_guid(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test author_name is ignored if it's not a valid GUID."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [
            ChatMessage(
                role=Role.USER,
                text="Test",
                author_name="John Doe",  # Not a GUID
            )
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        # Should return empty since author_name is not a valid GUID
        assert user_id is None
        assert len(requests) == 0

    async def test_provided_user_id_used_as_last_resort(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test provided_user_id parameter is used as last resort."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [ChatMessage(role=Role.USER, text="Test")]

        requests, user_id = await processor._map_messages(
            messages, Activity.UPLOAD_TEXT, provided_user_id="44444444-4444-4444-4444-444444444444"
        )

        assert user_id == "44444444-4444-4444-4444-444444444444"

    async def test_invalid_provided_user_id_ignored(self, mock_client: AsyncMock, settings: PurviewSettings) -> None:
        """Test invalid provided_user_id is ignored."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [ChatMessage(role=Role.USER, text="Test")]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT, provided_user_id="not-a-guid")

        assert user_id is None
        assert len(requests) == 0

    async def test_multiple_messages_same_user_id(self, mock_client: AsyncMock, settings: PurviewSettings) -> None:
        """Test that all messages use the same resolved user_id."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [
            ChatMessage(
                role=Role.USER, text="First", additional_properties={"user_id": "55555555-5555-5555-5555-555555555555"}
            ),
            ChatMessage(role=Role.ASSISTANT, text="Response"),
            ChatMessage(role=Role.USER, text="Second"),
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert user_id == "55555555-5555-5555-5555-555555555555"
        # All requests should have the same user_id
        assert all(req.user_id == "55555555-5555-5555-5555-555555555555" for req in requests)

    async def test_first_valid_user_id_in_messages_is_used(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test that the first valid user_id found in messages is used for all."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [
            ChatMessage(role=Role.USER, text="First", author_name="Not a GUID"),
            ChatMessage(
                role=Role.ASSISTANT,
                text="Response",
                additional_properties={"user_id": "66666666-6666-6666-6666-666666666666"},
            ),
            ChatMessage(
                role=Role.USER, text="Third", additional_properties={"user_id": "77777777-7777-7777-7777-777777777777"}
            ),
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        # First valid user_id (from second message) should be used
        assert user_id == "66666666-6666-6666-6666-666666666666"
        assert all(req.user_id == "66666666-6666-6666-6666-666666666666" for req in requests)


class TestScopedContentProcessorCaching:
    """Test caching functionality in ScopedContentProcessor."""

    @pytest.fixture
    def mock_client(self) -> AsyncMock:
        """Create a mock Purview client."""
        client = AsyncMock()
        client.get_user_info_from_token = AsyncMock(
            return_value={
                "tenant_id": "12345678-1234-1234-1234-123456789012",
                "user_id": "12345678-1234-1234-1234-123456789012",
                "client_id": "12345678-1234-1234-1234-123456789012",
            }
        )
        client.get_protection_scopes = AsyncMock()
        return client

    @pytest.fixture
    def settings(self) -> PurviewSettings:
        """Create test settings."""
        location = PurviewAppLocation(location_type=PurviewLocationType.APPLICATION, location_value="app-id")
        return PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            default_user_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=location,
        )

    async def test_protection_scopes_cached_on_first_call(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test that protection scopes response is cached after first call."""
        from agent_framework_purview._cache import InMemoryCacheProvider
        from agent_framework_purview._models import ProtectionScopesResponse

        cache_provider = InMemoryCacheProvider()
        processor = ScopedContentProcessor(mock_client, settings, cache_provider=cache_provider)

        mock_client.get_protection_scopes.return_value = ProtectionScopesResponse(
            scope_identifier="scope-123", scopes=[]
        )

        messages = [ChatMessage(role=Role.USER, text="Test")]

        await processor.process_messages(messages, Activity.UPLOAD_TEXT, user_id="12345678-1234-1234-1234-123456789012")

        mock_client.get_protection_scopes.assert_called_once()

        await processor.process_messages(messages, Activity.UPLOAD_TEXT, user_id="12345678-1234-1234-1234-123456789012")

        mock_client.get_protection_scopes.assert_called_once()

    async def test_payment_required_exception_cached_at_tenant_level(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test that 402 payment required exceptions are cached at tenant level."""
        from agent_framework_purview._cache import InMemoryCacheProvider
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        cache_provider = InMemoryCacheProvider()
        processor = ScopedContentProcessor(mock_client, settings, cache_provider=cache_provider)

        mock_client.get_protection_scopes.side_effect = PurviewPaymentRequiredError("Payment required")

        messages = [ChatMessage(role=Role.USER, text="Test")]

        with pytest.raises(PurviewPaymentRequiredError):
            await processor.process_messages(
                messages, Activity.UPLOAD_TEXT, user_id="12345678-1234-1234-1234-123456789012"
            )

        mock_client.get_protection_scopes.assert_called_once()

        with pytest.raises(PurviewPaymentRequiredError):
            await processor.process_messages(
                messages, Activity.UPLOAD_TEXT, user_id="12345678-1234-1234-1234-123456789012"
            )

        mock_client.get_protection_scopes.assert_called_once()

    async def test_custom_cache_provider_used(self, mock_client: AsyncMock, settings: PurviewSettings) -> None:
        """Test that custom cache provider is used when provided."""
        from agent_framework_purview._cache import InMemoryCacheProvider

        custom_cache = InMemoryCacheProvider(default_ttl_seconds=60)
        processor = ScopedContentProcessor(mock_client, settings, cache_provider=custom_cache)

        assert processor._cache is custom_cache
        assert processor._cache._default_ttl == 60
