# Copyright (c) Microsoft. All rights reserved.

from enum import IntEnum


class FeatureIndex(IntEnum):
    """Orchestration-owned feature-usage indexes."""

    SEQUENTIAL = 32
    CONCURRENT = 33
    GROUP_CHAT = 34
    MAGENTIC = 35
    HANDOFF = 36
