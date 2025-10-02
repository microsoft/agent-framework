# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from azure.core.credentials import AccessToken

from agent_framework_purview import PurviewSettings
from agent_framework_purview._client import PurviewClient
from agent_framework_purview._exceptions import (
    PurviewAuthenticationError,
    PurviewRateLimitError,
    PurviewRequestError,
    PurviewServiceError,
)
from agent_framework_purview._models import (
    Activity,
    ActivityMetadata,
    ContentToProcess,
    DeviceMetadata,
    IntegratedAppMetadata,
    OperatingSystemSpecifications,
    PolicyLocation,
    ProcessContentRequest,
    ProcessConversationMetadata,
    ProtectedAppMetadata,
    ProtectionScopesRequest,
    PurviewTextContent,
)


class TestPurviewClient:
    """Test PurviewClient functionality."""

    @pytest.fixture
    def mock_credential(self) -> MagicMock:
        """Create a mock async credential."""
        from azure.core.credentials_async import AsyncTokenCredential

        credential = MagicMock(spec=AsyncTokenCredential)
        # Mock get_token as an async function that returns an AccessToken
        mock_token = AccessToken("fake-token", 9999999999)

        async def mock_get_token(*args, **kwargs):
            return mock_token

        credential.get_token = mock_get_token
        return credential

    @pytest.fixture
    def settings(self) -> PurviewSettings:
        """Create test settings."""
        return PurviewSettings(app_name="Test App", tenant_id="test-tenant", default_user_id="test-user")

    @pytest.fixture
    async def client(self, mock_credential: MagicMock, settings: PurviewSettings) -> PurviewClient:
        """Create a PurviewClient with mock credential."""
        client = PurviewClient(mock_credential, settings, timeout=10.0)
        yield client
        await client.close()

    async def test_client_initialization(self, mock_credential: MagicMock, settings: PurviewSettings) -> None:
        """Test PurviewClient initialization."""
        client = PurviewClient(mock_credential, settings)

        assert client._credential == mock_credential
        assert client._settings == settings
        assert client._graph_uri == "https://graph.microsoft.com/v1.0"
        assert client._timeout == 10.0

        await client.close()

    async def test_client_custom_timeout(self, mock_credential: AsyncMock, settings: PurviewSettings) -> None:
        """Test PurviewClient with custom timeout."""
        client = PurviewClient(mock_credential, settings, timeout=30.0)

        assert client._timeout == 30.0

        await client.close()

    async def test_get_token_async_credential(self, client: PurviewClient, mock_credential: MagicMock) -> None:
        """Test _get_token with async credential."""
        token = await client._get_token(tenant_id="test-tenant")

        assert token == "fake-token"
        # Can't assert on the function itself, but we got the token so it was called

    async def test_get_token_sync_credential(self, settings: PurviewSettings) -> None:
        """Test _get_token with sync credential."""
        sync_credential = MagicMock()
        sync_credential.get_token = MagicMock(return_value=AccessToken("sync-token", 9999999999))

        client = PurviewClient(sync_credential, settings)

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_executor = AsyncMock()
            mock_executor.return_value = AccessToken("sync-token", 9999999999)
            mock_loop.return_value.run_in_executor = mock_executor

            token = await client._get_token(tenant_id="test-tenant")

            # The token should be extracted from AccessToken
            assert token == "sync-token"

        await client.close()

    async def test_extract_token_info(self) -> None:
        """Test _extract_token_info extracts JWT claims."""
        # Create a minimal JWT token (header.payload.signature)
        # Payload: {"tid": "test-tenant", "oid": "test-user", "appid": "test-client", "idtyp": "user"}
        import base64
        import json

        payload = {"tid": "test-tenant", "oid": "test-user", "appid": "test-client", "idtyp": "user"}
        payload_str = json.dumps(payload)
        payload_bytes = payload_str.encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")

        fake_token = f"header.{payload_b64}.signature"

        token_info = PurviewClient._extract_token_info(fake_token)

        assert token_info["tenant_id"] == "test-tenant"
        assert token_info["user_id"] == "test-user"
        assert token_info["client_id"] == "test-client"

    async def test_get_user_info_from_token(self, client: PurviewClient) -> None:
        """Test get_user_info_from_token extracts user info."""
        import base64
        import json

        payload = {"tid": "test-tenant", "oid": "test-user", "idtyp": "user"}
        payload_str = json.dumps(payload)
        payload_bytes = payload_str.encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        fake_token = f"header.{payload_b64}.signature"

        with patch.object(client, "_get_token", return_value=fake_token):
            user_info = await client.get_user_info_from_token(tenant_id="test-tenant")

            assert user_info["tenant_id"] == "test-tenant"
            assert user_info["user_id"] == "test-user"

    @pytest.mark.parametrize(
        "status_code,exception_type",
        [
            (401, PurviewAuthenticationError),
            (403, PurviewAuthenticationError),
            (429, PurviewRateLimitError),
            (400, PurviewRequestError),
            (404, PurviewRequestError),
            (500, PurviewServiceError),
            (502, PurviewServiceError),
        ],
    )
    async def test_post_error_handling(
        self, client: PurviewClient, status_code: int, exception_type: type[Exception]
    ) -> None:
        """Test _post method handles different HTTP errors correctly."""
        from agent_framework_purview._models import ProcessContentResponse

        # Create a valid request
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

        # Mock the HTTP client to return an error
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = status_code
        mock_response.text = "Error message"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        )

        with patch.object(client._client, "post", return_value=mock_response), pytest.raises(exception_type):
            await client._post(
                "https://graph.microsoft.com/v1.0/test",
                request,
                ProcessContentResponse,
                "fake-token",
            )

    async def test_process_content_success(self, client: PurviewClient, mock_credential: MagicMock) -> None:
        """Test process_content method success path."""
        # Create a valid request
        text_content = PurviewTextContent(data="Test message")
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

        # Mock successful response
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "response-123", "protectionScopeState": "notModified"}

        with patch.object(client._client, "post", return_value=mock_response):
            response = await client.process_content(request)

            assert response.id == "response-123"
            assert response.protection_scope_state == "notModified"

    async def test_get_protection_scopes_success(self, client: PurviewClient) -> None:
        """Test get_protection_scopes method success path."""
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        request = ProtectionScopesRequest(
            user_id="user-123", tenant_id="tenant-456", locations=[location], correlation_id="corr-789"
        )

        # Mock successful response
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"scopeIdentifier": "scope-123", "value": []}

        with patch.object(client._client, "post", return_value=mock_response):
            response = await client.get_protection_scopes(request)

            assert response.scope_identifier == "scope-123"
            assert response.scopes == []

    async def test_client_close(self, mock_credential: AsyncMock, settings: PurviewSettings) -> None:
        """Test client properly closes HTTP client."""
        client = PurviewClient(mock_credential, settings)

        with patch.object(client._client, "aclose", new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()

    async def test_post_includes_user_agent(self, client: PurviewClient) -> None:
        """Test _post method includes User-Agent header."""
        from agent_framework_purview._models import ProcessContentResponse

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

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "response-123"}

        with patch.object(client._client, "post", return_value=mock_response) as mock_post:
            await client._post(
                "https://graph.microsoft.com/v1.0/test",
                request,
                ProcessContentResponse,
                "fake-token",
            )

            # Check that User-Agent header was included
            call_args = mock_post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "User-Agent" in headers
            assert headers["User-Agent"]  # Should not be empty
