// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Bot.ObjectModel;

/// <summary>
/// Extension methods for <see cref="InvokeClientTaskAction"/>.
/// </summary>
public static class FunctionToolExtensions
{
    /// <summary>
    /// Creates a <see cref="FunctionToolDefinition"/> from a <see cref="InvokeClientTaskAction"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="InvokeClientTaskAction"/></param>
    internal static FunctionToolDefinition CreateFunctionToolDefinition(this InvokeClientTaskAction tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.Name);

        BinaryData parameters = tool.GetParameters();

        return new FunctionToolDefinition(
            name: tool.Name,
            description: tool.Description,
            parameters: parameters);
    }

    /// <summary>
    /// Creates the parameters schema for a <see cref="InvokeClientTaskAction"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="InvokeClientTaskAction"/></param>
    internal static BinaryData GetParameters(this InvokeClientTaskAction tool)
    {
        Throw.IfNull(tool);

        var parameters = tool.ClientActionInputSchema?.GetSchema().ToString() ?? DefaultSchema;

        return new BinaryData(parameters);
    }

    private const string DefaultSchema = "{\"type\":\"object\",\"properties\":{},\"additionalProperties\":false}";
}
