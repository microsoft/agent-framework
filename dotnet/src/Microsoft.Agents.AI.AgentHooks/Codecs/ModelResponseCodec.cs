// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

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
