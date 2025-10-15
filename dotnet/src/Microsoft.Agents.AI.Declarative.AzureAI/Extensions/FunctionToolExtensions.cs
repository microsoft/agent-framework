// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="FunctionTool"/>.
/// </summary>
public static class FunctionToolExtensions
{
    /// <summary>
    /// Creates a <see cref="AIFunctionDeclaration"/> from a <see cref="FunctionTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="FunctionTool"/></param>
    internal static FunctionToolDefinition CreateFunctionToolDefinition(this FunctionTool tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name);

        BinaryData parameters = tool.GetParameters();

        return new FunctionToolDefinition(
            name: tool.Name,
            description: tool.Description,
            parameters: parameters);
    }

    internal static BinaryData GetParameters(this AgentTool tool)
    {
        Throw.IfNull(tool);

        return new BinaryData("{}");
    }
}
