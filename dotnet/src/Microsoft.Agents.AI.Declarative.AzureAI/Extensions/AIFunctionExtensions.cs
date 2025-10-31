// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for <see cref="AIFunction"/>.
/// </summary>
internal static class AIFunctionExtensions
{
    /// <summary>
    /// Creates a <see cref="AIFunctionDeclaration"/> from a <see cref="AIFunction"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="AIFunction"/></param>
    internal static FunctionToolDefinition CreateFunctionToolDefinition(this AIFunction tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name);

        BinaryData parameters = tool.GetParameters();

        return new FunctionToolDefinition(
            name: tool.Name,
            description: tool.Description,
            parameters: parameters);
    }

    internal static BinaryData GetParameters(this AIFunction tool)
    {
        Throw.IfNull(tool);

        return new BinaryData("{}");
    }
}
