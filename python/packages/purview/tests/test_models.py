# Copyright (c) Microsoft. All rights reserved.

"""Tests for Purview models and serialization."""

from agent_framework_purview._models import (
    Activity,
    ActivityMetadata,
    ContentToProcess,
    DeviceMetadata,
    DlpAction,
    DlpActionInfo,
    IntegratedAppMetadata,
    OperatingSystemSpecifications,
    PolicyLocation,
    ProcessContentRequest,
    ProcessContentResponse,
    ProcessConversationMetadata,
    ProtectedAppMetadata,
    ProtectionScopeActivities,
    ProtectionScopesRequest,
    ProtectionScopesResponse,
    PurviewTextContent,
    RestrictionAction,
)
from agent_framework_purview.models.enums import deserialize_flag, serialize_flag


class TestEnums:
    """Test enumeration types and flag operations."""

    def test_activity_enum_values(self) -> None:
        """Test Activity enum has expected values."""
        assert Activity.UPLOAD_TEXT == "uploadText"
        assert Activity.UPLOAD_FILE == "uploadFile"
        assert Activity.DOWNLOAD_TEXT == "downloadText"
        assert Activity.DOWNLOAD_FILE == "downloadFile"

    def test_dlp_action_enum_values(self) -> None:
        """Test DlpAction enum has expected values."""
        assert DlpAction.BLOCK_ACCESS == "blockAccess"
        assert DlpAction.OTHER == "other"

    def test_restriction_action_enum_values(self) -> None:
        """Test RestrictionAction enum has expected values."""
        assert RestrictionAction.BLOCK == "block"
        assert RestrictionAction.OTHER == "other"

    def test_protection_scope_activities_flag(self) -> None:
        """Test ProtectionScopeActivities flag enum."""
        # Test individual flags
        assert ProtectionScopeActivities.UPLOAD_TEXT.value == 1
        assert ProtectionScopeActivities.UPLOAD_FILE.value == 2
        assert ProtectionScopeActivities.DOWNLOAD_TEXT.value == 4
        assert ProtectionScopeActivities.DOWNLOAD_FILE.value == 8

        # Test combining flags
        combined = ProtectionScopeActivities.UPLOAD_TEXT | ProtectionScopeActivities.UPLOAD_FILE
        assert combined.value == 3
        assert ProtectionScopeActivities.UPLOAD_TEXT in combined
        assert ProtectionScopeActivities.UPLOAD_FILE in combined

    def test_deserialize_flag_with_string(self) -> None:
        """Test deserializing flag from comma-separated string."""
        mapping = {
            "uploadText": ProtectionScopeActivities.UPLOAD_TEXT,
            "uploadFile": ProtectionScopeActivities.UPLOAD_FILE,
        }

        result = deserialize_flag("uploadText,uploadFile", mapping, ProtectionScopeActivities)
        assert result is not None
        assert ProtectionScopeActivities.UPLOAD_TEXT in result
        assert ProtectionScopeActivities.UPLOAD_FILE in result

    def test_deserialize_flag_with_none(self) -> None:
        """Test deserializing None returns None."""
        mapping = {"uploadText": ProtectionScopeActivities.UPLOAD_TEXT}
        result = deserialize_flag(None, mapping, ProtectionScopeActivities)
        assert result is None

    def test_deserialize_flag_with_int(self) -> None:
        """Test deserializing flag from integer."""
        mapping = {"uploadText": ProtectionScopeActivities.UPLOAD_TEXT}
        result = deserialize_flag(3, mapping, ProtectionScopeActivities)
        assert result is not None
        assert result.value == 3

    def test_serialize_flag_with_none(self) -> None:
        """Test serializing None returns None."""
        result = serialize_flag(None, [])
        assert result is None

    def test_serialize_flag_with_zero(self) -> None:
        """Test serializing zero flag returns 'none'."""
        result = serialize_flag(ProtectionScopeActivities.NONE, [])
        assert result == "none"

    def test_serialize_flag_with_values(self) -> None:
        """Test serializing flag with values."""
        flag = ProtectionScopeActivities.UPLOAD_TEXT | ProtectionScopeActivities.UPLOAD_FILE
        ordered = [
            ("uploadText", ProtectionScopeActivities.UPLOAD_TEXT),
            ("uploadFile", ProtectionScopeActivities.UPLOAD_FILE),
        ]
        result = serialize_flag(flag, ordered)
        assert result == "uploadText,uploadFile"


