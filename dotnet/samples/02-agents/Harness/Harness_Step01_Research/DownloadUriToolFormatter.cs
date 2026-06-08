// Copyright (c) Microsoft. All rights reserved.

using Harness.Shared.Console.ToolFormatters;
using Microsoft.Extensions.AI;

namespace SampleApp;

/// <summary>
/// Formats <c>DownloadUri</c> tool calls, showing the target URI.
/// </summary>
public sealed class DownloadUriToolFormatter : ToolCallFormatter
{
    /// <inheritdoc/>
    public override bool CanFormat(FunctionCallContent call) =>
        call.Name is "DownloadUri";

    /// <inheritdoc/>
    public override string? FormatDetail(FunctionCallContent call)
    {
        string? value = GetStringArgumentValue(call, "uri");
        return value is not null ? $"({value})" : null;
    }
}
