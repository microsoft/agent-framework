// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Catch-all formatter that handles any tool not matched by a more specific formatter.
/// Displays a generic summary of the tool's arguments. This formatter should always be
/// placed last in the formatter list.
/// </summary>
public sealed class FallbackToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) => true;

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call)
    {
        if (call.Arguments is null || call.Arguments.Count == 0)
        {
            return null;
        }

        var parts = new List<string>();
        foreach (var kvp in call.Arguments)
        {
            string? stringValue = kvp.Value switch
            {
                JsonElement je => je.ValueKind switch
                {
                    JsonValueKind.String => je.GetString(),
                    JsonValueKind.Number => je.GetRawText(),
                    JsonValueKind.True => "true",
                    JsonValueKind.False => "false",
                    _ => null,
                },
                not null => kvp.Value.ToString(),
                _ => null,
            };

            if (stringValue is not null)
            {
                parts.Add($"{kvp.Key}: {Truncate(stringValue, 40)}");
            }
        }

        return parts.Count > 0 ? $"({string.Join(", ", parts)})" : null;
    }
}
