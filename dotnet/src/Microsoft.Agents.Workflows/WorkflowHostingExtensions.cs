// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Provides extension methods for treating workflows as <see cref="AIAgent"/>
/// </summary>
public static class WorkflowHostingExtensions
{
    /// <summary>
    /// Convert a workflow with the appropriate primary input type to an <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="workflow"></param>
    /// <param name="id"></param>
    /// <param name="name"></param>
    /// <returns></returns>
    public static AIAgent AsAgent(this Workflow<List<ChatMessage>> workflow, string? id = null, string? name = null)
    {
        return new WorkflowHostAgent(workflow, id, name);
    }

    internal static FunctionCallContent ToFunctionCall(this ExternalRequest request)
    {
        Dictionary<string, object?> parameters = new()
        {
            { "data", request.Data}
        };

        return new FunctionCallContent(request.RequestId, request.PortInfo.PortId, parameters);
    }
}
