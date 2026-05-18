// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Base class for tool call formatters that produce human-readable display strings
/// for <see cref="FunctionCallContent"/> items shown in the console.
/// </summary>
public abstract class ToolCallFormatter
{
    /// <summary>
    /// Returns <see langword="true"/> if this formatter can handle the given function call.
    /// </summary>
    /// <param name="call">The function call content to check.</param>
    /// <returns><see langword="true"/> if this formatter should be used; otherwise <see langword="false"/>.</returns>
    public abstract bool CanFormat(FunctionCallContent call);

    /// <summary>
    /// Returns the detail portion of the formatted output for the given tool call,
    /// or <see langword="null"/> if only the tool name should be displayed.
    /// </summary>
    /// <param name="call">The function call content to format.</param>
    /// <returns>A detail string to append after the tool name, or <see langword="null"/>.</returns>
    public abstract string? FormatDetail(FunctionCallContent call);

    /// <summary>
    /// Formats a tool call using the first matching formatter from the provided list.
    /// Returns <c>"{toolName} {detail}"</c> when a formatter produces detail,
    /// or just <c>"{toolName}"</c> otherwise.
    /// </summary>
    internal static string Format(IReadOnlyList<ToolCallFormatter> formatters, FunctionCallContent call)
    {
        foreach (var formatter in formatters)
        {
            if (formatter.CanFormat(call))
            {
                string? detail = formatter.FormatDetail(call);
                return detail is not null ? $"{call.Name} {detail}" : call.Name;
            }
        }

        return call.Name;
    }

    /// <summary>
    /// Creates the default list of tool call formatters. The <see cref="FallbackToolFormatter"/>
    /// is always last. Users can call this method and combine the result with their own formatters.
    /// </summary>
    /// <returns>A list of all built-in tool call formatters.</returns>
    public static List<ToolCallFormatter> BuildDefaultToolFormatters()
    {
        return
        [
            new TodoToolFormatter(),
            new ModeToolFormatter(),
            new SubAgentToolFormatter(),
            new FileMemoryToolFormatter(),
            new WebSearchToolFormatter(),
            new FallbackToolFormatter(),
        ];
    }

    /// <summary>
    /// Extracts a string argument value from a function call.
    /// </summary>
    protected static string? GetStringArgumentValue(FunctionCallContent call, string paramName)
    {
        if (call.Arguments?.TryGetValue(paramName, out object? value) != true || value is null)
        {
            return null;
        }

        return value switch
        {
            JsonElement je when je.ValueKind == JsonValueKind.String => je.GetString(),
            string s => s,
            _ => value.ToString(),
        };
    }

    /// <summary>
    /// Extracts an integer argument value from a function call.
    /// </summary>
    protected static int? GetIntArgumentValue(FunctionCallContent call, string paramName)
    {
        if (call.Arguments?.TryGetValue(paramName, out object? value) != true || value is null)
        {
            return null;
        }

        return value switch
        {
            JsonElement je when je.ValueKind == JsonValueKind.Number => je.GetInt32(),
            int i => i,
            _ => int.TryParse(value.ToString(), out int parsed) ? parsed : null,
        };
    }

    /// <summary>
    /// Extracts a list of integer argument values from a function call.
    /// </summary>
    protected static List<int>? GetIntListArgumentValue(FunctionCallContent call, string paramName)
    {
        if (call.Arguments?.TryGetValue(paramName, out object? value) != true || value is null)
        {
            return null;
        }

        var result = new List<int>();

        if (value is JsonElement je && je.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in je.EnumerateArray())
            {
                if (item.ValueKind == JsonValueKind.Number)
                {
                    result.Add(item.GetInt32());
                }
            }
        }

        return result.Count > 0 ? result : null;
    }

    /// <summary>
    /// Truncates a string to the specified maximum length, appending an ellipsis if truncated.
    /// </summary>
    protected static string Truncate(string text, int maxLength)
    {
        return text.Length <= maxLength ? text : string.Concat(text.AsSpan(0, maxLength), "…");
    }
}
