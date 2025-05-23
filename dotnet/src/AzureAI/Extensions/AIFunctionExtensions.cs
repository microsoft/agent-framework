// Copyright (c) Microsoft. All rights reserved.
using Azure.AI.Agents.Persistent;
using Microsoft.Extensions.AI;
using System;

namespace Microsoft.Agents.AzureAI;

/// <summary>
/// Extensions for <see cref="AIFunction"/> to support Azure AI specific operations.
/// </summary>
public static class AIFunctionExtensions
{
    /// <summary>
    /// Convert <see cref="AIFunction"/> to an OpenAI tool model.
    /// </summary>
    /// <param name="function">The source function</param>
    /// <param name="pluginName">The plugin name</param>
    /// <returns>An OpenAI tool definition</returns>
    public static FunctionToolDefinition ToToolDefinition(this AIFunction function, string pluginName)
    {
        Verify.NotNull(function, nameof(function));

        BinaryData parameters = new(function.JsonSchema, function.JsonSerializerOptions);
        return new FunctionToolDefinition(function.Name, function.Description, parameters);
    }
}
