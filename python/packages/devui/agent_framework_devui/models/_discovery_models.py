# Copyright (c) Microsoft. All rights reserved.

"""Discovery API models for entity information."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
