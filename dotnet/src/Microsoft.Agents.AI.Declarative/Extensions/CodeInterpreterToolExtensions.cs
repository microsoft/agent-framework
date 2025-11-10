// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="CodeInterpreterTool"/>.
/// </summary>
internal static class CodeInterpreterToolExtensions
{
    /// <summary>
    /// Creates a <see cref="HostedCodeInterpreterTool"/> from a <see cref="CodeInterpreterTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="CodeInterpreterTool"/></param>
    internal static HostedCodeInterpreterTool AsCodeInterpreterTool(this CodeInterpreterTool tool)
    {
        Throw.IfNull(tool);

        return new HostedCodeInterpreterTool();
    }
}
