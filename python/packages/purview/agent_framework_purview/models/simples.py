# Copyright (c) Microsoft. All rights reserved.

"""Simple value object model definitions for Purview policy evaluation APIs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import Activity, DlpAction, RestrictionAction


class PolicyLocation(BaseModel):
    """Represents a location (tenant, site, repository, etc.) within a protection scope."""

    model_config = ConfigDict(populate_by_name=True)
    data_type: str | None = Field(None, alias="@odata.type")
    value: str | None = None


class ActivityMetadata(BaseModel):
    """Metadata describing the user/agent activity being evaluated."""

    model_config = ConfigDict(populate_by_name=True)
    activity: Activity = Field(alias="activity")


class DeviceMetadata(BaseModel):
    """Information about the device originating the activity."""

    model_config = ConfigDict(populate_by_name=True)
    ip_address: str | None = Field(default=None, alias="ipAddress")
    operating_system_specifications: OperatingSystemSpecifications | None = Field(
        default=None, alias="operatingSystemSpecifications"
    )


class OperatingSystemSpecifications(BaseModel):
    """Details about the operating system for the originating device."""

    model_config = ConfigDict(populate_by_name=True)
    operating_system_platform: str | None = Field(default=None, alias="operatingSystemPlatform")
    operating_system_version: str | None = Field(default=None, alias="operatingSystemVersion")


class IntegratedAppMetadata(BaseModel):
    """Metadata for the integrating application (e.g. host application)."""

    model_config = ConfigDict(populate_by_name=True)
    name: str | None = None
    version: str | None = None


class ProtectedAppMetadata(BaseModel):
    """Metadata for the protected application context used during evaluation."""

    model_config = ConfigDict(populate_by_name=True)
    name: str | None = None
    version: str | None = None
    application_location: PolicyLocation = Field(alias="applicationLocation")


class DlpActionInfo(BaseModel):
    """Information about a DLP action and any associated restriction action."""

    model_config = ConfigDict(populate_by_name=True)
    action: DlpAction | None = Field(default=None, alias="action")
    restriction_action: RestrictionAction | None = Field(default=None, alias="restrictionAction")


class AccessedResourceDetails(BaseModel):
    """Information about a resource accessed within the conversation context."""

    model_config = ConfigDict(populate_by_name=True)
    identifier: str | None = Field(default=None, alias="identifier")
    name: str | None = Field(default=None, alias="name")
    url: str | None = Field(default=None, alias="url")
    label_id: str | None = Field(default=None, alias="labelId")
    access_type: str | None = Field(default=None, alias="accessType")
    status: str | None = Field(default=None, alias="status")
    is_cross_prompt_injection_detected: bool | None = Field(default=None, alias="isCrossPromptInjectionDetected")


class AiInteractionPlugin(BaseModel):
    """A plugin utilized during an AI interaction (e.g. tool invocation)."""

    model_config = ConfigDict(populate_by_name=True)
    identifier: str | None = Field(default=None, alias="identifier")
    name: str | None = Field(default=None, alias="name")
    version: str | None = Field(default=None, alias="version")


class AiAgentInfo(BaseModel):
    """Information about an AI agent participating in a conversation."""

    model_config = ConfigDict(populate_by_name=True)
    identifier: str | None = Field(default=None, alias="identifier")
    name: str | None = Field(default=None, alias="name")
    version: str | None = Field(default=None, alias="version")
