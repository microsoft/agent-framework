// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Harness.Shared.Console.ToolFormatters;

/// <summary>
/// Formats <c>web_search</c> tool calls, showing the search query.
/// </summary>
public sealed class WebSearchToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) =>
        call.Name is "web_search";

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call)
    {
        string? value = GetStringArgumentValue(call, "query");
        return value is not null ? $"({value})" : null;
    }
}
