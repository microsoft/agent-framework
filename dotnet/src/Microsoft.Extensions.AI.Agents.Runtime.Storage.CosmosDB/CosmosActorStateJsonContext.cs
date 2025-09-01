// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime.Storage.CosmosDB;

/// <summary>
/// Source-generated JSON type information for Cosmos DB actor state documents.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(ActorStateDocument))]
[JsonSerializable(typeof(ActorRootDocument))]
[JsonSerializable(typeof(KeyProjection))]
[JsonSerializable(typeof(KeyProjection[]))]
[JsonSerializable(typeof(JsonElement))]
public sealed partial class CosmosActorStateJsonContext : JsonSerializerContext;
