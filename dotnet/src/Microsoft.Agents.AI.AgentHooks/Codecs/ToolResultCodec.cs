// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

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
