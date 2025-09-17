// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.UnitTests;

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    UseStringEnumConverter = true)]
[JsonSerializable(typeof(JsonElement))]
[JsonSerializable(typeof(string))]
internal sealed partial class TestJsonSerializerContext : JsonSerializerContext;
