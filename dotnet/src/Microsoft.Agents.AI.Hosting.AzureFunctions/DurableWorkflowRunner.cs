// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

internal sealed class DurableWorkflowRunner
{
    private readonly DurableWorkflowOptions _options;
    private readonly ILogger<DurableWorkflowRunner> _logger;
    public DurableWorkflowRunner(ILogger<DurableWorkflowRunner> logger, DurableWorkflowOptions durableWorkflowOptions)
    {
        this._logger = logger;
        this._options = durableWorkflowOptions;
    }

    internal async Task RunAsync(
        TaskOrchestrationContext taskOrchestrationContext,
        string workflowName,
        object? initialInput = null,
        CancellationToken cancellationToken = default)
    {
        this._logger.LogAttemptingToRunWorkflow(workflowName);

        if (this._options.Workflows.TryGetValue(workflowName, out Workflow? wf))
        {
            this._logger.LogRunningWorkflow(wf.Name);

            await this.RunExecutorsInWorkFlowAsync(taskOrchestrationContext, wf, initialInput, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            throw new InvalidOperationException($"Workflow '{workflowName}' not found.");
        }
    }

    private Task RunExecutorsInWorkFlowAsync(
        TaskOrchestrationContext taskOrchestrationContext,
        Workflow wf,
        object? initialInput,
        CancellationToken cancellationToken)
    {
        // Extract edeges and executors from the workflow and execute them in order/based on the pattern as Durable entities.

        return Task.CompletedTask;
    }
}
