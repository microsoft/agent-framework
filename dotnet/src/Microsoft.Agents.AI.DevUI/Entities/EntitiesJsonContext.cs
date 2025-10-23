﻿// Copyright (c) Microsoft. All rights reserved.

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
[JsonSerializable(typeof(EnvVarRequirement))]
[JsonSerializable(typeof(List<EntityInfo>))]
[JsonSerializable(typeof(List<JsonElement>))]
[JsonSerializable(typeof(Dictionary<string, JsonElement>))]
[JsonSerializable(typeof(JsonElement))]
[ExcludeFromCodeCoverage]
internal sealed partial class EntitiesJsonContext : JsonSerializerContext;
