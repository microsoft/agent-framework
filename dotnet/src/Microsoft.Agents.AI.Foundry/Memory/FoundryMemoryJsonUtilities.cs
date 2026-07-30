// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Provides JSON serialization utilities for the Foundry Memory provider.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal static class FoundryMemoryJsonUtilities
{
    /// <summary>
    /// Gets the default JSON serializer options for Foundry Memory operations.
    /// </summary>
    public static JsonSerializerOptions DefaultOptions { get; } = new JsonSerializerOptions
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
        TypeInfoResolver = FoundryMemoryJsonContext.Default
    };
}

/// <summary>
/// Source-generated JSON serialization context for Foundry Memory types.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.General,
    UseStringEnumConverter = false,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    WriteIndented = false)]
[JsonSerializable(typeof(FoundryMemoryProviderScope))]
[JsonSerializable(typeof(FoundryMemoryProvider.State))]
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
internal partial class FoundryMemoryJsonContext : JsonSerializerContext;
