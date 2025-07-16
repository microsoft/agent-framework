// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace HelloHttpApi.ApiService;

public sealed class ChatClientAgentRunRequest
{
    [JsonPropertyName("messages")]
    public List<ChatMessage> Messages { get; set; } = [];
}
