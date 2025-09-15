# Copyright (c) Microsoft. All rights reserved.

"""Discovery API models for entity information."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class EntityInfo(BaseModel):
    """Entity information for discovery and detailed views."""

    # Always present (core entity data)
    id: str
    type: str  # "agent", "workflow"
    name: str
    description: Optional[str] = None
    framework: str
    tools: Optional[List[Union[str, Dict[str, Any]]]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Workflow-specific fields (populated only for detailed info requests)
    executors: Optional[List[str]] = None
    workflow_dump: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None
    input_type_name: Optional[str] = None
    start_executor_id: Optional[str] = None


class DiscoveryResponse(BaseModel):
    """Response model for entity discovery."""

    entities: List[EntityInfo] = Field(default_factory=list)
