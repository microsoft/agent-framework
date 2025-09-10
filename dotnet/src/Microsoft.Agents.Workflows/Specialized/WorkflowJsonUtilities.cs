// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Specialized;

internal static partial class WorkflowJsonUtilities
{
    public static WorkflowJsonContext Default { get; } = new();

    [JsonSerializable(typeof(ChatMessage))]
    [JsonSerializable(typeof(List<ChatMessage>))]
    internal sealed partial class WorkflowJsonContext : JsonSerializerContext;

    public static JsonElement SerializeToJson(this List<ChatMessage> messages)
    {
        return JsonSerializer.SerializeToElement(messages, Default.ListChatMessage);
    }

    public static JsonElement SerializeToJson(this IEnumerable<ChatMessage> messages)
        => messages.ToList().SerializeToJson();

    public static List<ChatMessage> DeserializeMessageList(this JsonElement element)
    {
        return element.Deserialize<List<ChatMessage>>(Default.ListChatMessage) ?? [];
    }
}
