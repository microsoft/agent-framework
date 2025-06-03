# Copyright (c) Microsoft. All rights reserved.
from typing import Any, Dict, Protocol


class AITool(Protocol):
    """Represents a tool that can be specified to an AI service."""
    name: str
    """The name of the tool."""
    description: str | None = None
    """A description of the tool, suitable for use in describing the purpose to a model."""
    additional_properties: Dict[str, Any] | None = None
    """Additional properties associated with the tool."""
