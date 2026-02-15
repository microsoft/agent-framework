// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.DurableTask;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// A custom <see cref="ITaskOrchestrator"/> implementation that delegates workflow orchestration
/// execution to the <see cref="DurableWorkflowRunner"/>.
/// </summary>
internal sealed class WorkflowOrchestrator : ITaskOrchestrator
{
    private readonly IServiceProvider _serviceProvider;

    /// <summary>
    /// Initializes a new instance of the <see cref="WorkflowOrchestrator"/> class.
    /// </summary>
    /// <param name="serviceProvider">The service provider used to resolve workflow dependencies.</param>
    public WorkflowOrchestrator(IServiceProvider serviceProvider)
    {
        this._serviceProvider = serviceProvider ?? throw new ArgumentNullException(nameof(serviceProvider));
    }

    /// <inheritdoc />
    public Type InputType => typeof(DurableWorkflowInput<object>);

    /// <inheritdoc />
    public Type OutputType => typeof(string);

    /// <inheritdoc />
    public async Task<object?> RunAsync(TaskOrchestrationContext context, object? input)
    {
        ArgumentNullException.ThrowIfNull(context);

        DurableWorkflowRunner runner = this._serviceProvider.GetRequiredService<DurableWorkflowRunner>();
        ILogger logger = context.CreateReplaySafeLogger(context.Name);

        DurableWorkflowInput<object> workflowInput = input switch
        {
            DurableWorkflowInput<object> existing => existing,
            _ => new DurableWorkflowInput<object> { Input = input! }
        };

        // ConfigureAwait(true) is required to preserve the orchestration context
        // across awaits, which the Durable Task framework uses for replay.
        return await runner.RunWorkflowOrchestrationAsync(context, workflowInput, logger).ConfigureAwait(true);
    }
}
