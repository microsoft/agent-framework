# Copyright (c) Microsoft. All rights reserved.

"""Discovery API models for entity information."""

from typing import Any

from pydantic import BaseModel, Field


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

    # Workflow-specific fields (populated only for detailed info requests)
    executors: list[str] | None = None
    workflow_dump: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    input_type_name: str | None = None
    start_executor_id: str | None = None


class DiscoveryResponse(BaseModel):
    """Response model for entity discovery."""

    entities: list[EntityInfo] = Field(default_factory=list)
