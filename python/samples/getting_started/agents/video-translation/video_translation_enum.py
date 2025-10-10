# Copyright (c) Microsoft. All rights reserved.

from enum import Enum


class VoiceKind(str, Enum):
    PlatformVoice = "PlatformVoice"
    PersonalVoice = "PersonalVoice"


class Region(str, Enum):
    eastus = "eastus"
    westus = "westus"


class OneApiState(str, Enum):
    NotStarted = "NotStarted"
    Running = "Running"
    Succeeded = "Succeeded"
    Failed = "Failed"


class OperationStatus(str, Enum):
    NotStarted = "NotStarted"
    Running = "Running"
    Succeeded = "Succeeded"
    Failed = "Failed"
    Canceled = "Canceled"


class WebvttFileKind(str, Enum):
    SourceLocaleSubtitle = "SourceLocaleSubtitle"
    TargetLocaleSubtitle = "TargetLocaleSubtitle"
    MetadataJson = "MetadataJson"
