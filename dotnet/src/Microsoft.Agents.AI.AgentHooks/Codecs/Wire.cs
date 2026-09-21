// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Wire building blocks shared by the per-point codecs (framework values &lt;-&gt; AGENT-HOOKS wire JSON).
/// </summary>
/// <remarks>
/// One codec per interception point owns both directions of the wire conversion:
/// <c>ToWire</c> projects the native framework value into the spec's payload, and
/// <c>WriteBack</c> converts the (possibly transformed) wire target back into the native
/// value. Every <c>WriteBack</c> implements the same rule exactly once per point: a wire
/// value the interceptors left untouched maps back to the untouched native value — only
/// genuine transforms modify native state, and an untranslatable transform throws
/// <see cref="AgentHooksWriteBackException"/> (fail closed) rather than being dropped.
/// </remarks>
internal static class Wire
{
    /// <summary>The serializer options used for all content projections.</summary>
    public static JsonSerializerOptions JsonOptions { get; } = AIJsonUtilities.DefaultOptions;

    public static bool WireEquals(JsonNode? left, JsonNode? right) => JsonNode.DeepEquals(left, right);

    public static string RoleString(ChatRole? role)
    {
        var value = role?.Value;
        return string.IsNullOrEmpty(value) ? "user" : value!;
    }

    /// <summary>Map a framework role onto the spec's input role enum (user | system | external).</summary>
    public static string InputRole(ChatRole? role)
    {
        var value = RoleString(role);
        return value is "user" or "system" ? value : "external";
    }

    public static string FinishReasonString(ChatFinishReason? finishReason)
    {
        var value = finishReason?.Value;
        return string.IsNullOrEmpty(value) ? "stop" : value!;
    }

    /// <summary>Project message contents faithfully: plain text as a string, rich content as content objects.</summary>
    public static JsonNode? ContentsToWire(IList<AIContent> contents)
    {
        if (contents.Count == 1 && contents[0] is TextContent text)
        {
            return JsonValue.Create(text.Text ?? string.Empty);
        }

        var array = new JsonArray();
        foreach (var content in contents)
        {
            array.Add(JsonSerializer.SerializeToNode(content, typeof(AIContent), JsonOptions));
        }

        return array;
    }

    public static JsonObject MessageToWire(ChatMessage message) => new()
    {
        ["role"] = RoleString(message.Role),
        ["content"] = ContentsToWire(message.Contents),
    };

    public static JsonArray MessagesToWire(IEnumerable<ChatMessage> messages)
    {
        var array = new JsonArray();
        foreach (var message in messages)
        {
            array.Add(MessageToWire(message));
        }

        return array;
    }

    /// <summary>Decode a transformed wire content value back into framework <see cref="AIContent"/> objects.</summary>
    public static List<AIContent> WireToContents(JsonNode? value, string point)
    {
        if (value is null)
        {
            return [];
        }

        if (value is JsonValue jsonValue && jsonValue.TryGetValue(out string? s))
        {
            return [new TextContent(s)];
        }

        List<JsonNode?> items = value switch
        {
            JsonObject o => [o],
            JsonArray a => [.. a],
            _ => throw new AgentHooksWriteBackException($"agent-hooks {point} transform produced an unsupported content value type."),
        };

        List<AIContent> contents = [];
        foreach (var item in items)
        {
            if (item is JsonValue itemValue && itemValue.TryGetValue(out string? itemText))
            {
                contents.Add(new TextContent(itemText));
                continue;
            }

            if (item is JsonObject itemObject && itemObject.ContainsKey("$type"))
            {
                try
                {
                    var content = JsonSerializer.Deserialize<AIContent>(itemObject, JsonOptions);
                    if (content is not null)
                    {
                        contents.Add(content);
                        continue;
                    }
                }
                catch (Exception exception) when (exception is JsonException or NotSupportedException)
                {
                    throw new AgentHooksWriteBackException($"agent-hooks {point} transform produced an undecodable content item.");
                }
            }

            throw new AgentHooksWriteBackException($"agent-hooks {point} transform produced an unsupported content item.");
        }

        return contents;
    }

    public static bool LooksLikeMessageObjects(JsonNode? value) =>
        value is JsonArray array && array.Count > 0 &&
        array.All(item => item is JsonObject o && o.ContainsKey("content"));

