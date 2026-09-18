// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary><c>output</c>: the final agent response &lt;-&gt; the spec's output payload.</summary>
internal static class OutputCodec
{
    /// <summary>Project the run output: a single plain-text message as a string, else per-message objects.</summary>
    public static JsonNode? ToWire(AgentResponse response)
    {
        var parts = Wire.MessagesToWire(response.Messages);
        if (parts.Count == 1 && parts[0]!["content"] is JsonValue value && value.TryGetValue(out string? text))
        {
            return JsonValue.Create(text);
        }

        return parts;
    }

    /// <summary>Write a transformed <c>output</c> target back into the agent response. Returns whether it changed.</summary>
    /// <remarks>
    /// Mutations happen in place (message contents and the response's message list) so
    /// that persistence deferred behind the run gate — which holds references to the same
    /// message objects — observes the transformed content, never the pre-transform value.
    /// </remarks>
    public static bool WriteBack(AgentResponse response, JsonNode? beforeContent, JsonNode? after)
    {
        if (after is null)
        {
            return false;
        }

        if (after is not JsonObject afterObject)
        {
            throw new AgentHooksWriteBackException("agent-hooks output transform must produce an output object target.");
        }

        var afterContent = afterObject["content"];
        if (Wire.WireEquals(afterContent, beforeContent))
        {
            return false;
        }

        List<ChatMessage> originals = [.. response.Messages];
        if (afterContent is JsonValue value && value.TryGetValue(out string? text))
        {
            if (originals.Count == 1)
            {
                originals[0].Contents = Wire.WireToContents(afterContent, "output");
            }
            else
            {
                ReplaceMessages(response, [new ChatMessage(ChatRole.Assistant, text)]);
            }

            return true;
        }

        if (afterContent is null)
        {
            ReplaceMessages(response, []);
            return true;
        }

        List<JsonObject> beforeList = [.. originals.Select(Wire.MessageToWire)];
        ReplaceMessages(response, Wire.WriteBackMessageList(originals, beforeList, afterContent, "output"));
        return true;
    }

    private static void ReplaceMessages(AgentResponse response, List<ChatMessage> messages)
    {
        response.Messages.Clear();
        foreach (var message in messages)
        {
            response.Messages.Add(message);
        }
    }
}
