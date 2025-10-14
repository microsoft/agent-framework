// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
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
    /// <param name="tools">Instance of <see cref="IList{AITool}"/></param>
    internal static AITool CreateFunctionTool(this FunctionTool tool, IList<AITool>? tools)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name);

        // use the tool from the provided list if it exists
        if (tools is not null)
        {
            var function = tools
                .OfType<AIFunction>()
                .FirstOrDefault(f => f.Name == tool.Name);

            // TODO: Consider validating that the function signature matches the schema

            if (function is not null)
            {
                return function;
            }
        }

        var jsonSchema = tool.ExtensionData?.GetSchema() ?? new(); // TODO: Validate that this is a valid JSON schema

        return AIFunctionFactory.CreateDeclaration(
            name: tool.Name,
            description: tool.Description,
            jsonSchema: jsonSchema);
    }
}
