// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Abstractions.UnitTests.Models;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

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
[JsonSerializable(typeof(int))]
[JsonSerializable(typeof(InMemoryAgentThread.InMemoryAgentThreadState))]
[JsonSerializable(typeof(ServiceIdAgentThread.ServiceIdAgentThreadState))]
[JsonSerializable(typeof(ServiceIdAgentThreadTests.EmptyObject))]
[JsonSerializable(typeof(InMemoryChatMessageStoreTests.TestAIContent))]
internal sealed partial class TestJsonSerializerContext : JsonSerializerContext;
