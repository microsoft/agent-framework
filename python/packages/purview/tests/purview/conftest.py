# Copyright (c) Microsoft. All rights reserved.
"""Shared pytest fixtures for Purview tests."""

import pytest

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
    PurviewTextContent,
)


@pytest.fixture
def content_to_process_factory():
    """Factory fixture to create ContentToProcess objects with test data."""

    def _create_content(text: str = "Test") -> ContentToProcess:
        text_content = PurviewTextContent(data=text)
        metadata = ProcessConversationMetadata(
            identifier="msg-1",
            content=text_content,
            name="Test",
            is_truncated=False,
        )
        activity_meta = ActivityMetadata(activity=Activity.UPLOAD_TEXT)
        device_meta = DeviceMetadata(
            operating_system_specifications=OperatingSystemSpecifications(
                operating_system_platform="Windows", operating_system_version="10"
            )
        )
        integrated_app = IntegratedAppMetadata(name="App", version="1.0")
        location = PolicyLocation(data_type="microsoft.graph.policyLocationApplication", value="app-id")
        protected_app = ProtectedAppMetadata(name="Protected", version="1.0", application_location=location)

        return ContentToProcess(
            content_entries=[metadata],
            activity_metadata=activity_meta,
            device_metadata=device_meta,
            integrated_app_metadata=integrated_app,
            protected_app_metadata=protected_app,
        )

    return _create_content


@pytest.fixture
def process_content_request_factory(content_to_process_factory):
    """Factory fixture to create ProcessContentRequest objects with test data."""

    def _create_request(
        text: str = "Test", user_id: str = "user-123", tenant_id: str = "tenant-456"
    ) -> ProcessContentRequest:
        content = content_to_process_factory(text)
        return ProcessContentRequest(
            content_to_process=content,
            user_id=user_id,
            tenant_id=tenant_id,
        )

    return _create_request
