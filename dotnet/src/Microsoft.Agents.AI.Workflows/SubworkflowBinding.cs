// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Specialized;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Represents the workflow binding details for a subworkflow, including its instance, identifier, and optional
/// executor options.
/// </summary>
/// <param name="WorkflowInstance"></param>
/// <param name="Id"></param>
/// <param name="ExecutorOptions"></param>
public record SubworkflowBinding(Workflow WorkflowInstance, string Id, ExecutorOptions? ExecutorOptions = null)
    : ExecutorBinding(Throw.IfNull(Id),
                           CreateWorkflowExecutorFactory(WorkflowInstance, Id, ExecutorOptions),
                           typeof(WorkflowHostExecutor),
                           WorkflowInstance)
{
    private static Func<string, ValueTask<Executor>> CreateWorkflowExecutorFactory(Workflow workflow, string id, ExecutorOptions? options)
    {
        object ownershipToken = new();
        workflow.TakeOwnership(ownershipToken, subworkflow: true);

        return InitHostExecutorAsync;

        ValueTask<Executor> InitHostExecutorAsync(string runId)
        {
            return new(new WorkflowHostExecutor(id, workflow, runId, ownershipToken, options));
        }
    }

    /// <inheritdoc/>
    public override bool IsSharedInstance => false;

    /// <inheritdoc/>
    public override bool SupportsConcurrentSharedExecution => true;

    /// <inheritdoc/>
    public override bool SupportsResetting => false;
}
