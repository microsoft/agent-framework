# Copyright (c) Microsoft. All rights reserved.

"""Request model definitions for Purview policy evaluation APIs."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .content import ContentToProcess
from .enums import (
    _PROTECTION_SCOPE_ACTIVITIES_MAP,
    _PROTECTION_SCOPE_ACTIVITIES_SERIALIZE_ORDER,
    PolicyPivotProperty,
    ProtectionScopeActivities,
    deserialize_flag,
    serialize_flag,
)
from .simples import (
    DeviceMetadata,
    IntegratedAppMetadata,
    PolicyLocation,
)


class ProcessContentRequest(BaseModel):
    """Request body for submitting conversation content for inline policy processing."""

    model_config = ConfigDict(populate_by_name=True)
    content_to_process: ContentToProcess = Field(alias="contentToProcess")
    user_id: str = Field(exclude=True)
    tenant_id: str = Field(exclude=True)
    correlation_id: str | None = Field(default=None, exclude=True)
    process_inline: bool | None = Field(default=None, exclude=True)


class ProtectionScopesRequest(BaseModel):
    """Request for retrieving protection scopes based on user, device, and app context."""

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)
    user_id: str = Field(exclude=True)
    tenant_id: str = Field(exclude=True)
    activities: ProtectionScopeActivities | None = Field(default=None, alias="activities")
    locations: list[PolicyLocation] | None = Field(default=None, alias="locations")
    pivot_on: PolicyPivotProperty | None = Field(default=None, alias="pivotOn")
    device_metadata: DeviceMetadata | None = Field(default=None, alias="deviceMetadata")
    integrated_app_metadata: IntegratedAppMetadata | None = Field(default=None, alias="integratedAppMetadata")
    correlation_id: str | None = Field(default=None, exclude=True)
    scope_identifier: str | None = Field(default=None, exclude=True)

    @field_validator("activities", mode="before")
    @classmethod
    def _parse_flag(cls, v: object) -> ProtectionScopeActivities | None:  # pragma: no cover
        return deserialize_flag(v, _PROTECTION_SCOPE_ACTIVITIES_MAP, ProtectionScopeActivities)

    @field_serializer("activities", when_used="json")
    def _serialize_flag(self, v: ProtectionScopeActivities | None) -> str | None:  # pragma: no cover
        return serialize_flag(v, _PROTECTION_SCOPE_ACTIVITIES_SERIALIZE_ORDER) if v is not None else None


class ContentActivitiesRequest(BaseModel):
    """Request for retrieving policy activity outcomes for specific content."""

    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: str(uuid4()), alias="id")
    user_id: str = Field(alias="userId")
    tenant_id: str = Field(exclude=True)
    scope_identifier: str | None = Field(default=None, alias="scopeIdentifier")
    content_to_process: ContentToProcess = Field(alias="contentMetadata")
    correlation_id: str | None = Field(default=None, exclude=True)
