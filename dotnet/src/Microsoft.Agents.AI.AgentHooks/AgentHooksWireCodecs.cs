// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// A transform verdict could not be converted back into the native framework value.
/// </summary>
/// <remarks>
/// Thrown (and deliberately never caught by this package) so an unappliable transform
/// fails the run closed instead of silently proceeding with the untransformed value.
/// </remarks>
internal sealed class AgentHooksWriteBackException : InvalidOperationException
{
    public AgentHooksWriteBackException()
    {
    }

    public AgentHooksWriteBackException(string message)
        : base(message)
    {
    }

    public AgentHooksWriteBackException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

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

/// <summary>
/// <c>post_model_call</c>: the assembled chat response &lt;-&gt; the spec's response payload.
/// </summary>
/// <remarks>
/// Host-executed tool calls ride <c>tool_calls</c> (they drive the function seam);
/// service-executed (informational-only) tool calls are part of the model response itself
/// and are surfaced in <c>content</c> so hosted tool activity is interceptable here even
/// though the function seam never sees it.
/// </remarks>
internal static class ModelResponseCodec
{
    private static bool IsHostExecutedCall(AIContent content) =>
        content is FunctionCallContent { InformationalOnly: false };

    /// <summary>Project the response content (everything except host-executed tool calls).</summary>
    public static JsonNode? ContentToWire(IList<ChatMessage> messages)
    {
        var parts = new JsonArray();
        foreach (var message in messages)
        {
            List<AIContent> visible = [.. message.Contents.Where(content => !IsHostExecutedCall(content))];
            if (visible.Count == 0)
            {
                continue;
            }

            parts.Add(new JsonObject
            {
                ["role"] = Wire.RoleString(message.Role),
                ["content"] = Wire.ContentsToWire(visible),
            });
        }

        if (parts.Count == 0)
        {
            return null;
        }

        if (parts.Count == 1 && parts[0]!["content"] is JsonValue value && value.TryGetValue(out string? text))
        {
            return JsonValue.Create(text);
        }

        return parts;
    }

    /// <summary>Project the host-executed tool calls (the ones the function seam will bracket).</summary>
    public static JsonArray ToolCallsToWire(IList<ChatMessage> messages)
    {
        var calls = new JsonArray();
        foreach (var message in messages)
        {
            foreach (var content in message.Contents)
            {
                if (content is FunctionCallContent { InformationalOnly: false } call)
                {
                    calls.Add(new JsonObject
                    {
                        ["id"] = call.CallId ?? string.Empty,
                        ["name"] = call.Name ?? string.Empty,
                        ["args"] = Wire.ArgumentsToWire(call.Arguments),
                    });
                }
            }
        }

        return calls;
    }

    public static JsonObject ToWire(ChatResponse response) => new()
    {
        ["content"] = ContentToWire(response.Messages),
        ["tool_calls"] = ToolCallsToWire(response.Messages),
        ["finish_reason"] = Wire.FinishReasonString(response.FinishReason),
    };

    /// <summary>Write a transformed <c>post_model_call</c> target back into the chat response. Returns whether it changed.</summary>
    public static bool WriteBack(ChatResponse response, JsonObject before, JsonNode? after)
    {
        if (after is null || Wire.WireEquals(after, before))
        {
            return false;
        }

        if (after is not JsonObject afterObject)
        {
            throw new AgentHooksWriteBackException("agent-hooks post_model_call transform must produce a response object.");
        }

        bool changed = false;
        var afterFinish = afterObject["finish_reason"];
        if (!Wire.WireEquals(afterFinish, before["finish_reason"]))
        {
            if ((afterFinish as JsonValue)?.TryGetValue(out string? finish) is not true)
            {
                throw new AgentHooksWriteBackException("agent-hooks post_model_call transform must keep finish_reason a string.");
            }

            response.FinishReason = new ChatFinishReason(finish!);
            changed = true;
        }

        var afterCalls = afterObject["tool_calls"];
        if (!Wire.WireEquals(afterCalls, before["tool_calls"]))
        {
            changed |= WriteBackToolCalls(response, afterCalls);
        }

        var afterContent = afterObject["content"];
        if (!Wire.WireEquals(afterContent, before["content"]))
        {
            WriteBackContent(response, afterContent);
            changed = true;
        }

        return changed;
    }

