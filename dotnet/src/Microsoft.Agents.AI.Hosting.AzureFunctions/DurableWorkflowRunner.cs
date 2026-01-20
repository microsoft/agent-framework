// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Executes workflow orchestrations and activity functions for durable workflows.
/// </summary>
internal sealed class DurableWorkflowRunner
{
    private readonly DurableWorkflowOptions _options;
    private readonly ILogger<DurableWorkflowRunner> _logger;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowRunner"/> class.
    /// </summary>
    /// <param name="logger">The logger instance.</param>
    /// <param name="durableOptions">The durable options containing workflow configurations.</param>
    public DurableWorkflowRunner(ILogger<DurableWorkflowRunner> logger, DurableOptions durableOptions)
    {
        ArgumentNullException.ThrowIfNull(logger);
        ArgumentNullException.ThrowIfNull(durableOptions);

        this._logger = logger;
        this._options = durableOptions.Workflows;
    }

    /// <summary>
    /// Runs a workflow orchestration.
    /// </summary>
    /// <param name="context">The task orchestration context.</param>
    /// <param name="request">The workflow run request containing workflow name and input.</param>
    /// <param name="logger">The replay-safe logger for orchestration logging.</param>
    /// <returns>A list containing the workflow execution result.</returns>
    internal async Task<List<string>> RunWorkflowOrchestrationAsync(
        TaskOrchestrationContext context,
        DuableWorkflowRunRequest request,
        ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(request);

        if (!this._options.Workflows.TryGetValue(request.WorkflowName, out Workflow? workflow))
        {
            throw new InvalidOperationException($"Workflow '{request.WorkflowName}' not found.");
        }

        logger.LogRunningWorkflow(workflow.Name);

        string result = await this.ExecuteWorkflowLevelsAsync(context, workflow, request.Input, logger).ConfigureAwait(true);

        await CleanupWorkflowStateAsync(context).ConfigureAwait(true);

        return [result];
    }

    /// <summary>
    /// Cleans up the workflow state entity by signaling it to delete itself.
    /// </summary>
    private static async Task CleanupWorkflowStateAsync(TaskOrchestrationContext context)
    {
        EntityInstanceId stateEntityId = new(WorkflowSharedStateEntity.EntityName, context.InstanceId);

        // Call the entity's Delete method to clean up state
        // Using CallEntityAsync ensures the deletion completes before the orchestration finishes
        await context.Entities.CallEntityAsync(stateEntityId, nameof(WorkflowSharedStateEntity.Delete)).ConfigureAwait(true);
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

        if (!this._options.Executors.TryGetExecutor(executorName, out ExecutorRegistration? registration) || registration is null)
        {
            throw new InvalidOperationException($"Executor '{executorName}' not found in the executor registry.");
        }

        this._logger.LogExecutingActivity(registration.ExecutorId, executorName);

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

    private async Task<string> ExecuteWorkflowLevelsAsync(
        TaskOrchestrationContext context,
        Workflow workflow,
        string initialInput,
        ILogger logger)
    {
        WorkflowExecutionPlan plan = WorkflowHelper.GetExecutionPlan(workflow);
        Dictionary<string, string> results = [];

        foreach (WorkflowExecutionLevel level in plan.Levels)
        {
            if (level.Executors.Count == 1)
            {
                WorkflowExecutorInfo executorInfo = level.Executors[0];
                string input = GetExecutorInput(executorInfo.ExecutorId, initialInput, results, plan);
                results[executorInfo.ExecutorId] = await this.ExecuteExecutorAsync(context, executorInfo, input, logger).ConfigureAwait(true);
            }
            else
            {
                List<Task<(string Id, string Result)>> tasks = [];
                foreach (WorkflowExecutorInfo executorInfo in level.Executors)
                {
                    string input = GetExecutorInput(executorInfo.ExecutorId, initialInput, results, plan);
                    tasks.Add(this.ExecuteExecutorWithIdAsync(context, executorInfo, input, logger));
                }

                foreach ((string id, string result) in await Task.WhenAll(tasks).ConfigureAwait(true))
                {
                    results[id] = result;
                }
            }
        }

        return GetFinalResult(plan, results);
    }

    private async Task<(string Id, string Result)> ExecuteExecutorWithIdAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        ILogger logger)
    {
        string result = await this.ExecuteExecutorAsync(context, executorInfo, input, logger).ConfigureAwait(true);
        return (executorInfo.ExecutorId, result);
    }

