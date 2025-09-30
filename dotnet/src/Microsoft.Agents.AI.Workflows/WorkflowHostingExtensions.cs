// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

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

    /// <summary>
    /// Convert a workflow with the appropriate primary input type to an <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="workflow"></param>
    /// <param name="id"></param>
    /// <param name="name"></param>
    /// <returns></returns>
    public static async ValueTask<AIAgent> AsAgentAsync(this Workflow workflow, string? id = null, string? name = null)
    {
        Workflow<List<ChatMessage>>? maybeTyped = await workflow.TryPromoteAsync<List<ChatMessage>>()
                                                                .ConfigureAwait(false);

        if (maybeTyped is null)
        {
            throw new InvalidOperationException("Cannot host a workflow that does not accept List<ChatMessage> as an input");
        }

        return maybeTyped.AsAgent(id: id, name: name);
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