    /// <summary>Reconcile transformed <c>tool_calls</c> with the response's function-call contents.</summary>
    private static bool WriteBackToolCalls(ChatResponse response, JsonNode? afterCalls)
    {
        if (afterCalls is not JsonArray callsArray)
        {
            throw new AgentHooksWriteBackException("agent-hooks post_model_call transform must keep tool_calls a list.");
        }

        // Validate the complete shape up front, before any reconciliation: every call —
        // kept or added — must carry a non-empty string id, a non-empty string name and
        // object-valued args, and ids must be unique (duplicates would silently collapse
        // during reconciliation). An invalid shape fails closed rather than becoming a
        // malformed native call.
        List<(string Id, string Name, JsonObject Args)> wireCalls = [];
        Dictionary<string, (string Name, JsonObject Args)> callsById = [];
        foreach (var item in callsArray)
        {
            if (item is not JsonObject callObject)
            {
                throw new AgentHooksWriteBackException("agent-hooks post_model_call transform produced a tool call that is not an object.");
            }

            if ((callObject["id"] as JsonValue)?.TryGetValue(out string? id) is not true || string.IsNullOrEmpty(id))
            {
                throw new AgentHooksWriteBackException(
                    "agent-hooks post_model_call transform must give each tool call a non-empty string id.");
            }

            if ((callObject["name"] as JsonValue)?.TryGetValue(out string? name) is not true || string.IsNullOrEmpty(name))
            {
                throw new AgentHooksWriteBackException(
                    "agent-hooks post_model_call transform must keep each tool call's name a non-empty string.");
            }

            if (callObject["args"] is not JsonObject args)
            {
                throw new AgentHooksWriteBackException(
                    "agent-hooks post_model_call transform must keep each tool call's args an object.");
            }

            if (!callsById.TryAdd(id!, (name!, args)))
            {
                throw new AgentHooksWriteBackException(
                    "agent-hooks post_model_call transform produced two tool calls with the same id.");
            }

            wireCalls.Add((id!, name!, args));
        }

        HashSet<string> consumed = [];
        bool changed = false;
        foreach (var message in response.Messages)
        {
            List<AIContent> kept = [];
            foreach (var content in message.Contents)
            {
                if (content is not FunctionCallContent { InformationalOnly: false } call)
                {
                    kept.Add(content);
                    continue;
                }

                if (!callsById.TryGetValue(call.CallId ?? string.Empty, out var wire))
                {
                    changed = true; // the transform dropped this tool call
                    continue;
                }

                consumed.Add(call.CallId ?? string.Empty);
                if (wire.Name != call.Name || !Wire.WireEquals(Wire.ArgumentsToWire(call.Arguments), wire.Args))
                {
                    kept.Add(new FunctionCallContent(call.CallId ?? string.Empty, wire.Name, WireArgsToNative(wire.Args)));
                    changed = true;
                }
                else
                {
                    kept.Add(content);
                }
            }

            if (kept.Count != message.Contents.Count || !kept.SequenceEqual(message.Contents))
            {
                message.Contents = kept;
            }
        }

        List<AIContent> added = [];
        foreach (var (id, name, args) in wireCalls)
        {
            if (!consumed.Contains(id))
            {
                added.Add(new FunctionCallContent(id, name, WireArgsToNative(args)));
                changed = true;
            }
        }

        if (added.Count > 0)
        {
            var target = response.Messages.LastOrDefault(m => Wire.RoleString(m.Role) == "assistant");
            if (target is not null)
            {
                target.Contents = [.. target.Contents, .. added];
            }
            else
            {
                response.Messages.Add(new ChatMessage(ChatRole.Assistant, added));
            }
        }

        return changed;
    }

    private static Dictionary<string, object?> WireArgsToNative(JsonObject wireArgs)
    {
        Dictionary<string, object?> native = [];
        foreach (var (key, value) in wireArgs)
        {
            native[key] = value?.DeepClone();
        }

        return native;
    }

    /// <summary>Rebuild the response's visible content from a transformed <c>response.content</c> value, preserving host-executed tool calls.</summary>
    private static void WriteBackContent(ChatResponse response, JsonNode? afterContent)
    {
        List<AIContent> calls = [.. response.Messages
            .SelectMany(message => message.Contents)
            .Where(IsHostExecutedCall)];

        List<ChatMessage> baseMessages;
        if (afterContent is null)
        {
            baseMessages = [];
        }
        else if (afterContent is JsonValue value && value.TryGetValue(out string? text))
        {
            baseMessages = [new ChatMessage(ChatRole.Assistant, text)];
        }
        else if (afterContent is JsonArray array)
        {
            baseMessages = [];
            foreach (var item in array)
            {
                if (item is not JsonObject wireMessage || !wireMessage.ContainsKey("content"))
                {
                    throw new AgentHooksWriteBackException("agent-hooks post_model_call transform produced content without role/content.");
                }

                string role = (wireMessage["role"] as JsonValue)?.GetValue<string>() ?? "assistant";
                baseMessages.Add(new ChatMessage(new ChatRole(role), Wire.WireToContents(wireMessage["content"], "post_model_call")));
            }
        }
        else
        {
            throw new AgentHooksWriteBackException("agent-hooks post_model_call transform produced unsupported content.");
        }

        if (calls.Count > 0)
        {
            if (baseMessages.Count > 0 && Wire.RoleString(baseMessages[^1].Role) == "assistant")
            {
                baseMessages[^1].Contents = [.. baseMessages[^1].Contents, .. calls];
            }
            else
            {
                baseMessages.Add(new ChatMessage(ChatRole.Assistant, calls));
            }
        }

        // Mutate the response's message list in place: deferred persistence callbacks and
        // outer layers hold references to this list, and must observe the transformed content.
        response.Messages.Clear();
        foreach (var message in baseMessages)
        {
            response.Messages.Add(message);
        }
    }
}

/// <summary><c>pre_tool_call</c>: the native tool arguments &lt;-&gt; the spec's args object.</summary>
internal static class ToolArgumentsCodec
{
    public static JsonObject ToWire(IDictionary<string, object?>? arguments) => Wire.ArgumentsToWire(arguments);

