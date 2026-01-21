// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Core workflow runner that executes workflow orchestrations using Durable Tasks.
/// This class contains the core workflow execution logic independent of the hosting environment.
/// </summary>
public class DurableWorkflowRunner
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowRunner"/> class.
    /// </summary>
    /// <param name="logger">The logger instance.</param>
    /// <param name="durableOptions">The durable options containing workflow configurations.</param>
    public DurableWorkflowRunner(ILogger<DurableWorkflowRunner> logger, DurableOptions durableOptions)
    {
        ArgumentNullException.ThrowIfNull(logger);
        ArgumentNullException.ThrowIfNull(durableOptions);

        this.Logger = logger;
        this.Options = durableOptions.Workflows;
    }

    /// <summary>
    /// Gets the workflow options.
    /// </summary>
    protected DurableWorkflowOptions Options { get; }

    /// <summary>
    /// Gets the logger instance.
    /// </summary>
    protected ILogger Logger { get; }

    /// <summary>
    /// Runs a workflow orchestration.
    /// </summary>
    /// <param name="context">The task orchestration context.</param>
    /// <param name="input">The workflow run input containing workflow name and input.</param>
    /// <param name="logger">The replay-safe logger for orchestration logging.</param>
    /// <returns>The result of the workflow execution.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the specified workflow is not found.</exception>
    public async Task<string> RunWorkflowOrchestrationAsync(
        TaskOrchestrationContext context,
        string input,
        ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(input);

        string orchestrationName = context.Name;
        string workflowName = WorkflowNamingHelper.ToWorkflowName(orchestrationName);
        if (!this.Options.Workflows.TryGetValue(workflowName, out Workflow? workflow))
        {
            throw new InvalidOperationException($"Workflow '{workflowName}' not found.");
        }

        logger.LogRunningWorkflow(workflow.Name);

        string result = await this.ExecuteWorkflowLevelsAsync(context, workflow, input, logger).ConfigureAwait(true);

        await CleanupWorkflowStateAsync(context).ConfigureAwait(true);

        return result;
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
    /// Parses the executor name from an activity function name.
    /// </summary>
    /// <param name="activityFunctionName">The activity function name.</param>
    /// <returns>The extracted executor name.</returns>
    protected static string ParseExecutorName(string activityFunctionName)
    {
        if (!activityFunctionName.StartsWith(WorkflowNamingHelper.OrchestrationFunctionPrefix, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"Activity function name '{activityFunctionName}' does not start with '{WorkflowNamingHelper.OrchestrationFunctionPrefix}' prefix.");
        }

        string executorName = activityFunctionName[WorkflowNamingHelper.OrchestrationFunctionPrefix.Length..];

        if (string.IsNullOrEmpty(executorName))
        {
            throw new InvalidOperationException(
                $"Activity function name '{activityFunctionName}' is not in the expected format '{WorkflowNamingHelper.OrchestrationFunctionPrefix}{{executorName}}'.");
        }

        return executorName;
    }

    /// <summary>
    /// Serializes a list of strings to JSON.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing known types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing known types.")]
    protected static string SerializeToJson(List<string> values)
    {
        return JsonSerializer.Serialize(values);
    }

    /// <summary>
    /// Serializes a result object to JSON or string.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow types registered at startup.")]
    protected static string SerializeResult(object? result)
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

    /// <summary>
    /// Deserializes input from JSON to the target type.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    protected static object DeserializeInput(string input, Type targetType)
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
            string executorName = WorkflowNamingHelper.GetExecutorName(executorInfo.ExecutorId);
            string triggerName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);
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
        string agentName = WorkflowNamingHelper.GetExecutorName(executorInfo.ExecutorId);
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
}
