# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview processor."""

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import Message

from agent_framework_purview import PurviewAppLocation, PurviewLocationType, PurviewSettings
from agent_framework_purview._models import (
    Activity,
    DlpAction,
    DlpActionInfo,
    ExecutionMode,
    PolicyLocation,
    PolicyScope,
    ProcessContentResponse,
    ProtectionScopeActivities,
    ProtectionScopeState,
    PurviewBinaryContent,
    PurviewTextContent,
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
            Message(role="user", contents=["Hello"]),
            Message(role="assistant", contents=["Hi there"]),
        ]

        with patch.object(processor, "_map_messages", return_value=([], None)) as mock_map:
            should_block, user_id = await processor.process_messages(messages, Activity.UPLOAD_TEXT)

            assert should_block is False
            assert user_id is None
            mock_map.assert_called_once_with(messages, Activity.UPLOAD_TEXT, None, None)

    async def test_process_messages_blocks_content(
        self, processor: ScopedContentProcessor, process_content_request_factory
    ) -> None:
        """Test process_messages returns True when content should be blocked."""
        messages = [Message(role="user", contents=["Sensitive content"])]

        mock_request = process_content_request_factory("Sensitive content")

        mock_response = ProcessContentResponse(
            policy_actions=cast(
                Any, [DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)]
            )
        )

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
            Message(
                role="user",
                contents=["Test message"],
                message_id="msg-123",
                author_name="12345678-1234-1234-1234-123456789012",
            ),
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 1
        assert requests[0].user_id == "12345678-1234-1234-1234-123456789012"
        assert requests[0].tenant_id == "12345678-1234-1234-1234-123456789012"
        assert user_id == "12345678-1234-1234-1234-123456789012"

    async def test_map_messages_submits_each_content_item_in_separate_request(
        self, processor: ScopedContentProcessor
    ) -> None:
        """Test _map_messages submits every content item in a separate request.

        Non-text content flattened to Message.text is empty for binary, tool-call and
        tool-result content, which would have Purview classify an empty string.
        """
        from agent_framework import Content

        secret = b"credit card 4532667785213500"
        messages = [
            Message(
                role="user",
                contents=[
                    Content.from_data(data=secret, media_type="application/octet-stream"),
                    Content(
                        "function_call",
                        call_id="call-1",
                        name="send_email",
                        arguments={"body": "ssn 120-98-1437"},
                    ),
                    Content("function_result", call_id="call-1", result="account 999-12345"),
                ],
            )
        ]

        requests, _ = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 3
        entries = [request.content_to_process.content_entries[0] for request in requests]
        assert all(len(request.content_to_process.content_entries) == 1 for request in requests)
        binary_entry, call_entry, result_entry = entries
        assert isinstance(binary_entry.content, PurviewBinaryContent)
        assert binary_entry.content.data == secret

        assert isinstance(call_entry.content, PurviewTextContent)
        assert "send_email" in call_entry.content.data
        assert "120-98-1437" in call_entry.content.data

        assert isinstance(result_entry.content, PurviewTextContent)
        assert "999-12345" in result_entry.content.data

        # Every entry must carry real content; an empty payload would not be evaluated.
        assert all(entry.content is not None for entry in entries)
        assert not any(isinstance(entry.content, PurviewTextContent) and entry.content.data == "" for entry in entries)

    async def test_map_messages_skips_empty_text_and_data(self, processor: ScopedContentProcessor) -> None:
        """Test _map_messages does not create requests for empty text or binary data."""
        from agent_framework import Content

        messages = [
            Message(
                role="user",
                contents=[
                    "",
                    Content.from_data(data=b"", media_type="application/octet-stream"),
                ],
            )
        ]

        requests, _ = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert requests == []

    async def test_map_messages_decodes_data_uri_with_media_type_parameters(
        self, processor: ScopedContentProcessor
    ) -> None:
        """Test _map_messages decodes base64 data URIs whose media type carries parameters.

        A data URI may carry any number of ";parameter=value" segments between the media type and
        ";base64". Failing to decode one leaves the payload as a base64 string that no classifier
        can read.
        """
        from agent_framework import Content

        secret = b"credit card 4532667785213500"
        content = Content.from_data(data=secret, media_type="text/plain;charset=utf-8")
        assert content.uri is not None
        assert content.uri.startswith("data:text/plain;charset=utf-8;base64,")

        messages = [Message(role="user", contents=[content])]

        requests, _ = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        entries = requests[0].content_to_process.content_entries
        assert len(entries) == 1
        assert isinstance(entries[0].content, PurviewBinaryContent)
        assert entries[0].content.data == secret

    async def test_map_messages_submits_additional_properties_on_structured_content(
        self, processor: ScopedContentProcessor
    ) -> None:
        """Test _map_messages serializes structured content whole, including additional_properties.

        Building an entry from name/arguments alone drops additional_properties, leaving a
        data channel on tool calls and tool results that Purview never sees.
        """
        from agent_framework import Content

        call = Content("function_call", call_id="call-1", name="send_email", arguments={"body": "hello"})
        call.additional_properties = {"hidden": "ssn 120-98-1437"}
        result = Content("function_result", call_id="call-1", result="ok")
        result.additional_properties = {"hidden": "card 4532667785213500"}

        messages = [Message(role="user", contents=[call, result])]

        requests, _ = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        assert len(requests) == 2
        call_entry = requests[0].content_to_process.content_entries[0]
        result_entry = requests[1].content_to_process.content_entries[0]

        assert isinstance(call_entry.content, PurviewTextContent)
        assert "120-98-1437" in call_entry.content.data
        assert "send_email" in call_entry.content.data

        assert isinstance(result_entry.content, PurviewTextContent)
        assert "4532667785213500" in result_entry.content.data

    async def test_map_messages_without_defaults_gets_token_info(self, mock_client: AsyncMock) -> None:
        """Test _map_messages gets token info when settings lack some defaults."""
        settings = PurviewSettings(app_name="Test App", tenant_id="12345678-1234-1234-1234-123456789012")
        processor = ScopedContentProcessor(mock_client, settings)
        messages = [Message(role="user", contents=["Test"], message_id="msg-123")]

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

        messages = [Message(role="user", contents=["Test"], message_id="msg-123")]

        with pytest.raises(ValueError, match="Tenant id required"):
            await processor._map_messages(messages, Activity.UPLOAD_TEXT)

    async def test_check_applicable_scopes_no_scopes(
        self, processor: ScopedContentProcessor, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes when no scopes are returned."""
        from agent_framework_purview._models import ProtectionScopesResponse

        request = process_content_request_factory()
        response = ProtectionScopesResponse(scopes=None)

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
        scope_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationApplication",
            value="app-id",
        )
        scope = PolicyScope(
            **cast(
                Any,
                {
                    "policyActions": [block_action],
                    "activities": ProtectionScopeActivities.UPLOAD_TEXT,
                    "locations": [scope_location],
                },
            )
        )
        response = ProtectionScopesResponse(scopes=cast(Any, [scope]))

        should_process, actions, execution_mode = processor._check_applicable_scopes(request, response)

        assert should_process is True
        assert len(actions) == 1
        assert actions[0].action == DlpAction.BLOCK_ACCESS

    async def test_check_applicable_scopes_matches_location_case_insensitively(
        self, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes matches location values regardless of GUID casing.

        A casing difference between the request location and the scope location would
        otherwise hide an applicable block scope.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        pc_request.content_to_process.protected_app_metadata.application_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationApplication",
            value="A1B2C3D4-E5F6-4A5B-8C9D-0E1F2A3B4C5D",
        )
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_INLINE,
            locations=[
                PolicyLocation(
                    data_type="#microsoft.graph.policyLocationApplication",
                    value="a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                )
            ],
            policy_actions=[DlpActionInfo(action=DlpAction.BLOCK_ACCESS)],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])

        should_process, dlp_actions, execution_mode = ScopedContentProcessor._check_applicable_scopes(
            pc_request, ps_response
        )

        assert should_process is True
        assert execution_mode == ExecutionMode.EVALUATE_INLINE
        assert dlp_actions

    async def test_check_applicable_scopes_matches_url_location_host_case_insensitively(
        self, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes ignores host casing on URL locations.

        The scheme and host of a URL are case-insensitive, so a casing difference there must not
        hide an applicable scope.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        pc_request.content_to_process.protected_app_metadata.application_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationUrl",
            value="HTTPS://Contoso.com/sites/marketing",
        )
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_INLINE,
            locations=[
                PolicyLocation(
                    data_type="#microsoft.graph.policyLocationUrl",
                    value="https://contoso.com/sites/marketing",
                )
            ],
            policy_actions=[DlpActionInfo(action=DlpAction.BLOCK_ACCESS)],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])

        should_process, dlp_actions, _ = ScopedContentProcessor._check_applicable_scopes(pc_request, ps_response)

        assert should_process is True
        assert dlp_actions

    async def test_check_applicable_scopes_treats_url_location_path_as_case_sensitive(
        self, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes keeps URL path casing significant.

        URL paths are case-sensitive, so a scope scoped to one path must not match a different path
        that differs only in casing.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        pc_request.content_to_process.protected_app_metadata.application_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationUrl",
            value="https://contoso.com/sites/Marketing",
        )
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_INLINE,
            locations=[
                PolicyLocation(
                    data_type="#microsoft.graph.policyLocationUrl",
                    value="https://contoso.com/sites/marketing",
                )
            ],
            policy_actions=[DlpActionInfo(action=DlpAction.BLOCK_ACCESS)],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])

        should_process, dlp_actions, _ = ScopedContentProcessor._check_applicable_scopes(pc_request, ps_response)

        assert should_process is False
        assert dlp_actions == []

    async def test_check_applicable_scopes_treats_url_location_query_as_case_sensitive(
        self, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes keeps URL query casing significant.

        A query value is case-sensitive, and it may follow the host directly with no path between
        them, so the authority has to end at the query delimiter as well as the path delimiter.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        pc_request.content_to_process.protected_app_metadata.application_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationUrl",
            value="https://contoso.com?label=Secret",
        )
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_INLINE,
            locations=[
                PolicyLocation(
                    data_type="#microsoft.graph.policyLocationUrl",
                    value="https://contoso.com?label=secret",
                )
            ],
            policy_actions=[DlpActionInfo(action=DlpAction.BLOCK_ACCESS)],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])

        should_process, dlp_actions, _ = ScopedContentProcessor._check_applicable_scopes(pc_request, ps_response)

        assert should_process is False
        assert dlp_actions == []

    async def test_check_applicable_scopes_treats_url_location_fragment_as_case_sensitive(
        self, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes keeps URL fragment casing significant.

        A fragment may follow the host directly, so the authority has to end at the fragment
        delimiter as well.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        pc_request.content_to_process.protected_app_metadata.application_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationUrl",
            value="https://contoso.com#Section",
        )
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_INLINE,
            locations=[
                PolicyLocation(
                    data_type="#microsoft.graph.policyLocationUrl",
                    value="https://contoso.com#section",
                )
            ],
            policy_actions=[DlpActionInfo(action=DlpAction.BLOCK_ACCESS)],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])

        should_process, dlp_actions, _ = ScopedContentProcessor._check_applicable_scopes(pc_request, ps_response)

        assert should_process is False
        assert dlp_actions == []

    async def test_check_applicable_scopes_treats_url_location_userinfo_as_case_sensitive(
        self, process_content_request_factory
    ) -> None:
        """Test _check_applicable_scopes keeps URL userinfo casing significant.

        Credentials embedded in the authority are case-sensitive, so only the host half of the
        authority may be folded.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        pc_request.content_to_process.protected_app_metadata.application_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationUrl",
            value="https://alice:SecretPass@contoso.com/docs",
        )
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_INLINE,
            locations=[
                PolicyLocation(
                    data_type="#microsoft.graph.policyLocationUrl",
                    value="https://alice:secretpass@contoso.com/docs",
                )
            ],
            policy_actions=[DlpActionInfo(action=DlpAction.BLOCK_ACCESS)],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])

        should_process, dlp_actions, _ = ScopedContentProcessor._check_applicable_scopes(pc_request, ps_response)

        assert should_process is False
        assert dlp_actions == []

    async def test_combine_policy_actions(self, processor: ScopedContentProcessor) -> None:
        """Test _combine_policy_actions merges action lists."""
        action1 = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)
        action2 = DlpActionInfo(action=DlpAction.OTHER, restrictionAction=RestrictionAction.OTHER)

        combined = processor._combine_policy_actions([action1], [action2])

        assert len(combined) == 2
        assert action1 in combined
        assert action2 in combined

    async def test_combine_policy_actions_preserves_restriction_only_actions(
        self, processor: ScopedContentProcessor
    ) -> None:
        """Test _combine_policy_actions keeps actions that only set restrictionAction."""
        existing_action = DlpActionInfo(action=DlpAction.OTHER, restrictionAction=RestrictionAction.OTHER)
        restriction_only_action = DlpActionInfo(restriction_action=RestrictionAction.BLOCK)

        combined = processor._combine_policy_actions([existing_action], [restriction_only_action])

        assert combined == [existing_action, restriction_only_action]

    async def test_combine_policy_actions_deduplicates_by_action_and_restriction(
        self, processor: ScopedContentProcessor
    ) -> None:
        """Test _combine_policy_actions removes exact duplicate actions."""
        block_action = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restriction_action=RestrictionAction.BLOCK)
        duplicate_block_action = DlpActionInfo(
            action=DlpAction.BLOCK_ACCESS, restriction_action=RestrictionAction.BLOCK
        )
        restriction_only_action = DlpActionInfo(restriction_action=RestrictionAction.BLOCK)

        combined = processor._combine_policy_actions(
            [block_action],
            [duplicate_block_action, restriction_only_action],
        )

        assert combined == [block_action, restriction_only_action]

    async def test_process_with_scopes_calls_client_methods(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test _process_with_scopes calls process_content immediately and warms scopes in background on cache miss."""
        from agent_framework_purview._models import (
            ContentActivitiesResponse,
            ProtectionScopesResponse,
        )

        request = process_content_request_factory()

        mock_client.get_protection_scopes = AsyncMock(return_value=ProtectionScopesResponse(scopes=[]))
        mock_client.process_content = AsyncMock(
            return_value=ProcessContentResponse(
                id="response-123", protection_scope_state=ProtectionScopeState.NOT_MODIFIED
            )
        )
        mock_client.send_content_activities = AsyncMock(return_value=ContentActivitiesResponse(**{"error": None}))

        response = await processor._process_with_scopes(request)

        # On cache miss, ProcessContent runs in the foreground and the response is returned.
        assert response.id == "response-123"
        mock_client.process_content.assert_called_once()
        assert mock_client.process_content.call_args.args[0].process_inline is True

        # Protection scopes are refreshed in a background task.
        await asyncio.gather(*list(processor._background_tasks))
        mock_client.get_protection_scopes.assert_called_once()
        mock_client.send_content_activities.assert_called_once()

    async def test_process_with_scopes_isolates_the_background_refresh_request(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test a cold scopes cache evaluates inline and hands the background refresh its own request.

        The background refresh must not observe foreground mutations of the request it was given.
        """
        pc_request = process_content_request_factory()
        cast(Any, processor._cache).get = AsyncMock(return_value=None)
        mock_client.process_content.return_value = ProcessContentResponse(id="1")

        captured: list[Any] = []

        async def capture_refresh(ps_req: Any, cache_key: str, request: Any) -> None:
            captured.append(request)

        cast(Any, processor)._refresh_protection_scopes_background = capture_refresh

        await processor._process_with_scopes(pc_request)
        await asyncio.gather(*list(processor._background_tasks))

        # Content was evaluated inline, so there is no window in which it goes unevaluated.
        mock_client.process_content.assert_called_once()
        assert pc_request.process_inline is True

        # The background task got its own request object.
        assert captured and captured[0] is not pc_request

    async def test_process_with_scopes_evaluates_unknown_execution_mode_inline(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test an unrecognised executionMode is evaluated inline.

        executionMode is an evolvable enum, so an unknown member must not skip enforcement.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.UNKNOWN_FUTURE_VALUE,
            locations=[PolicyLocation(data_type="microsoft.graph.policyLocationApplication", value="app-id")],
            policy_actions=[],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])
        cast(Any, processor._cache).get = AsyncMock(side_effect=[None, ps_response])
        mock_client.process_content.return_value = ProcessContentResponse(id="1")

        await processor._process_with_scopes(pc_request)

        mock_client.process_content.assert_called_once()
        assert pc_request.process_inline is True

    async def test_process_with_scopes_reports_block_action_on_offline_scope(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test a block verdict known from an offline scope is still reported rather than discarded."""
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_OFFLINE,
            locations=[PolicyLocation(data_type="microsoft.graph.policyLocationApplication", value="app-id")],
            policy_actions=[
                DlpActionInfo(action=DlpAction.RESTRICT_ACCESS, restriction_action=RestrictionAction.BLOCK)
            ],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])
        cast(Any, processor._cache).get = AsyncMock(side_effect=[None, ps_response])
        mock_client.process_content.return_value = ProcessContentResponse(id="1")

        response = await processor._process_with_scopes(pc_request)
        await asyncio.gather(*list(processor._background_tasks))

        assert response.policy_actions
        assert all(
            action.action == DlpAction.RESTRICT_ACCESS and action.restriction_action == RestrictionAction.BLOCK
            for action in response.policy_actions
        )

    async def test_process_with_scopes_ignores_non_blocking_restriction_on_offline_scope(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test a restrictAccess scope whose restriction mode does not block is not reported as blocking.

        restrictAccess carries a separate restriction mode which may be audit, warn or allow. Only an
        explicit block mode withholds the content, so the other modes must not surface as a verdict.
        """
        from agent_framework_purview._models import ProtectionScopesResponse

        pc_request = process_content_request_factory()
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            execution_mode=ExecutionMode.EVALUATE_OFFLINE,
            locations=[PolicyLocation(data_type="microsoft.graph.policyLocationApplication", value="app-id")],
            policy_actions=[
                DlpActionInfo(action=DlpAction.RESTRICT_ACCESS, restriction_action=RestrictionAction.OTHER)
            ],
        )
        ps_response = ProtectionScopesResponse(scopes=[scope])
        cast(Any, processor._cache).get = AsyncMock(side_effect=[None, ps_response])
        mock_client.process_content.return_value = ProcessContentResponse(id="1")

        response = await processor._process_with_scopes(pc_request)
        await asyncio.gather(*list(processor._background_tasks))

        assert not response.policy_actions

    async def test_process_with_scopes_preserves_restriction_only_policy_actions(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test cold-cache ProcessContent actions are not dropped when they only contain restrictionAction."""
        from agent_framework_purview._models import ProtectionScopesResponse

        request = process_content_request_factory()
        restriction_only_action = DlpActionInfo(restriction_action=RestrictionAction.BLOCK)

        mock_client.get_protection_scopes = AsyncMock(return_value=ProtectionScopesResponse(scopes=[]))
        mock_client.process_content = AsyncMock(
            return_value=ProcessContentResponse(
                id="response-123",
                protection_scope_state=ProtectionScopeState.NOT_MODIFIED,
                policy_actions=[restriction_only_action],
            )
        )

        response = await processor._process_with_scopes(request)

        assert response.policy_actions == [restriction_only_action]
        await asyncio.gather(*list(processor._background_tasks))

    async def test_process_with_cached_scopes_preserves_restriction_only_policy_actions(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test cached ProtectionScopes actions are not dropped when they only contain restrictionAction."""
        from agent_framework_purview._models import (
            ExecutionMode,
            PolicyLocation,
            PolicyScope,
            ProtectionScopeActivities,
            ProtectionScopesResponse,
        )

        request = process_content_request_factory()
        restriction_only_action = DlpActionInfo(restriction_action=RestrictionAction.BLOCK)
        process_content_action = DlpActionInfo(action=DlpAction.OTHER, restriction_action=RestrictionAction.OTHER)
        scope_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationApplication",
            value="app-id",
        )
        scope = PolicyScope(
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            locations=[scope_location],
            policy_actions=[restriction_only_action],
            execution_mode=ExecutionMode.EVALUATE_INLINE,
        )

        cast(Any, processor._cache).get = AsyncMock(
            side_effect=[
                None,
                ProtectionScopesResponse(scope_identifier="scope-123", scopes=[scope]),
            ]
        )
        mock_client.process_content = AsyncMock(
            return_value=ProcessContentResponse(
                id="response-123",
                protection_scope_state=ProtectionScopeState.NOT_MODIFIED,
                policy_actions=[process_content_action],
            )
        )

        response = await processor._process_with_scopes(request)

        assert response.policy_actions == [process_content_action, restriction_only_action]

    async def test_process_with_scopes_ignores_unexpected_cached_value_type(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test that a corrupted cache entry does not crash processing."""
        from agent_framework_purview._models import ProtectionScopesResponse

        request = process_content_request_factory()

        mock_client.get_protection_scopes = AsyncMock(return_value=ProtectionScopesResponse(scopes=[]))
        # Return a valid, inline scope so we stay on the normal (non-background) path.
        scope_location = PolicyLocation(
            data_type="microsoft.graph.policyLocationApplication",
            value="app-id",
        )
        scope = PolicyScope(
            **cast(
                Any,
                {
                    "activities": ProtectionScopeActivities.UPLOAD_TEXT,
                    "locations": [scope_location],
                    "execution_mode": ExecutionMode.EVALUATE_INLINE,
                },
            )
        )
        mock_client.get_protection_scopes = AsyncMock(return_value=ProtectionScopesResponse(scopes=cast(Any, [scope])))
        mock_client.process_content = AsyncMock(
            return_value=ProcessContentResponse(id="ok", protection_scope_state=ProtectionScopeState.NOT_MODIFIED)
        )

        # First cache read is the tenant payment key (None). Second is the scopes cache (corrupt value).
        cast(Any, processor._cache).get = AsyncMock(side_effect=[None, "corrupt-value"])
        cast(Any, processor._cache).set = AsyncMock()

        response = await processor._process_with_scopes(request)

        assert response.id == "ok"
        mock_client.process_content.assert_called_once()
        await asyncio.gather(*list(processor._background_tasks))
        mock_client.get_protection_scopes.assert_called_once()

    async def test_process_with_scopes_uses_tenant_payment_exception_cache(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test that a cached 402 exception short-circuits all subsequent requests for the tenant."""
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        request = process_content_request_factory()

        cast(Any, processor._cache).get = AsyncMock(return_value=PurviewPaymentRequiredError("Payment required"))

        with pytest.raises(PurviewPaymentRequiredError):
            await processor._process_with_scopes(request)

        mock_client.get_protection_scopes.assert_not_called()

    async def test_process_content_background_retries_on_modified_state(
        self, processor: ScopedContentProcessor, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test offline background processing invalidates cache and retries when scope state changes."""
        request = process_content_request_factory()
        request.scope_identifier = "etag-1"

        mock_client.process_content = AsyncMock(
            side_effect=[
                ProcessContentResponse(id="r1", protection_scope_state=ProtectionScopeState.MODIFIED),
                ProcessContentResponse(id="r2", protection_scope_state=ProtectionScopeState.NOT_MODIFIED),
            ]
        )
        cast(Any, processor._cache).remove = AsyncMock()

        await processor._process_content_background(request, cache_key="purview:protection_scopes:abc")

        cast(Any, processor._cache).remove.assert_called_once_with("purview:protection_scopes:abc")
        assert mock_client.process_content.call_count == 2

    async def test_background_scope_refresh_caches_payment_required(
        self, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """402 raised during background scope refresh is cached at the tenant level."""
        from agent_framework_purview._cache import InMemoryCacheProvider
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )

        cache = InMemoryCacheProvider()
        processor = ScopedContentProcessor(mock_client, settings, cache_provider=cache)

        mock_client.get_protection_scopes = AsyncMock(side_effect=PurviewPaymentRequiredError("nope"))
        mock_client.process_content = AsyncMock(
            return_value=ProcessContentResponse(id="pc-1", protection_scope_state=ProtectionScopeState.NOT_MODIFIED)
        )

        request = process_content_request_factory()
        await processor._process_with_scopes(request)
        await asyncio.gather(*list(processor._background_tasks))

        cached = await cache.get(f"purview:payment_required:{request.tenant_id}")
        assert isinstance(cached, PurviewPaymentRequiredError)

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
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [
            Message(
                role="user",
                contents=["Test message"],
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
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [Message(role="user", contents=["Test message"])]

        requests, user_id = await processor._map_messages(
            messages, Activity.UPLOAD_TEXT, provided_user_id="32345678-1234-1234-1234-123456789012"
        )

        assert len(requests) == 1
        assert user_id == "32345678-1234-1234-1234-123456789012"
        assert requests[0].user_id == "32345678-1234-1234-1234-123456789012"

    async def test_map_messages_raises_when_no_user_id(self, mock_client: AsyncMock) -> None:
        """Test that an unresolvable user_id fails closed instead of skipping evaluation."""
        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [Message(role="user", contents=["Test message"])]

        with pytest.raises(ValueError, match="No user id"):
            await processor._map_messages(messages, Activity.UPLOAD_TEXT)

    async def test_process_content_sends_activities_when_not_applicable(
        self, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test that response is returned when scopes don't apply (activities sent in background)."""
        from agent_framework_purview._models import ProtectionScopesResponse

        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)

        pc_request = process_content_request_factory()

        mock_ps_response = ProtectionScopesResponse(scopes=[])
        cast(Any, processor._cache).get = AsyncMock(side_effect=[None, mock_ps_response])

        # Mock send_content_activities to return success (called in background)
        mock_ca_response = MagicMock()
        mock_ca_response.error = None
        mock_client.send_content_activities.return_value = mock_ca_response

        response = await processor._process_with_scopes(pc_request)

        mock_client.get_protection_scopes.assert_not_called()
        mock_client.process_content.assert_not_called()
        await asyncio.gather(*list(processor._background_tasks))
        mock_client.send_content_activities.assert_called_once()
        # Response should have id=204 when no scopes apply
        assert response.id == "204"

    async def test_process_content_handles_activities_error(
        self, mock_client: AsyncMock, process_content_request_factory
    ) -> None:
        """Test that errors in background activities don't affect the response."""
        from agent_framework_purview._models import ProtectionScopesResponse

        settings = PurviewSettings(
            app_name="Test App",
            tenant_id="12345678-1234-1234-1234-123456789012",
            purview_app_location=PurviewAppLocation(
                location_type=PurviewLocationType.APPLICATION, location_value="app-id"
            ),
        )
        processor = ScopedContentProcessor(mock_client, settings)

        pc_request = process_content_request_factory()

        mock_ps_response = ProtectionScopesResponse(scopes=[])
        cast(Any, processor._cache).get = AsyncMock(side_effect=[None, mock_ps_response])

        # Mock send_content_activities to return error (called in background task)
        mock_ca_response = MagicMock()
        mock_ca_response.error = "Test error message"
        mock_client.send_content_activities.return_value = mock_ca_response

        response = await processor._process_with_scopes(pc_request)

        # Since activities are sent in background, errors don't affect the response
        # Response should have id=204 when no scopes apply
        assert response.id == "204"
        await asyncio.gather(*list(processor._background_tasks))
        mock_client.send_content_activities.assert_called_once()


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

        messages = [Message(role="user", contents=["Test"])]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        mock_client.get_user_info_from_token.assert_called_once()
        assert user_id == "11111111-1111-1111-1111-111111111111"

    async def test_user_id_from_token_takes_priority_over_additional_properties(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test token user_id takes priority over message additional_properties."""
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [
            Message(
                role="user",
                contents=["Test"],
                additional_properties={"user_id": "22222222-2222-2222-2222-222222222222"},
            )
        ]

        requests, user_id = await processor._map_messages(messages, Activity.UPLOAD_TEXT)

        mock_client.get_user_info_from_token.assert_called_once()
        assert user_id == "11111111-1111-1111-1111-111111111111"
        assert all(req.user_id == "11111111-1111-1111-1111-111111111111" for req in requests)

    async def test_user_id_from_author_name_as_fallback(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test user_id is extracted from author_name when it's a valid GUID."""
        processor = ScopedContentProcessor(mock_client, settings)
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [
            Message(
                role="user",
                contents=["Test"],
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
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [
            Message(
                role="user",
                contents=["Test"],
                author_name="John Doe",  # Not a GUID
            )
        ]

        # author_name is not a valid GUID, so no identity resolves and evaluation fails closed
        with pytest.raises(ValueError, match="No user id"):
            await processor._map_messages(messages, Activity.UPLOAD_TEXT)

    async def test_provided_user_id_used_as_last_resort(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test provided_user_id parameter is used as last resort."""
        processor = ScopedContentProcessor(mock_client, settings)
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [Message(role="user", contents=["Test"])]

        requests, user_id = await processor._map_messages(
            messages, Activity.UPLOAD_TEXT, provided_user_id="44444444-4444-4444-4444-444444444444"
        )

        assert user_id == "44444444-4444-4444-4444-444444444444"

    async def test_invalid_provided_user_id_ignored(self, mock_client: AsyncMock, settings: PurviewSettings) -> None:
        """Test invalid provided_user_id is ignored."""
        processor = ScopedContentProcessor(mock_client, settings)
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [Message(role="user", contents=["Test"])]

        with pytest.raises(ValueError, match="No user id"):
            await processor._map_messages(messages, Activity.UPLOAD_TEXT, provided_user_id="not-a-guid")

    async def test_unresolvable_user_id_blocks_processing(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test process_messages raises rather than sending content when no user id resolves.

        Without a user id there is no policy to evaluate against, so the content must not be
        forwarded to Purview or on to the model.
        """
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }
        processor = ScopedContentProcessor(mock_client, settings)

        messages = [Message(role="user", contents=["ssn 120-98-1437"])]

        with pytest.raises(ValueError, match="No user id"):
            await processor.process_messages(messages, Activity.UPLOAD_TEXT)

        mock_client.process_content.assert_not_called()

    async def test_multiple_messages_same_user_id(self, mock_client: AsyncMock, settings: PurviewSettings) -> None:
        """Test that all messages use the same resolved user_id."""
        processor = ScopedContentProcessor(mock_client, settings)
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [
            Message(
                role="user",
                contents=["First"],
                additional_properties={"user_id": "55555555-5555-5555-5555-555555555555"},
            ),
            Message(role="assistant", contents=["Response"]),
            Message(role="user", contents=["Second"]),
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
        mock_client.get_user_info_from_token.return_value = {
            "tenant_id": "12345678-1234-1234-1234-123456789012",
            "client_id": "12345678-1234-1234-1234-123456789012",
        }

        messages = [
            Message(role="user", contents=["First"], author_name="Not a GUID"),
            Message(
                role="assistant",
                contents=["Response"],
                additional_properties={"user_id": "66666666-6666-6666-6666-666666666666"},
            ),
            Message(
                role="user",
                contents=["Third"],
                additional_properties={"user_id": "77777777-7777-7777-7777-777777777777"},
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
        mock_client.process_content.return_value = ProcessContentResponse(
            id="ok", protection_scope_state=ProtectionScopeState.NOT_MODIFIED
        )

        messages = [Message(role="user", contents=["Test"])]

        await processor.process_messages(messages, Activity.UPLOAD_TEXT, user_id="12345678-1234-1234-1234-123456789012")
        await asyncio.gather(*list(processor._background_tasks))

        mock_client.get_protection_scopes.assert_called_once()

        await processor.process_messages(messages, Activity.UPLOAD_TEXT, user_id="12345678-1234-1234-1234-123456789012")

        mock_client.get_protection_scopes.assert_called_once()

    async def test_payment_required_exception_cached_at_tenant_level(
        self, mock_client: AsyncMock, settings: PurviewSettings
    ) -> None:
        """Test that background scope 402 returns once, then throws from the tenant-level cache."""
        from agent_framework_purview._cache import InMemoryCacheProvider
        from agent_framework_purview._exceptions import PurviewPaymentRequiredError

        cache_provider = InMemoryCacheProvider()
        processor = ScopedContentProcessor(mock_client, settings, cache_provider=cache_provider)

        mock_client.get_protection_scopes.side_effect = PurviewPaymentRequiredError("Payment required")
        mock_client.process_content.return_value = ProcessContentResponse(
            id="ok", protection_scope_state=ProtectionScopeState.NOT_MODIFIED
        )

        messages = [Message(role="user", contents=["Test"])]

        await processor.process_messages(messages, Activity.UPLOAD_TEXT, user_id="12345678-1234-1234-1234-123456789012")
        await asyncio.gather(*list(processor._background_tasks))

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
        assert isinstance(processor._cache, InMemoryCacheProvider)
        assert processor._cache._default_ttl == 60
