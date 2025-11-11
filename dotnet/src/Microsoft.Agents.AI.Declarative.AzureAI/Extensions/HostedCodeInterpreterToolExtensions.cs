// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for <see cref="HostedCodeInterpreterTool"/>.
/// </summary>
internal static class HostedCodeInterpreterToolExtensions
{
    /// <summary>
    /// Creates a <see cref="CodeInterpreterToolDefinition"/> from a <see cref="HostedCodeInterpreterTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="CodeInterpreterTool"/></param>
    internal static CodeInterpreterToolDefinition CreateHostedCodeInterpreterToolDefinition(this HostedCodeInterpreterTool tool)
    {
        Throw.IfNull(tool);

        return new CodeInterpreterToolDefinition();
    }
}
