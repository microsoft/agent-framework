// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="InvokeClientTaskAction"/>.
/// </summary>
internal static class FunctionToolExtensions
{
    /// <summary>
    /// Creates a <see cref="AIFunctionDeclaration"/> from a <see cref="InvokeClientTaskAction"/>.
    /// </summary>
    /// <remarks>
    /// If a matching function already exists in the provided list, it will be returned.
    /// Otherwise, a new function declaration will be created.
    /// </remarks>
    /// <param name="tool">Instance of <see cref="InvokeClientTaskAction"/></param>
    /// <param name="functions">Instance of <see cref="IList{AIFunction}"/></param>
    internal static AITool CreateOrGetAITool(this InvokeClientTaskAction tool, IList<AIFunction>? functions)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name);

        // use the tool from the provided list if it exists
        if (functions is not null)
        {
            var function = functions.FirstOrDefault(f => tool.Matches(f));

            if (function is not null)
            {
                return function;
            }
        }

        return AIFunctionFactory.CreateDeclaration(
            name: tool.Name,
            description: tool.Description,
            jsonSchema: tool.ClientActionInputSchema?.GetSchema() ?? s_defaultSchema);
    }

    /// <summary>
    /// Checks if a <see cref="InvokeClientTaskAction"/> matches an <see cref="AITool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="InvokeClientTaskAction"/></param>
    /// <param name="aiFunc">Instance of <see cref="AIFunction"/></param>
    internal static bool Matches(this InvokeClientTaskAction tool, AIFunction aiFunc)
    {
        Throw.IfNull(tool);
        Throw.IfNull(aiFunc);

        return tool.Name == aiFunc.Name;
    }

    private static readonly JsonElement s_defaultSchema = JsonDocument.Parse("{\"type\":\"object\",\"properties\":{},\"additionalProperties\":false}").RootElement;
}
