// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI.Agents.Abstractions.UnitTests.Models;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    UseStringEnumConverter = true)]
[JsonSerializable(typeof(AgentRunResponse))]
[JsonSerializable(typeof(AgentRunResponseUpdate))]
[JsonSerializable(typeof(AgentRunOptions))]
[JsonSerializable(typeof(Animal))]
[JsonSerializable(typeof(JsonElement))]
[JsonSerializable(typeof(Dictionary<string, object?>))]
[JsonSerializable(typeof(string[]))]
internal sealed partial class TestJsonSerializerContext : JsonSerializerContext;
