# Copyright (c) Microsoft. All rights reserved.

"""Discovery API models for entity information."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EnvVarRequirement(BaseModel):
    """Environment variable requirement for an entity."""

    name: str
    description: str
    required: bool = True
    example: str | None = None


class EntityInfo(BaseModel):
    """Entity information for discovery and detailed views."""

    # Always present (core entity data)
    id: str
    type: str  # "agent", "workflow"
    name: str
    description: str | None = None
    framework: str
    tools: list[str | dict[str, Any]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Source information
    source: str = "directory"  # "directory" or "in_memory"

    # Environment variable requirements
    required_env_vars: list[EnvVarRequirement] | None = None

    # Deployment support
    deployment_supported: bool = False  # Whether entity can be deployed
    deployment_reason: str | None = None  # Explanation of why/why not entity can be deployed

    # Agent-specific fields (optional, populated when available)
    instructions: str | None = None
    model_id: str | None = None
    chat_client_type: str | None = None
    context_providers: list[str] | None = None
    middleware: list[str] | None = None

    # Workflow-specific fields (populated only for detailed info requests)
    executors: list[str] | None = None
    workflow_dump: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    input_type_name: str | None = None
    start_executor_id: str | None = None


class DiscoveryResponse(BaseModel):
    """Response model for entity discovery."""

    entities: list[EntityInfo] = Field(default_factory=list)


# ============================================================================
# Deployment Models
# ============================================================================


class DeploymentConfig(BaseModel):
    """Configuration for deploying an entity."""

    entity_id: str = Field(description="Entity ID to deploy")
    resource_group: str = Field(description="Azure resource group name")
    app_name: str = Field(description="Azure Container App name")
    region: str = Field(default="eastus", description="Azure region")
    ui_mode: str = Field(default="user", description="UI mode (user or developer)")
    ui_enabled: bool = Field(default=True, description="Whether to enable web interface")
    stream: bool = Field(default=True, description="Stream deployment events")

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, v: str) -> str:
        """Validate Azure Container App name format.

        Azure Container App names must:
        - Be 3-32 characters long
        - Contain only lowercase letters, numbers, and hyphens
        - Start with a lowercase letter
        - End with a lowercase letter or number
        - Not contain consecutive hyphens
        """
        if not v:
            raise ValueError("app_name cannot be empty")

        if len(v) < 3 or len(v) > 32:
            raise ValueError("app_name must be between 3 and 32 characters")

        if not re.match(r"^[a-z][a-z0-9-]*[a-z0-9]$", v):
            raise ValueError(
                "app_name must start with a lowercase letter, "
                "end with a letter or number, and contain only lowercase letters, numbers, and hyphens"
            )

        if "--" in v:
            raise ValueError("app_name cannot contain consecutive hyphens")

        return v

    @field_validator("resource_group")
    @classmethod
    def validate_resource_group(cls, v: str) -> str:
        """Validate Azure resource group name format.

        Azure resource group names must:
        - Be 1-90 characters long
        - Contain only alphanumeric, underscore, parentheses, hyphen, period (except at end)
        - Not end with a period
        """
        if not v:
            raise ValueError("resource_group cannot be empty")

        if len(v) > 90:
            raise ValueError("resource_group must be 90 characters or less")

        if not re.match(r"^[a-zA-Z0-9._()-]+$", v):
            raise ValueError(
                "resource_group can only contain alphanumeric characters, "
                "underscores, hyphens, periods, and parentheses"
            )

        if v.endswith("."):
            raise ValueError("resource_group cannot end with a period")

        return v

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        """Validate Azure region format.

        Validates that the region string is a reasonable format.
        Does not validate against the full list of Azure regions (which changes).
        """
        if not v:
            raise ValueError("region cannot be empty")

        if len(v) > 50:
            raise ValueError("region name too long")

        # Azure regions are typically lowercase with no spaces (e.g., eastus, westeurope)
        if not re.match(r"^[a-z0-9]+$", v):
            raise ValueError("region must contain only lowercase letters and numbers (e.g., eastus, westeurope)")

        return v

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, v: str) -> str:
        """Validate entity_id format to prevent injection attacks."""
        if not v:
            raise ValueError("entity_id cannot be empty")

        if len(v) > 256:
            raise ValueError("entity_id too long")

        # Allow alphanumeric, hyphens, underscores, and periods
        if not re.match(r"^[a-zA-Z0-9._-]+$", v):
            raise ValueError("entity_id contains invalid characters")

        return v

    @field_validator("ui_mode")
    @classmethod
    def validate_ui_mode(cls, v: str) -> str:
        """Validate ui_mode is one of the allowed values."""
        if v not in ("user", "developer"):
            raise ValueError("ui_mode must be 'user' or 'developer'")

        return v


class DeploymentEvent(BaseModel):
    """Real-time deployment event (SSE)."""

    type: str = Field(description="Event type (e.g., deploy.validating, deploy.building)")
    message: str = Field(description="Human-readable message")
    url: str | None = Field(default=None, description="Deployment URL (on completion)")
    auth_token: str | None = Field(default=None, description="Auth token (on completion, shown once)")


class Deployment(BaseModel):
    """Deployment record."""

    id: str = Field(description="Deployment ID (UUID)")
    entity_id: str = Field(description="Entity ID that was deployed")
    resource_group: str = Field(description="Azure resource group")
    app_name: str = Field(description="Azure Container App name")
    region: str = Field(description="Azure region")
    url: str = Field(description="Deployment URL")
    status: str = Field(description="Deployment status (deploying, deployed, failed)")
    created_at: str = Field(description="ISO 8601 timestamp")
    error: str | None = Field(default=None, description="Error message if failed")
