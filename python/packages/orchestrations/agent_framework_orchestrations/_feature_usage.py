# Copyright (c) Microsoft. All rights reserved.

from enum import IntEnum


class FeatureIndex(IntEnum):
    """Orchestration-owned feature-usage indexes."""

    ORCHESTRATION_SEQUENTIAL = 32
    ORCHESTRATION_CONCURRENT = 33
    ORCHESTRATION_GROUP_CHAT = 34
    ORCHESTRATION_MAGENTIC = 35
    ORCHESTRATION_HANDOFF = 36
