// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Agents.AI.Purview.Models.Requests;
using Microsoft.Agents.AI.Purview.Models.Responses;

namespace Microsoft.Agents.AI.Purview.Serialization;

/// <summary>
/// Source generation context for Purview serialization.
/// </summary>
[JsonSerializable(typeof(ProtectionScopesRequest))]
[JsonSerializable(typeof(ProtectionScopesResponse))]
[JsonSerializable(typeof(ProcessContentRequest))]
[JsonSerializable(typeof(ProcessContentResponse))]
[JsonSerializable(typeof(ContentActivitiesRequest))]
[JsonSerializable(typeof(ContentActivitiesResponse))]
[JsonSerializable(typeof(ProtectionScopesCacheKey))]
internal sealed partial class SourceGenerationContext : JsonSerializerContext;

/// <summary>
/// Utility class for Purview serialization settings.
/// </summary>
internal static class PurviewSerializationUtils
{
    /// <summary>
    /// Serialization settings for Purview.
    /// </summary>
    public static JsonSerializerOptions SerializationSettings { get; } = new JsonSerializerOptions
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
        WriteIndented = false,
        AllowTrailingCommas = false,
        DictionaryKeyPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        TypeInfoResolver = SourceGenerationContext.Default,
    };
}