    /// <summary>
    /// Convert a transformed wire message list back into framework messages.
    /// </summary>
    /// <remarks>
    /// The transformed list is authoritative. Entries are matched to original messages by
    /// projection identity rather than list position, so a removal or insertion in the
    /// middle does not shift content onto the wrong original:
    /// <list type="bullet">
    /// <item><description>An entry equal to an (unconsumed) original's projection reuses that
    /// original untouched; originals skipped over were removed by the transform.</description></item>
    /// <item><description>A changed entry mutates the next unconsumed original in place only when
    /// that original's projection is not preserved later in the transformed list (i.e. it was
    /// modified, not shifted) and its role is unchanged.</description></item>
    /// <item><description>Anything else (insertions, role changes) becomes a new <see cref="ChatMessage"/>.</description></item>
    /// </list>
    /// </remarks>
    public static List<ChatMessage> WriteBackMessageList(
        IReadOnlyList<ChatMessage> originals, IReadOnlyList<JsonObject> before, JsonNode? after, string point)
    {
        if (after is not JsonArray afterArray)
        {
            throw new AgentHooksWriteBackException($"agent-hooks {point} transform must produce a list of messages.");
        }

        List<JsonObject> afterItems = [];
        foreach (var item in afterArray)
        {
            if (item is not JsonObject itemObject || !itemObject.ContainsKey("content"))
            {
                throw new AgentHooksWriteBackException($"agent-hooks {point} transform produced a message without role/content.");
            }

            afterItems.Add(itemObject);
        }

        List<ChatMessage> result = [];
        int cursor = 0;
        for (int index = 0; index < afterItems.Count; index++)
        {
            var item = afterItems[index];
            int? matchIndex = null;
            for (int position = cursor; position < originals.Count; position++)
            {
                if (WireEquals(before[position], item))
                {
                    matchIndex = position;
                    break;
                }
            }

            if (matchIndex is int match)
            {
                result.Add(originals[match]);
                cursor = match + 1;
                continue;
            }

            if (cursor < originals.Count)
            {
                var candidateProjection = before[cursor];
                bool preservedLater = afterItems.Skip(index + 1).Any(later => WireEquals(later, candidateProjection));
                string role = (item["role"] as JsonValue)?.GetValue<string>() ?? "user";
                if (!preservedLater && role == (candidateProjection["role"] as JsonValue)?.GetValue<string>())
                {
                    var message = originals[cursor];
                    cursor++;
                    message.Contents = WireToContents(item["content"], point);
                    result.Add(message);
                    continue;
                }
            }

            string newRole = (item["role"] as JsonValue)?.GetValue<string>() ?? "user";
            result.Add(new ChatMessage(new ChatRole(newRole), WireToContents(item["content"], point)));
        }

        return result;
    }

    /// <summary>Project tool-call arguments as the spec's <c>args</c> object.</summary>
    public static JsonObject ArgumentsToWire(IDictionary<string, object?>? arguments)
    {
        var result = new JsonObject();
        if (arguments is not null)
        {
            foreach (var (key, value) in arguments)
            {
                result[key] = ValueToWire(value);
            }
        }

        return result;
    }

    /// <summary>Project one runtime value into wire JSON, never throwing (repr fallback, matching the Python feature's make_json_safe).</summary>
    public static JsonNode? ValueToWire(object? value)
    {
        if (value is null)
        {
            return null;
        }

        if (value is JsonNode node)
        {
            return node.DeepClone();
        }

        try
        {
            return JsonSerializer.SerializeToNode(value, value.GetType(), JsonOptions);
        }
        catch (Exception exception) when (exception is JsonException or NotSupportedException or InvalidOperationException)
        {
            return JsonValue.Create(value.ToString());
        }
    }

    public static JsonObject? UsageToWire(UsageDetails? usage)
    {
        if (usage is null)
        {
            return null;
        }

        var result = new JsonObject();
        if (usage.InputTokenCount is long input)
        {
            result["input_token_count"] = input;
        }

        if (usage.OutputTokenCount is long output)
        {
            result["output_token_count"] = output;
        }

        if (usage.TotalTokenCount is long total)
        {
            result["total_token_count"] = total;
        }

        if (usage.AdditionalCounts is not null)
        {
            foreach (var (key, count) in usage.AdditionalCounts)
            {
                result[key] = count;
            }
        }

        return result.Count > 0 ? result : null;
    }
}
