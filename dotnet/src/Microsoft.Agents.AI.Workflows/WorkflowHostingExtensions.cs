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
    /// <param name="workflow">The workflow to be hosted by the resulting <see cref="AIAgent"/></param>
    /// <param name="id">A unique id for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="name">A name for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="description">A description for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="checkpointManager">A <see cref="CheckpointManager"/> to enable persistence of run state.</param>
    /// <param name="executionEnvironment">Specify the execution environment to use when running the workflows. See
    /// <see cref="InProcessExecution.OffThread"/>, <see cref="InProcessExecution.Concurrent"/> and
    /// <see cref="InProcessExecution.Lockstep"/> for the in-process environments.</param>
    /// <returns></returns>
    public static AIAgent AsAgent(
        this Workflow<List<ChatMessage>> workflow,
        string? id = null,
        string? name = null,
        string? description = null,
        CheckpointManager? checkpointManager = null,
        IWorkflowExecutionEnvironment? executionEnvironment = null)
    {
        return new WorkflowHostAgent(workflow, id, name, description, checkpointManager, executionEnvironment);
    }

    /// <summary>
    /// Convert a workflow with the appropriate primary input type to an <see cref="AIAgent"/>.
    /// </summary>
    /// <param name="workflow">The workflow to be hosted by the resulting <see cref="AIAgent"/></param>
    /// <param name="id">A unique id for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="name">A name for the hosting <see cref="AIAgent"/>.</param>
    /// /// <param name="description">A description for the hosting <see cref="AIAgent"/>.</param>
    /// <param name="checkpointManager">A <see cref="CheckpointManager"/> to enable persistence of run state.</param>
    /// <param name="executionEnvironment">Specify the execution environment to use when running the workflows. See
    /// <see cref="InProcessExecution.OffThread"/>, <see cref="InProcessExecution.Concurrent"/> and
    /// <see cref="InProcessExecution.Lockstep"/> for the in-process environments.</param>
    /// <returns></returns>
    public static async ValueTask<AIAgent> AsAgentAsync(
        this Workflow workflow,
        string? id = null,
        string? name = null,
        string? description = null,
        CheckpointManager? checkpointManager = null,
        IWorkflowExecutionEnvironment? executionEnvironment = null)
    {
        Workflow<List<ChatMessage>>? maybeTyped = await workflow.TryPromoteAsync<List<ChatMessage>>()
                                                                .ConfigureAwait(false);

        if (maybeTyped is null)
        {
            throw new InvalidOperationException("Cannot host a workflow that does not accept List<ChatMessage> as an input");
        }

        return maybeTyped.AsAgent(id, name, description, checkpointManager, executionEnvironment);
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