    private async Task<string> ExecuteExecutorAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        ILogger logger)
    {
        if (!executorInfo.IsAgenticExecutor)
        {
            string triggerName = $"dafx-{GetBaseName(executorInfo.ExecutorId)}";
            return await context.CallActivityAsync<string>(triggerName, input).ConfigureAwait(true);
        }

        return await ExecuteAgentAsync(context, executorInfo, input, logger).ConfigureAwait(true);
    }

    private static async Task<string> ExecuteAgentAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        ILogger logger)
    {
        string agentName = GetBaseName(executorInfo.ExecutorId);
        DurableAIAgent agent = context.GetAgent(agentName);

        if (agent is null)
        {
            logger.LogWarning("Agent '{AgentName}' not found", agentName);
            return $"Agent '{agentName}' not found";
        }

        AgentThread thread = agent.GetNewThread();
        AgentRunResponse response = await agent.RunAsync(input, thread).ConfigureAwait(true);
        return response.Text;
    }

    private static string GetExecutorInput(
        string executorId,
        string initialInput,
        Dictionary<string, string> results,
        WorkflowExecutionPlan plan)
    {
        List<string> predecessors = plan.Predecessors[executorId];

        if (predecessors.Count == 0)
        {
            return initialInput;
        }

        if (predecessors.Count == 1)
        {
            return results.TryGetValue(predecessors[0], out string? result) ? result : initialInput;
        }

        List<string> aggregated = [];
        foreach (string predecessorId in predecessors)
        {
            if (results.TryGetValue(predecessorId, out string? result))
            {
                aggregated.Add(result);
            }
        }

        return SerializeToJson(aggregated);
    }

    private static string GetFinalResult(WorkflowExecutionPlan plan, Dictionary<string, string> results)
    {
        WorkflowExecutionLevel lastLevel = plan.Levels[^1];

        if (lastLevel.Executors.Count == 1)
        {
            return results[lastLevel.Executors[0].ExecutorId];
        }

        List<string> finalResults = [];
        foreach (WorkflowExecutorInfo executor in lastLevel.Executors)
        {
            if (results.TryGetValue(executor.ExecutorId, out string? result))
            {
                finalResults.Add(result);
            }
        }

        return string.Join("\n---\n", finalResults);
    }

    private static string ParseExecutorName(string activityFunctionName)
    {
        const string Prefix = "dafx-";

        if (!activityFunctionName.StartsWith(Prefix, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"Activity function name '{activityFunctionName}' does not start with '{Prefix}' prefix.");
        }

        string executorName = activityFunctionName[Prefix.Length..];

        if (string.IsNullOrEmpty(executorName))
        {
            throw new InvalidOperationException(
                $"Activity function name '{activityFunctionName}' is not in the expected format '{Prefix}{{executorName}}'.");
        }

        return executorName;
    }

    private static string GetBaseName(string executorId)
    {
        int underscoreIndex = executorId.IndexOf('_');
        return underscoreIndex > 0 ? executorId[..underscoreIndex] : executorId;
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing known types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing known types.")]
    private static string SerializeToJson(List<string> values)
    {
        return JsonSerializer.Serialize(values);
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow types registered at startup.")]
    private static string SerializeResult(object? result)
    {
        if (result is null)
        {
            return string.Empty;
        }

        if (result is string str)
        {
            return str;
        }

        Type resultType = result.GetType();
        if (resultType.IsPrimitive || resultType == typeof(decimal))
        {
            return result.ToString() ?? string.Empty;
        }

        return JsonSerializer.Serialize(result, resultType);
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static object DeserializeInput(string input, Type targetType)
    {
        if (targetType == typeof(string))
        {
            return input;
        }

        string json = input;
        if (input.StartsWith('"') && input.EndsWith('"'))
        {
            try
            {
                string? innerJson = JsonSerializer.Deserialize<string>(input);
                if (innerJson is not null)
                {
                    json = innerJson;
                }
            }
            catch (JsonException)
            {
                // Not double-serialized, use original
            }
        }

        return JsonSerializer.Deserialize(json, targetType)
            ?? throw new InvalidOperationException($"Failed to deserialize input to type '{targetType.Name}'.");
    }
}
