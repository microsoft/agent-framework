// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary><c>input</c>: the run's input messages &lt;-&gt; the spec's input payload.</summary>
internal static class InputCodec
{
    /// <summary>Project one input message with the spec's input role mapping.</summary>
    public static JsonObject MessageToWire(ChatMessage message) => new()
    {
        ["role"] = Wire.InputRole(message.Role),
        ["content"] = Wire.ContentsToWire(message.Contents),
    };

    /// <summary>
    /// Project run input per the spec's <c>input</c> payload schema: a single plain-text
    /// message projects as its content string (so string-matching perimeter guards fire);
    /// multi-message or rich input projects as a list of per-message objects.
    /// </summary>
    public static JsonObject ToWire(IReadOnlyList<ChatMessage> messages)
    {
        if (messages.Count == 1)
        {
            return new JsonObject
            {
                ["content"] = Wire.ContentsToWire(messages[0].Contents),
                ["role"] = Wire.InputRole(messages[0].Role),
            };
        }

        var content = new JsonArray();
        foreach (var message in messages)
        {
            content.Add(MessageToWire(message));
        }

        return new JsonObject { ["content"] = content, ["role"] = "user" };
    }

    /// <summary>Write a transformed <c>input</c> target back into the run's message list.</summary>
    public static void WriteBack(List<ChatMessage> messages, JsonObject before, JsonNode? after)
    {
        if (after is null || Wire.WireEquals(after, before))
        {
            return;
        }

        if (after is not JsonObject afterObject)
        {
            throw new AgentHooksWriteBackException("agent-hooks input transform must produce an input object target.");
        }

        var afterRole = afterObject["role"];
        if (!Wire.WireEquals(afterRole, before["role"]))
        {
            // The role field is per-message only for single-message input; for
            // multi-message input the top-level role is synthetic and a transform
            // against it is ambiguous.
            if (messages.Count != 1 || (afterRole as JsonValue)?.TryGetValue(out string? newRole) is not true)
            {
                throw new AgentHooksWriteBackException(
                    "agent-hooks input transform changed the input role in a way that cannot be written back.");
            }

            messages[0].Role = new ChatRole(newRole!);
        }

        var afterContent = afterObject["content"];
        if (Wire.WireEquals(afterContent, before["content"]))
        {
            return;
        }

        if (messages.Count == 1 && !Wire.LooksLikeMessageObjects(afterContent))
        {
            messages[0].Contents = Wire.WireToContents(afterContent, "input");
            return;
        }

        List<JsonObject> beforeList = [.. messages.Select(MessageToWire)];
        var rebuilt = Wire.WriteBackMessageList([.. messages], beforeList, afterContent, "input");
        messages.Clear();
        messages.AddRange(rebuilt);
    }
}
