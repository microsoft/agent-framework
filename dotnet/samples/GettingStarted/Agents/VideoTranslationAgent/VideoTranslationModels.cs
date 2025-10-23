// Copyright (c) Microsoft. All rights reserved.

// This file contains the data models used in the video translation service.

using System;
using System.Text.Json.Serialization;

namespace VideoTranslationAgent;

/// <summary>
/// Base definition for translation input.
/// </summary>
public class TranslationInputBaseDefinition
{
    [JsonPropertyName("speakerCount")]
    public int? SpeakerCount { get; set; }

    [JsonPropertyName("subtitleMaxCharCountPerSegment")]
    public int? SubtitleMaxCharCountPerSegment { get; set; }

    [JsonPropertyName("exportSubtitleInVideo")]
    public bool? ExportSubtitleInVideo { get; set; }
}

/// <summary>
/// WebVTT file definition.
/// </summary>
public class WebvttFileDefinition
{
    [JsonPropertyName("kind")]
    public string? Kind { get; set; }

    [JsonPropertyName("url")]
    public string? Url { get; set; }
}

/// <summary>
/// Translation input definition.
/// </summary>
public class TranslationInputDefinition : TranslationInputBaseDefinition
{
    [JsonPropertyName("sourceLocale")]
    public string? SourceLocale { get; set; }

    [JsonPropertyName("targetLocale")]
    public string? TargetLocale { get; set; }

    [JsonPropertyName("voiceKind")]
    public string? VoiceKind { get; set; }

    [JsonPropertyName("videoFileUrl")]
    public string? VideoFileUrl { get; set; }
}

/// <summary>
/// Base definition for stateless resources.
/// </summary>
public class StatelessResourceBaseDefinition
{
    [JsonPropertyName("id")]
    public string? Id { get; set; }

    [JsonPropertyName("displayName")]
    public string? DisplayName { get; set; }

    [JsonPropertyName("description")]
    public string? Description { get; set; }

    [JsonPropertyName("createdDateTime")]
    public DateTime? CreatedDateTime { get; set; }
}

/// <summary>
/// Base definition for stateful resources.
/// </summary>
public class StatefulResourceBaseDefinition : StatelessResourceBaseDefinition
{
    [JsonPropertyName("status")]
    public string? Status { get; set; }

    [JsonPropertyName("lastActionDateTime")]
    public DateTime? LastActionDateTime { get; set; }
}

/// <summary>
/// Iteration input definition.
/// </summary>
public class IterationInputDefinition : TranslationInputBaseDefinition
{
    [JsonPropertyName("webvttFile")]
    public WebvttFileDefinition? WebvttFile { get; set; }
}

/// <summary>
/// Iteration result definition.
/// </summary>
public class IterationResultDefinition
{
    [JsonPropertyName("translatedVideoFileUrl")]
    public string? TranslatedVideoFileUrl { get; set; }

    [JsonPropertyName("sourceLocaleSubtitleWebvttFileUrl")]
    public string? SourceLocaleSubtitleWebvttFileUrl { get; set; }

    [JsonPropertyName("targetLocaleSubtitleWebvttFileUrl")]
    public string? TargetLocaleSubtitleWebvttFileUrl { get; set; }

    [JsonPropertyName("metadataJsonWebvttFileUrl")]
    public string? MetadataJsonWebvttFileUrl { get; set; }
}

/// <summary>
/// Translation definition.
/// </summary>
public class TranslationDefinition : StatefulResourceBaseDefinition
{
    [JsonPropertyName("input")]
    public TranslationInputDefinition? Input { get; set; }

    [JsonPropertyName("translationFailureReason")]
    public string? TranslationFailureReason { get; set; }
}

/// <summary>
/// Iteration definition.
/// </summary>
public class IterationDefinition : StatefulResourceBaseDefinition
{
    [JsonPropertyName("input")]
    public IterationInputDefinition? Input { get; set; }

    [JsonPropertyName("result")]
    public IterationResultDefinition? Result { get; set; }

    [JsonPropertyName("iterationFailureReason")]
    public string? IterationFailureReason { get; set; }
}

/// <summary>
/// Operation definition.
/// </summary>
public class OperationDefinition
{
    [JsonPropertyName("id")]
    public string? Id { get; set; }

    [JsonPropertyName("status")]
    public string? Status { get; set; }

    [JsonPropertyName("createdDateTime")]
    public DateTime? CreatedDateTime { get; set; }

    [JsonPropertyName("lastActionDateTime")]
    public DateTime? LastActionDateTime { get; set; }
}

/// <summary>
/// Paged translation definition.
/// </summary>
public class PagedTranslationDefinition
{
    [JsonPropertyName("value")]
    public TranslationDefinition[]? Value { get; set; }

    [JsonPropertyName("nextLink")]
    public string? NextLink { get; set; }
}

/// <summary>
/// Paged iteration definition.
/// </summary>
public class PagedIterationDefinition
{
    [JsonPropertyName("value")]
    public IterationDefinition[]? Value { get; set; }

    [JsonPropertyName("nextLink")]
    public string? NextLink { get; set; }
}
