﻿// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="InvokeClientTaskAction"/>.
/// </summary>
public static class FunctionToolExtensions
{
    /// <summary>
    /// Creates a <see cref="AIFunctionDeclaration"/> from a <see cref="InvokeClientTaskAction"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="InvokeClientTaskAction"/></param>
    /// <param name="functions">Instance of <see cref="IList{AIFunction}"/></param>
    internal static AITool CreateFunctionTool(this InvokeClientTaskAction tool, IList<AIFunction>? functions)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name);

        // use the tool from the provided list if it exists
        if (functions is not null)
        {
            var function = functions
                .OfType<AIFunction>()
                .FirstOrDefault(f => tool.Matches(f));

            // TODO: Consider validating that the function signature matches the schema

            if (function is not null)
            {
                return function;
            }
        }

        // TODO: Replace with actual schema from tool
        var jsonSchema = new System.Text.Json.JsonElement(); // TODO: Validate that this is a valid JSON schema

        return AIFunctionFactory.CreateDeclaration(
            name: tool.Name,
            description: tool.Description,
            jsonSchema: jsonSchema);
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

        if (tool.Name != aiFunc.Name)
        {
            return false;
        }

        return true;
    }
}
