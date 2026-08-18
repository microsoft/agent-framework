// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary><c>pre_model_call</c>: the outgoing request messages &lt;-&gt; the spec's messages list.</summary>
internal static class ModelRequestCodec
{
    public static JsonArray ToWire(IReadOnlyList<ChatMessage> messages) => Wire.MessagesToWire(messages);

    /// <summary>Return the transformed message list, or <see langword="null"/> when the target is untouched.</summary>
    public static List<ChatMessage>? WriteBack(IReadOnlyList<ChatMessage> messages, JsonArray before, JsonNode? after)
    {
        if (Wire.WireEquals(after, before))
        {
            return null;
        }

        List<JsonObject> beforeList = [.. before.Cast<JsonObject>()];
        return Wire.WriteBackMessageList(messages, beforeList, after, "pre_model_call");
    }
}