    /// <summary>
    /// Merge a transformed <c>args</c> target back onto the native arguments.
    /// </summary>
    /// <remarks>
    /// Returns the effective wire args, and sets <paramref name="merged"/> to the merged
    /// native arguments (or <see langword="null"/> when untouched). Only the keys the
    /// transform actually changed (or added/removed) are taken from the wire value;
    /// untouched keys keep their original native values, so non-JSON-native argument
    /// values survive a transform that did not touch them.
    /// </remarks>
    public static JsonObject WriteBack(
        IDictionary<string, object?> arguments, JsonObject before, JsonNode? after, out Dictionary<string, object?>? merged)
    {
        if (after is not JsonObject effective)
        {
            throw new AgentHooksWriteBackException("agent-hooks pre_tool_call transform must produce an arguments object.");
        }

        if (Wire.WireEquals(effective, before))
        {
            merged = null;
            return effective;
        }

        merged = [];
        foreach (var (key, value) in arguments)
        {
            if (effective.ContainsKey(key))
            {
                merged[key] = value;
            }
        }

        foreach (var (key, value) in effective)
        {
            if (!before.ContainsKey(key) || !Wire.WireEquals(before[key], value))
            {
                merged[key] = value?.DeepClone();
            }
        }

        return effective;
    }
}

/// <summary><c>post_tool_call</c>: the native tool result &lt;-&gt; the spec's result value.</summary>
internal static class ToolResultCodec
{
    /// <summary>
    /// Project a tool result faithfully, unwrapping framework content containers: text
    /// content projects as its text, function-result content projects as its canonical
    /// result value, and any other content projects as its full content object.
    /// </summary>
    public static JsonNode? ToWire(object? value)
    {
        switch (value)
        {
            case null:
                return null;
            case string s:
                return JsonValue.Create(s);
            case TextContent text:
                return JsonValue.Create(text.Text ?? string.Empty);
            case FunctionResultContent { Result: not null } result:
                return ToWire(result.Result);
            case AIContent content:
                return JsonSerializer.SerializeToNode(content, typeof(AIContent), Wire.JsonOptions);
            case IList<AIContent> { Count: 1 } single:
                // The canonical single-content result projects as the content's value
                // itself, matching what the model sees.
                return ToWire(single[0]);
            case IEnumerable<AIContent> contents:
                var array = new JsonArray();
                foreach (var item in contents)
                {
                    array.Add(ToWire(item));
                }

                return array;
            default:
                return Wire.ValueToWire(value);
        }
    }

    /// <summary>
    /// Convert a transformed <c>post_tool_call</c> value back into the native result
    /// shape. A wire value the interceptors left untouched maps back to the untouched
    /// native result; text-content wrappers are preserved when shape-compatible;
    /// otherwise the transformed wire value becomes the result as-is (the function
    /// invocation layer serializes JSON values faithfully).
    /// </summary>
    public static object? WriteBack(object? original, JsonNode? before, JsonNode? after)
    {
        if (Wire.WireEquals(after, before))
        {
            return original;
        }

        if (original is string && after is JsonValue afterString && afterString.TryGetValue(out string? text))
        {
            return text;
        }

        if (original is TextContent && after is JsonValue afterText && afterText.TryGetValue(out string? content))
        {
            return new TextContent(content);
        }

        if (original is IList<AIContent> { Count: 1 } single && single[0] is TextContent &&
            after is JsonValue afterValue && afterValue.TryGetValue(out string? singleText))
        {
            return new List<AIContent> { new TextContent(singleText) };
        }

        return after?.DeepClone();
    }
}

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
