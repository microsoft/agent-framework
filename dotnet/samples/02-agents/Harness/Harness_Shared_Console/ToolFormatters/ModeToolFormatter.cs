// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Formats <c>AgentMode_*</c> tool calls, showing the target mode for Set operations.
/// </summary>
public sealed class ModeToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) => call.Name.StartsWith("AgentMode_", StringComparison.Ordinal);

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call) => call.Name switch
    {
        "AgentMode_Set" => FormatStringArg(call, "mode"),
        _ => null,
    };

    private static string? FormatStringArg(FunctionCallContent call, string paramName)
    {
        string? value = GetStringArgumentValue(call, paramName);
        return value is not null ? $"({value})" : null;
    }
}
