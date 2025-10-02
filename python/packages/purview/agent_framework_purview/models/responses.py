# Copyright (c) Microsoft. All rights reserved.

"""Response model definitions for Purview policy evaluation APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .enums import (
    _PROTECTION_SCOPE_ACTIVITIES_MAP,
    _PROTECTION_SCOPE_ACTIVITIES_SERIALIZE_ORDER,
    ExecutionMode,
    ProtectionScopeActivities,
    ProtectionScopeState,
    deserialize_flag,
    serialize_flag,
)
from .simples import DlpActionInfo, PolicyLocation


class ErrorDetails(BaseModel):
    """Minimal error information returned when a specific policy operation fails."""

    code: str | None = Field(default=None, alias="code")
    message: str | None = Field(default=None, alias="message")


class ProcessingError(BaseModel):
    """Represents a content processing error returned by the service."""

    message: str | None = None


class ProcessContentResponse(BaseModel):
    """Response from submitting content for processing / evaluation."""

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)
    id: str | None = None
    protection_scope_state: ProtectionScopeState | None = Field(default=None, alias="protectionScopeState")
    policy_actions: list[DlpActionInfo] | None = Field(default=None, alias="policyActions")
    processing_errors: list[ProcessingError] | None = Field(default=None, alias="processingErrors")


class PolicyScope(BaseModel):
    """A single protection scope with evaluated activities, locations and actions."""

    model_config = ConfigDict(populate_by_name=True)
    activities: ProtectionScopeActivities | None = Field(default=None, alias="activities")
    locations: list[PolicyLocation] | None = Field(default=None, alias="locations")
    policy_actions: list[DlpActionInfo] | None = Field(default=None, alias="policyActions")
    execution_mode: ExecutionMode | None = Field(default=None, alias="executionMode")

    @field_validator("activities", mode="before")
    @classmethod
    def _parse_flag(cls, v: object) -> ProtectionScopeActivities | None:  # pragma: no cover
        return deserialize_flag(v, _PROTECTION_SCOPE_ACTIVITIES_MAP, ProtectionScopeActivities)

    @field_serializer("activities", when_used="json")
    def _serialize_flag(self, v: ProtectionScopeActivities | None) -> str | None:  # pragma: no cover
        return serialize_flag(v, _PROTECTION_SCOPE_ACTIVITIES_SERIALIZE_ORDER) if v is not None else None


class ProtectionScopesResponse(BaseModel):
    """Response containing one or more computed policy scopes for the caller context."""

    model_config = ConfigDict(populate_by_name=True)
    scope_identifier: str | None = Field(default=None, alias="scopeIdentifier")
    scopes: list[PolicyScope] | None = Field(default=None, alias="value")


class ContentActivitiesResponse(BaseModel):
    """Response with aggregated policy evaluation results for specific content items."""

    model_config = ConfigDict(populate_by_name=True)
    status_code: int | None = Field(default=None, exclude=True)
    error: ErrorDetails | None = Field(default=None, alias="error")
