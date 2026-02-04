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
[JsonSerializable(typeof(AgentResponse))]
[JsonSerializable(typeof(AgentResponseUpdate))]
[JsonSerializable(typeof(AgentRunOptions))]
[JsonSerializable(typeof(Animal))]
[JsonSerializable(typeof(JsonElement))]
[JsonSerializable(typeof(Dictionary<string, object?>))]
[JsonSerializable(typeof(string[]))]
[JsonSerializable(typeof(int))]
[JsonSerializable(typeof(InMemoryAgentSession.InMemoryAgentSessionState))]
[JsonSerializable(typeof(ServiceIdAgentSession.ServiceIdAgentSessionState))]
[JsonSerializable(typeof(ServiceIdAgentSessionTests.EmptyObject))]
[JsonSerializable(typeof(InMemoryChatHistoryProviderTests.TestAIContent))]
internal sealed partial class TestJsonSerializerContext : JsonSerializerContext;
