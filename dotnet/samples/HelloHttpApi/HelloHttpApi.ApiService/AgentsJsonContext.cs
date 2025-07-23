// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using HelloHttpApi.ApiService;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
/// <summary>
/// Source-generated JSON type information for use by all Agents implementations.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(ChatMessage))]
[JsonSerializable(typeof(List<ChatMessage>))]
[JsonSerializable(typeof(ChatClientAgentThread))]
[JsonSerializable(typeof(ChatClientAgentRunRequest))]
[JsonSerializable(typeof(AgentRunResponseUpdate))]
internal sealed partial class AgentsJsonContext : JsonSerializerContext;