class TestSimpleModels:
    """Test simple value object models."""

    def test_policy_location_creation(self) -> None:
        """Test PolicyLocation model creation."""
        location = PolicyLocation(**{
            "@odata.type": "microsoft.graph.policyLocationApplication",
            "value": "test-app-id",
        })
        assert location.data_type == "microsoft.graph.policyLocationApplication"
        assert location.value == "test-app-id"

    def test_activity_metadata_creation(self) -> None:
        """Test ActivityMetadata creation."""
        metadata = ActivityMetadata(activity=Activity.UPLOAD_TEXT)
        assert metadata.activity == Activity.UPLOAD_TEXT

    def test_device_metadata_creation(self) -> None:
        """Test DeviceMetadata creation with OS specifications."""
        os_specs = OperatingSystemSpecifications(operatingSystemPlatform="Windows", operatingSystemVersion="10.0")
        device = DeviceMetadata(ipAddress="192.168.1.1", operatingSystemSpecifications=os_specs)

        assert device.ip_address == "192.168.1.1"
        assert device.operating_system_specifications is not None
        assert device.operating_system_specifications.operating_system_platform == "Windows"

    def test_integrated_app_metadata_creation(self) -> None:
        """Test IntegratedAppMetadata creation."""
        app = IntegratedAppMetadata(name="Test App", version="1.0.0")
        assert app.name == "Test App"
        assert app.version == "1.0.0"

    def test_protected_app_metadata_creation(self) -> None:
        """Test ProtectedAppMetadata creation."""
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        app = ProtectedAppMetadata(name="Protected App", version="2.0", applicationLocation=location)

        assert app.name == "Protected App"
        assert app.version == "2.0"
        assert app.application_location.value == "app-id"

    def test_dlp_action_info_creation(self) -> None:
        """Test DlpActionInfo creation."""
        action_info = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)

        assert action_info.action == DlpAction.BLOCK_ACCESS
        assert action_info.restriction_action == RestrictionAction.BLOCK


class TestContentModels:
    """Test content and metadata models."""

    def test_purview_text_content_creation(self) -> None:
        """Test PurviewTextContent creation."""
        content = PurviewTextContent(data="Hello, world!")
        assert content.data == "Hello, world!"
        assert content.data_type == "microsoft.graph.textContent"

    def test_process_conversation_metadata_creation(self) -> None:
        """Test ProcessConversationMetadata creation."""
        text_content = PurviewTextContent(data="Test message")
        metadata = ProcessConversationMetadata(**{
            "@odata.type": "microsoft.graph.processConversationMetadata",
            "identifier": "msg-123",
            "content": text_content,
            "name": "Test Message",
            "isTruncated": False,
            "correlationId": "corr-123",
        })

        assert metadata.identifier == "msg-123"
        assert metadata.name == "Test Message"
        assert metadata.is_truncated is False
        assert metadata.correlation_id == "corr-123"
        assert isinstance(metadata.content, PurviewTextContent)

    def test_content_to_process_creation(self) -> None:
        """Test ContentToProcess creation."""
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

        assert len(content.content_entries) == 1
        assert content.activity_metadata.activity == Activity.UPLOAD_TEXT
        assert content.device_metadata is not None
        assert content.integrated_app_metadata.name == "App"
        assert content.protected_app_metadata.name == "Protected"


