// Copyright (c) Microsoft. All rights reserved.

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
internal sealed partial class TestJsonSerializerContext : JsonSerializerContext;
