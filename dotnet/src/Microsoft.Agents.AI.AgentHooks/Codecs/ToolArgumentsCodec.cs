// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Nodes;

namespace Microsoft.Agents.AI.AgentHooks;

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
