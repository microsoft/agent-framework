// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="CodeInterpreterTool"/>.
/// </summary>
public static class CodeInterpreterToolExtensions
{
    /// <summary>
    /// Creates a <see cref="CodeInterpreterToolDefinition"/> from a <see cref="CodeInterpreterTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="CodeInterpreterTool"/></param>
    internal static CodeInterpreterToolDefinition CreateCodeInterpreterToolDefinition(this CodeInterpreterTool tool)
    {
        Throw.IfNull(tool);

        return new CodeInterpreterToolDefinition();
    }
}