class TestRequestModels:
    """Test request models."""

    def test_process_content_request_creation(self) -> None:
        """Test ProcessContentRequest creation."""
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
            "correlation_id": "corr-789",
            "process_inline": True,
        })

        assert request.content_to_process is not None
        assert request.user_id == "user-123"
        assert request.tenant_id == "tenant-456"
        assert request.correlation_id == "corr-789"
        assert request.process_inline is True

    def test_protection_scopes_request_creation(self) -> None:
        """Test ProtectionScopesRequest creation."""
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})
        device_meta = DeviceMetadata(ipAddress="192.168.1.1")
        integrated_app = IntegratedAppMetadata(name="App", version="1.0")

        request = ProtectionScopesRequest(
            user_id="user-123",
            tenant_id="tenant-456",
            activities=ProtectionScopeActivities.UPLOAD_TEXT,
            locations=[location],
            deviceMetadata=device_meta,
            integratedAppMetadata=integrated_app,
            correlation_id="corr-789",
        )

        assert request.user_id == "user-123"
        assert request.tenant_id == "tenant-456"
        # After Pydantic processing, the enum value becomes the underlying int value
        assert request.activities == ProtectionScopeActivities.UPLOAD_TEXT.value
        assert len(request.locations) == 1
        assert request.device_metadata is not None
        assert request.integrated_app_metadata is not None

    def test_protection_scopes_request_serialization(self) -> None:
        """Test ProtectionScopesRequest serializes correctly."""
        location = PolicyLocation(**{"@odata.type": "microsoft.graph.policyLocationApplication", "value": "app-id"})

        request = ProtectionScopesRequest(
            user_id="user-123",
            tenant_id="tenant-456",
            activities=ProtectionScopeActivities.UPLOAD_TEXT | ProtectionScopeActivities.UPLOAD_FILE,
            locations=[location],
        )

        # Test model_dump with aliases
        dumped = request.model_dump(by_alias=True, exclude_none=True, mode="json")

        assert "activities" in dumped
        # Activities should be serialized as comma-separated string
        assert isinstance(dumped["activities"], str)
        assert "uploadText" in dumped["activities"]


class TestResponseModels:
    """Test response models."""

    def test_process_content_response_creation(self) -> None:
        """Test ProcessContentResponse creation."""
        action_info = DlpActionInfo(action=DlpAction.BLOCK_ACCESS, restrictionAction=RestrictionAction.BLOCK)

        response = ProcessContentResponse(**{
            "id": "response-123",
            "protectionScopeState": "modified",
            "policyActions": [action_info],
        })

        assert response.id == "response-123"
        assert response.protection_scope_state == "modified"
        assert len(response.policy_actions) == 1
        assert response.policy_actions[0].action == DlpAction.BLOCK_ACCESS

    def test_protection_scopes_response_creation(self) -> None:
        """Test ProtectionScopesResponse creation."""
        response = ProtectionScopesResponse(**{"scopeIdentifier": "scope-123", "value": []})

        assert response.scope_identifier == "scope-123"
        assert response.scopes == []

    def test_process_content_response_with_errors(self) -> None:
        """Test ProcessContentResponse with processing errors."""
        from agent_framework_purview._models import ProcessingError

        error = ProcessingError(message="Test error occurred")
        response = ProcessContentResponse(**{"processingErrors": [error]})

        assert response.processing_errors is not None
        assert len(response.processing_errors) == 1
        assert response.processing_errors[0].message == "Test error occurred"


class TestModelSerialization:
    """Test model serialization and deserialization."""

    def test_content_to_process_serialization(self) -> None:
        """Test ContentToProcess can be serialized with aliases."""
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

        # Serialize with aliases
        dumped = content.model_dump(by_alias=True, exclude_none=True, mode="json")

        # Check that camelCase aliases are used
        assert "contentEntries" in dumped
        assert "activityMetadata" in dumped
        assert "deviceMetadata" in dumped
        assert "integratedAppMetadata" in dumped
        assert "protectedAppMetadata" in dumped

    def test_process_content_request_excludes_private_fields(self) -> None:
        """Test ProcessContentRequest excludes private fields when serializing."""
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
            "correlation_id": "corr-789",
        })

        # Serialize with aliases
        dumped = request.model_dump(by_alias=True, exclude_none=True, mode="json")

        # Check that excluded fields are not present
        assert "user_id" not in dumped
        assert "tenant_id" not in dumped
        assert "correlation_id" not in dumped

        # Check that content is present
        assert "contentToProcess" in dumped
