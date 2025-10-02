# Copyright (c) Microsoft. All rights reserved.

"""Content model definitions for Purview policy evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import BaseModel, ConfigDict, Field

from .simples import (
    AccessedResourceDetails,
    ActivityMetadata,
    AiAgentInfo,
    AiInteractionPlugin,
    DeviceMetadata,
    IntegratedAppMetadata,
    ProtectedAppMetadata,
)


class GraphDataTypeBase(BaseModel):
    """Base model for Microsoft Graph typed objects.

    Provides a shared ``@odata.type`` field used when serializing to service requests.
    """

    model_config = ConfigDict(populate_by_name=True)
    data_type: str = Field(alias="@odata.type")


class ContentBase(GraphDataTypeBase):
    """Base type for content payloads (text or binary)."""

    # Intentionally empty; acts as a polymorphic base.
    pass


class PurviewTextContent(ContentBase):
    """UTF-8 textual content to evaluate or process."""

    data_type: str = Field(default="microsoft.graph.textContent", alias="@odata.type")
    data: str = Field(alias="data")


class PurviewBinaryContent(ContentBase):
    """Binary content (e.g. file bytes) to evaluate or process."""

    data_type: str = Field(default="microsoft.graph.binaryContent", alias="@odata.type")
    data: bytes = Field(alias="data")


class ProcessConversationMetadata(GraphDataTypeBase):
    """Envelope describing a single message (prompt or response) within a conversation.

    Includes linkage/correlation data plus content and plugin/resource metadata. This
    mirrors the shape expected by the Purview policy evaluation service.
    """

    identifier: str = Field(alias="identifier")
    content: PurviewTextContent | PurviewBinaryContent | ContentBase = Field(alias="content")
    name: str = Field(alias="name")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    sequence_number: int | None = Field(default=None, alias="sequenceNumber")
    length: int | None = Field(default=None, alias="length")
    is_truncated: bool = Field(alias="isTruncated")
    created_date_time: datetime | None = Field(default=None, alias="createdDateTime")
    modified_date_time: datetime | None = Field(default=None, alias="modifiedDateTime")

    parent_message_id: str | None = Field(default=None, alias="parentMessageId")
    accessed_resources: list[AccessedResourceDetails] | None = Field(default=None, alias="accessedResources_v2")
    plugins: list[AiInteractionPlugin] | None = Field(default=None, alias="plugins")
    agents: list[AiAgentInfo] | None = Field(default=None, alias="agents")


class ContentToProcess(BaseModel):
    """Container aggregating messages and associated context for a policy check."""

    model_config = ConfigDict(populate_by_name=True)
    content_entries: list[ProcessConversationMetadata] = Field(alias="contentEntries")
    activity_metadata: ActivityMetadata = Field(alias="activityMetadata")
    device_metadata: DeviceMetadata = Field(alias="deviceMetadata")
    integrated_app_metadata: IntegratedAppMetadata = Field(alias="integratedAppMetadata")
    protected_app_metadata: ProtectedAppMetadata = Field(alias="protectedAppMetadata")
