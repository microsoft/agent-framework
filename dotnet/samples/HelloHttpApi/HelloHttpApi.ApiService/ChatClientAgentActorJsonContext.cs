// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace HelloHttpApi.ApiService;

/// <summary>
/// Source-generated JSON type information for use by ChatClientAgentActor.
/// </summary>
[JsonSourceGenerationOptions(
    JsonSerializerDefaults.Web,
    UseStringEnumConverter = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    WriteIndented = false)]
[JsonSerializable(typeof(ChatClientAgentRunRequest))]
internal sealed partial class ChatClientAgentActorJsonContext : JsonSerializerContext;
