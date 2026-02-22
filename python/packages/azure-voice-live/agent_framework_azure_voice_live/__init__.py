# Copyright (c) Microsoft. All rights reserved.

"""Azure Voice Live integration for Microsoft Agent Framework.

This package provides real-time voice conversation capabilities using Azure Voice Live SDK.
"""

from ._types import AudioContent, VoiceOptions
from ._voice_live_agent import VoiceLiveAgent
from ._voice_live_session import VoiceLiveSession

__all__ = [
    "VoiceLiveAgent",
    "VoiceLiveSession",
    "AudioContent",
    "VoiceOptions",
]

__version__ = "0.1.0"
