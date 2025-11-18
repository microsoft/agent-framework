// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DevUI.Entities;

/// <summary>
/// JSON serialization context for entity-related types.
/// Enables AOT-compatible JSON serialization using source generators.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(EntityInfo))]
[JsonSerializable(typeof(DiscoveryResponse))]
[JsonSerializable(typeof(MetaResponse))]
[JsonSerializable(typeof(EnvVarRequirement))]
[JsonSerializable(typeof(List<EntityInfo>))]
[JsonSerializable(typeof(List<Dictionary<string, JsonElement>>))]
[JsonSerializable(typeof(List<Dictionary<string, string>>))]
[JsonSerializable(typeof(Dictionary<string, JsonElement>))]
[JsonSerializable(typeof(Dictionary<string, Dictionary<string, string>>))]
[JsonSerializable(typeof(Dictionary<string, string>))]
[JsonSerializable(typeof(JsonElement))]
[JsonSerializable(typeof(string))]
[JsonSerializable(typeof(int))]
[ExcludeFromCodeCoverage]
internal sealed partial class EntitiesJsonContext : JsonSerializerContext;
