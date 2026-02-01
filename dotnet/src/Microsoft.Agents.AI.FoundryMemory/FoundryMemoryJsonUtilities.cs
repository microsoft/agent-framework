// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.FoundryMemory.Core.Models;

namespace Microsoft.Agents.AI.FoundryMemory;

/// <summary>
/// Provides JSON serialization utilities for the Foundry Memory provider.
/// </summary>
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
[JsonSerializable(typeof(FoundryMemoryProvider.FoundryMemoryState))]
[JsonSerializable(typeof(SearchMemoriesRequest))]
[JsonSerializable(typeof(SearchMemoriesResponse))]
[JsonSerializable(typeof(SearchMemoriesOptions))]
[JsonSerializable(typeof(UpdateMemoriesRequest))]
[JsonSerializable(typeof(UpdateMemoriesResponse))]
[JsonSerializable(typeof(UpdateMemoriesError))]
[JsonSerializable(typeof(DeleteScopeRequest))]
[JsonSerializable(typeof(CreateMemoryStoreRequest))]
[JsonSerializable(typeof(MemoryStoreDefinitionRequest))]
[JsonSerializable(typeof(MemoryStoreResponse))]
[JsonSerializable(typeof(MemoryInputMessage))]
[JsonSerializable(typeof(MemoryInputMessage[]))]
[JsonSerializable(typeof(MemorySearchResult))]
[JsonSerializable(typeof(MemorySearchResult[]))]
[JsonSerializable(typeof(MemoryItem))]
internal partial class FoundryMemoryJsonContext : JsonSerializerContext;
