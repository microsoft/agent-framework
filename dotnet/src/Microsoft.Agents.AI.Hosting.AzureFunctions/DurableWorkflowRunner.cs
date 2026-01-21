// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Azure Functions-specific workflow runner that extends the base <see cref="DurableWorkflowRunner"/>
/// with Azure Functions activity execution support.
/// </summary>
internal sealed class FunctionsWorkflowRunner : DurableWorkflowRunner
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FunctionsWorkflowRunner"/> class.
    /// </summary>
    /// <param name="logger">The logger instance.</param>
    /// <param name="durableOptions">The durable options containing workflow configurations.</param>
    public FunctionsWorkflowRunner(ILogger<FunctionsWorkflowRunner> logger, DurableOptions durableOptions)
        : base(logger, durableOptions)
    {
    }

    /// <summary>
    /// Executes an activity function for a workflow executor.
    /// </summary>
    /// <param name="activityFunctionName">The name of the activity function to execute.</param>
    /// <param name="input">The serialized executor input.</param>
    /// <param name="durableTaskClient">The durable task client for entity operations.</param>
    /// <param name="functionContext">The function context containing binding data with the orchestration instance ID.</param>
    /// <returns>The serialized executor output.</returns>
    internal async Task<string> ExecuteActivityAsync(
        string activityFunctionName,
        string input,
        DurableTaskClient durableTaskClient,
        FunctionContext functionContext)
    {
        ArgumentNullException.ThrowIfNull(activityFunctionName);
        ArgumentNullException.ThrowIfNull(input);
        ArgumentNullException.ThrowIfNull(durableTaskClient);
        ArgumentNullException.ThrowIfNull(functionContext);

        string executorName = ParseExecutorName(activityFunctionName);

        if (!this.Options.Executors.TryGetExecutor(executorName, out ExecutorRegistration? registration) || registration is null)
        {
            throw new InvalidOperationException($"Executor '{executorName}' not found in the executor registry.");
        }

        this.Logger.LogExecutingActivity(registration.ExecutorId, executorName);

        Executor executor = await registration.CreateExecutorInstanceAsync("activity-run", CancellationToken.None)
            .ConfigureAwait(false);

        Type inputType = executor.InputTypes.FirstOrDefault() ?? typeof(string);
        object typedInput = DeserializeInput(input, inputType);

        // Get the orchestration instance ID from the function context binding data
        string instanceId = GetInstanceIdFromContext(functionContext)
            ?? throw new InvalidOperationException(
                "Could not retrieve orchestration instance ID from FunctionContext. " +
                "Ensure the activity is being called from within a durable orchestration.");

        // Create context with durable entity-backed state
        IWorkflowContext context = CreateExecutorContext(instanceId, durableTaskClient);

        object? result = await executor.ExecuteAsync(
            typedInput,
            new TypeId(inputType),
            context,
            CancellationToken.None).ConfigureAwait(false);

        return SerializeResult(result);
    }

    private static string? GetInstanceIdFromContext(FunctionContext functionContext)
    {
        if (functionContext.BindingContext.BindingData.TryGetValue("instanceId", out object? instanceIdObj) &&
            instanceIdObj is string instanceId)
        {
            return instanceId;
        }

        return null;
    }

    [UnconditionalSuppressMessage("AOT", "IL2026:RequiresUnreferencedCode", Justification = "DurableExecutorContext state serialization is done at runtime with user-known types.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "DurableExecutorContext state serialization is done at runtime with user-known types.")]
    private static DurableExecutorContext CreateExecutorContext(
        string instanceId,
        DurableTaskClient client)
    {
        return new DurableExecutorContext(instanceId, client);
    }
}
