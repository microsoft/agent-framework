# Copyright (c) Microsoft. All rights reserved.

"""Type definitions for Cua integration."""

from typing import Any, Literal, TypedDict


class CuaStep(TypedDict, total=False):
    """Represents a single step in Cua agent execution."""

    step: int
    action: dict[str, Any]
    result: dict[str, Any]
    success: bool
    error: str | None


class CuaResult(TypedDict, total=False):
    """Result from Cua agent execution."""

    output: list[dict[str, Any]]
    steps: list[CuaStep]
    usage: dict[str, Any]
    stopped: bool
    reason: str | None


CuaModelId = str
"""
Model identifier for Cua agent.

Supports 100+ model configurations:
- OpenAI: "openai/gpt-4o", "openai/gpt-4o-mini"
- Anthropic: "anthropic/claude-3-5-sonnet-20241022"
- OpenCUA: "huggingface-local/ByteDance/OpenCUA-7B"
- InternVL: "huggingface-local/OpenGVLab/InternVL2-8B"
- UI-Tars: "huggingface-local/ByteDance-Seed/UI-TARS-1.5-7B"
- GLM: "huggingface-local/THUDM/glm-4v-9b"
- Composite: "grounding_model+planning_model"

Examples:
    >>> model = "anthropic/claude-3-5-sonnet-20241022"
    >>> model = "openai/gpt-4o"
    >>> model = "huggingface-local/ByteDance/OpenCUA-7B+openai/gpt-4o"
"""

CuaProviderType = Literal["lume", "docker", "cloud", "lumier", "winsandbox"]
"""
VM provider type for Cua computer.

- lume: Native macOS/Linux VMs (high performance)
- docker: Docker containers (cross-platform)
- cloud: Cloud sandbox (managed service)
- lumier: Docker-based Lume interface
- winsandbox: Windows Sandbox
"""

CuaOSType = Literal["macos", "linux", "windows"]
"""Operating system type for Cua computer."""


__all__ = [
    "CuaModelId",
    "CuaOSType",
    "CuaProviderType",
    "CuaResult",
    "CuaStep",
]
