// Copyright (c) Microsoft. All rights reserved.

// This file contains the enums used in the video translation service.

namespace VideoTranslationAgent;

/// <summary>
/// Voice kind for video translation.
/// </summary>
public enum VoiceKind
{
    PlatformVoice,
    PersonalVoice
}

/// <summary>
/// Status of an operation.
/// </summary>
public enum OperationStatus
{
    NotStarted,
    Running,
    Succeeded,
    Failed,
    Canceled
}

/// <summary>
/// State of a resource.
/// </summary>
public enum OneApiState
{
    NotStarted,
    Running,
    Succeeded,
    Failed
}

/// <summary>
/// Type of WebVTT file.
/// </summary>
public enum WebvttFileKind
{
    SourceLocaleSubtitle,
    TargetLocaleSubtitle,
    MetadataJson
}
