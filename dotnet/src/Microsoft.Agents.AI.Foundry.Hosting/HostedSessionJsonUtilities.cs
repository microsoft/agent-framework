// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// JSON serialization utilities for hosted session identity types.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
internal static class HostedSessionJsonUtilities
{
    /// <summary>
    /// Default JSON serializer options for hosted session state.
    /// </summary>
    public static JsonSerializerOptions DefaultOptions { get; } = new JsonSerializerOptions
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
        TypeInfoResolver = HostedSessionJsonContext.Default
    };
}

/// <summary>
/// Source-generated JSON serialization context for hosted session identity types.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.General,
    UseStringEnumConverter = false,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    WriteIndented = false)]
[JsonSerializable(typeof(HostedSessionContext))]
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
internal partial class HostedSessionJsonContext : JsonSerializerContext;
