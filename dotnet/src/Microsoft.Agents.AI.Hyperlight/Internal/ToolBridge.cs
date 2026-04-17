// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using HyperlightSandbox.Api;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hyperlight.Internal;

/// <summary>
/// Bridges an <see cref="AIFunction"/> to the
/// <see cref="Sandbox.RegisterToolAsync(string, Func{string, Task{string}})"/>
/// overload so the guest can invoke .NET tools via <c>call_tool(...)</c>.
/// </summary>
internal static class ToolBridge
{
    /// <summary>
    /// Registers every <paramref name="tools"/> entry against the provided
    /// <paramref name="sandbox"/> as a raw JSON-in / JSON-out async tool.
    /// </summary>
    public static void RegisterAll(Sandbox sandbox, IReadOnlyList<AIFunction> tools)
    {
        foreach (var tool in tools)
        {
            RegisterOne(sandbox, tool);
        }
    }

    private static void RegisterOne(Sandbox sandbox, AIFunction tool)
    {
        var unwrapped = Unwrap(tool);
        sandbox.RegisterToolAsync(
            unwrapped.Name,
            async (string argsJson) => await InvokeAsync(unwrapped, argsJson).ConfigureAwait(false));
    }

    internal static async Task<string> InvokeAsync(AIFunction tool, string argsJson)
    {
        try
        {
            var arguments = ParseArguments(argsJson);
            var result = await tool.InvokeAsync(new AIFunctionArguments(arguments)).ConfigureAwait(false);
            return SerializeResult(result);
        }
#pragma warning disable CA1031 // Catch all: we must surface every failure as a JSON error to the guest rather than crash the FFI boundary.
        catch (Exception ex)
#pragma warning restore CA1031
        {
            return JsonSerializer.Serialize(new { error = ex.Message });
        }
    }

    internal static IDictionary<string, object?> ParseArguments(string argsJson)
    {
        if (string.IsNullOrWhiteSpace(argsJson))
        {
            return new Dictionary<string, object?>(StringComparer.Ordinal);
        }

        var node = JsonNode.Parse(argsJson);
        if (node is not JsonObject obj)
        {
            throw new ArgumentException(
                "Tool arguments must be a JSON object.",
                nameof(argsJson));
        }

        var result = new Dictionary<string, object?>(StringComparer.Ordinal);
        foreach (var kvp in obj)
        {
            result[kvp.Key] = kvp.Value;
        }

        return result;
    }

    private static string SerializeResult(object? result)
    {
        switch (result)
        {
            case null:
                return "null";
            case string s:
                return JsonSerializer.Serialize(s);
            case JsonElement element:
                return element.GetRawText();
            case JsonNode node:
                return node.ToJsonString();
            default:
                return JsonSerializer.Serialize(result);
        }
    }

    /// <summary>
    /// Returns the underlying <see cref="AIFunction"/> removing any
    /// <see cref="ApprovalRequiredAIFunction"/> wrapping. The guest calls
    /// tools directly and approval is enforced at the <c>execute_code</c>
    /// layer.
    /// </summary>
    internal static AIFunction Unwrap(AIFunction tool)
    {
        while (tool is ApprovalRequiredAIFunction wrapper)
        {
            tool = wrapper.InnerFunction;
        }

        return tool;
    }
}
