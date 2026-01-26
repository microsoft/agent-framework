// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents the custom status set when the orchestration is waiting for an external event.
/// </summary>
/// <param name="EventName">The name of the event being waited for (the RequestPort ID).</param>
/// <param name="Input">The serialized input data that was passed to the RequestPort.</param>
/// <param name="RequestType">The full type name of the request type.</param>
/// <param name="ResponseType">The full type name of the expected response type.</param>
public sealed record PendingExternalEventStatus(
    string EventName,
    string Input,
    string RequestType,
    string ResponseType);

/// <summary>
/// Represents the complete custom status for a durable workflow orchestration.
/// </summary>
public sealed class DurableWorkflowCustomStatus
{
    /// <summary>
    /// Gets or sets the pending external event status when waiting for HITL input.
    /// </summary>
    public PendingExternalEventStatus? PendingEvent { get; set; }

    /// <summary>
    /// Gets or sets the list of serialized workflow events emitted by executors.
    /// </summary>
    public List<string> Events { get; set; } = [];
}

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

        return await this.ExecuteWorkflowLevelsAsync(context, workflow, input, logger).ConfigureAwait(true);
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

        // Check for double-serialized strings (e.g., "\"actual json\"")
        // A properly double-serialized string starts with \" and ends with \"
        if (input.Length > 2 && input[0] == '"' && input[^1] == '"' && input[1] == '\\')
        {
            string? innerJson = JsonSerializer.Deserialize<string>(input);
            if (innerJson is not null)
            {
                json = innerJson;
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
        Dictionary<string, string> results = new(plan.Levels.Sum(l => l.Executors.Count));

        // Track accumulated events and shared state
        DurableWorkflowCustomStatus customStatus = new();
        Dictionary<string, string> sharedState = [];

        foreach (WorkflowExecutionLevel level in plan.Levels)
        {
            // Filter executors based on edge conditions from their predecessors
            List<WorkflowExecutorInfo> eligibleExecutors = GetEligibleExecutors(level.Executors, results, plan, logger);

            if (eligibleExecutors.Count == 0)
            {
                // No eligible executors at this level, continue to next level
                continue;
            }

            if (eligibleExecutors.Count == 1)
            {
                WorkflowExecutorInfo executorInfo = eligibleExecutors[0];
                string input = GetExecutorInput(executorInfo.ExecutorId, initialInput, results, plan);
                string rawResult = await this.ExecuteExecutorAsync(context, executorInfo, input, logger, customStatus, sharedState).ConfigureAwait(true);
                results[executorInfo.ExecutorId] = UnwrapActivityResult(rawResult, customStatus, sharedState);

                // Update custom status with any new events
                UpdateCustomStatus(context, customStatus);
            }
            else
            {
                // For parallel execution, each activity gets a snapshot of the current state
                // State updates are merged after all activities complete
                Task<(string Id, string Result)>[] tasks = new Task<(string Id, string Result)>[eligibleExecutors.Count];
                for (int i = 0; i < eligibleExecutors.Count; i++)
                {
                    WorkflowExecutorInfo executorInfo = eligibleExecutors[i];
                    string input = GetExecutorInput(executorInfo.ExecutorId, initialInput, results, plan);
                    tasks[i] = this.ExecuteExecutorWithIdAsync(context, executorInfo, input, logger, customStatus, sharedState);
                }

                (string Id, string Result)[] completedTasks = await Task.WhenAll(tasks).ConfigureAwait(true);
                foreach ((string id, string rawResult) in completedTasks)
                {
                    results[id] = UnwrapActivityResult(rawResult, customStatus, sharedState);
                }

                // Update custom status with any new events
                UpdateCustomStatus(context, customStatus);
            }
        }

        return GetFinalResult(plan, results);
    }

    /// <summary>
    /// Unwraps an activity result, extracting state updates, events, and returning the actual result.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing known wrapper type.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing known wrapper type.")]
    private static string UnwrapActivityResult(string rawResult, DurableWorkflowCustomStatus customStatus, Dictionary<string, string> sharedState)
    {
        if (string.IsNullOrEmpty(rawResult))
        {
            return rawResult;
        }

        try
        {
            // Try to deserialize as DurableActivityOutput
            DurableActivityOutput? output = JsonSerializer.Deserialize<DurableActivityOutput>(rawResult);

            // Check if this is actually a DurableActivityOutput (has Result property set or state updates)
            // This distinguishes it from other JSON objects that would deserialize with default/empty values
            if (output is not null && (output.Result is not null || output.StateUpdates.Count > 0 || output.ClearedScopes.Count > 0 || output.Events.Count > 0))
            {
                // Apply cleared scopes first
                foreach (string clearedScope in output.ClearedScopes)
                {
                    string scopePrefix = clearedScope == "__default__" ? "__default__:" : $"{clearedScope}:";
                    List<string> keysToRemove = sharedState.Keys
                        .Where(k => k.StartsWith(scopePrefix, StringComparison.Ordinal))
                        .ToList();

                    foreach (string key in keysToRemove)
                    {
                        sharedState.Remove(key);
                    }
                }

                // Apply state updates
                foreach (KeyValuePair<string, string?> update in output.StateUpdates)
                {
                    if (update.Value is null)
                    {
                        sharedState.Remove(update.Key);
                    }
                    else
                    {
                        sharedState[update.Key] = update.Value;
                    }
                }

                // Add events to the accumulated list
                if (output.Events.Count > 0)
                {
                    customStatus.Events.AddRange(output.Events);
                }

                return output.Result ?? string.Empty;
            }
        }
        catch (JsonException)
        {
            // Not a wrapped result, return as-is
        }

        return rawResult;
    }

    /// <summary>
    /// Updates the orchestration custom status with current events and pending event info.
    /// </summary>
    private static void UpdateCustomStatus(TaskOrchestrationContext context, DurableWorkflowCustomStatus customStatus)
    {
        // Only update if there are events or a pending event
        if (customStatus.Events.Count > 0 || customStatus.PendingEvent is not null)
        {
            context.SetCustomStatus(customStatus);
        }
    }

    /// <summary>
    /// Wrapper for activity output that includes state updates and events.
    /// </summary>
    internal sealed class ActivityOutputWithState
    {
        /// <summary>
        /// Gets or sets the serialized result of the activity.
        /// </summary>
        public string? Result { get; set; }

        /// <summary>
        /// Gets or sets state updates made during activity execution.
        /// </summary>
        public Dictionary<string, string?> StateUpdates { get; set; } = [];

        /// <summary>
        /// Gets or sets scopes that were cleared during activity execution.
        /// </summary>
        public List<string> ClearedScopes { get; set; } = [];

        /// <summary>
        /// Gets or sets the serialized workflow events emitted during activity execution.
        /// </summary>
        public List<string> Events { get; set; } = [];
    }

    /// <summary>
    /// Wrapper for serialized workflow events that includes type information for proper deserialization.
    /// </summary>
    public sealed class SerializedWorkflowEvent
    {
        /// <summary>
        /// Gets or sets the assembly-qualified type name of the event.
        /// </summary>
        public string? TypeName { get; set; }

        /// <summary>
        /// Gets or sets the serialized JSON data of the event.
        /// </summary>
        public string? Data { get; set; }
    }

    /// <summary>
    /// Wrapper for activity input that includes shared state.
    /// </summary>
    internal sealed class ActivityInputWithState
    {
        /// <summary>
        /// Gets or sets the serialized executor input.
        /// </summary>
        public string? Input { get; set; }

        /// <summary>
        /// Gets or sets the shared state dictionary.
        /// </summary>
        public Dictionary<string, string> State { get; set; } = [];
    }

    /// <summary>
    /// Filters executors based on their incoming edge conditions.
    /// An executor is eligible if all its incoming edges have conditions that evaluate to true,
    /// or if the edges have no conditions.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static List<WorkflowExecutorInfo> GetEligibleExecutors(
        List<WorkflowExecutorInfo> executors,
        Dictionary<string, string> results,
        WorkflowExecutionPlan plan,
        ILogger logger)
    {
        List<WorkflowExecutorInfo> eligible = new(executors.Count);

        foreach (WorkflowExecutorInfo executorInfo in executors)
        {
            if (!plan.Predecessors.TryGetValue(executorInfo.ExecutorId, out List<string>? predecessors) || predecessors.Count == 0)
            {
                // Root executor (no predecessors) is always eligible
                eligible.Add(executorInfo);
                continue;
            }

            // Check if any predecessor's edge condition allows this executor to run
            bool isEligible = false;
            foreach (string predecessorId in predecessors)
            {
                // Get the condition for this edge (predecessor -> current executor)
                if (!plan.EdgeConditions.TryGetValue((predecessorId, executorInfo.ExecutorId), out Func<object?, bool>? condition) || condition is null)
                {
                    // No condition registered for this edge or edge has no condition, always eligible
                    isEligible = true;
                    break;
                }

                // Evaluate the condition using the predecessor's result
                if (results.TryGetValue(predecessorId, out string? predecessorResult))
                {
                    try
                    {
                        // Get the predecessor's output type for proper deserialization
                        plan.ExecutorOutputTypes.TryGetValue(predecessorId, out Type? predecessorOutputType);

                        // Deserialize the predecessor result to the expected type for condition evaluation
                        object? resultObject = DeserializeForCondition(predecessorResult, predecessorOutputType);
                        if (condition(resultObject))
                        {
                            isEligible = true;
                            break;
                        }
                    }
                    catch (Exception ex)
                    {
                        logger.LogWarning(ex, "Failed to evaluate condition for edge from '{PredecessorId}' to '{ExecutorId}'", predecessorId, executorInfo.ExecutorId);
                    }
                }
            }

            if (isEligible)
            {
                eligible.Add(executorInfo);
            }
            else
            {
                logger.LogExecutorSkipped(executorInfo.ExecutorId);
            }
        }

        return eligible;
    }

    /// <summary>
    /// Deserializes a JSON string result into an object for condition evaluation.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static object? DeserializeForCondition(string json, Type? targetType)
    {
        if (string.IsNullOrEmpty(json))
        {
            return null;
        }

        try
        {
            if (targetType is null)
            {
                return JsonSerializer.Deserialize<object>(json);
            }

            return JsonSerializer.Deserialize(json, targetType);
        }
        catch (JsonException)
        {
            // If it's not valid JSON, return the string as-is
            return json;
        }
    }

    private async Task<(string Id, string Result)> ExecuteExecutorWithIdAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        ILogger logger,
        DurableWorkflowCustomStatus customStatus,
        Dictionary<string, string> sharedState)
    {
        string result = await this.ExecuteExecutorAsync(context, executorInfo, input, logger, customStatus, sharedState).ConfigureAwait(true);
        return (executorInfo.ExecutorId, result);
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing known wrapper type.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing known wrapper type.")]
    private async Task<string> ExecuteExecutorAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        ILogger logger,
        DurableWorkflowCustomStatus customStatus,
        Dictionary<string, string> sharedState)
    {
        // Handle RequestPort executors by waiting for external event (human-in-the-loop)
        if (executorInfo.IsRequestPortExecutor)
        {
            return await ExecuteRequestPortAsync(context, executorInfo, input, logger, customStatus).ConfigureAwait(true);
        }

        if (!executorInfo.IsAgenticExecutor)
        {
            string executorName = WorkflowNamingHelper.GetExecutorName(executorInfo.ExecutorId);
            string triggerName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);

            // Wrap input with shared state for the activity
            ActivityInputWithState inputWithState = new()
            {
                Input = input,
                State = new Dictionary<string, string>(sharedState) // Pass a copy of the state
            };

            string wrappedInput = JsonSerializer.Serialize(inputWithState);
            return await context.CallActivityAsync<string>(triggerName, wrappedInput).ConfigureAwait(true);
        }

        return await ExecuteAgentAsync(context, executorInfo, input, logger).ConfigureAwait(true);
    }

    private static async Task<string> ExecuteRequestPortAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        ILogger logger,
        DurableWorkflowCustomStatus customStatus)
    {
        RequestPort requestPort = executorInfo.RequestPort!;
        string eventName = requestPort.Id;

        logger.LogWaitingForExternalEvent(eventName, input);

        // Set custom status to notify clients that we're waiting for external input
        // Include any accumulated events
        customStatus.PendingEvent = new(
            EventName: eventName,
            Input: input,
            RequestType: requestPort.Request.FullName ?? requestPort.Request.Name,
            ResponseType: requestPort.Response.FullName ?? requestPort.Response.Name);

        context.SetCustomStatus(customStatus);

        // Wait for the external event (human-in-the-loop)
        // The event data will be the response from the external actor
        string response = await context.WaitForExternalEvent<string>(eventName).ConfigureAwait(true);

        // Clear pending event status after receiving the event
        customStatus.PendingEvent = null;
        context.SetCustomStatus(customStatus.Events.Count > 0 ? customStatus : null);

        logger.LogReceivedExternalEvent(eventName, response);

        return response;
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

        AgentThread thread = await agent.GetNewThreadAsync();
        AgentResponse response = await agent.RunAsync(input, thread);
        return response.Text;
    }

    private static string GetExecutorInput(
        string executorId,
        string initialInput,
        Dictionary<string, string> results,
        WorkflowExecutionPlan plan)
    {
        if (!plan.Predecessors.TryGetValue(executorId, out List<string>? predecessors) || predecessors.Count == 0)
        {
            return initialInput;
        }

        if (predecessors.Count == 1)
        {
            return results.TryGetValue(predecessors[0], out string? result) ? result : initialInput;
        }

        List<string> aggregated = new(predecessors.Count);
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
        List<WorkflowExecutorInfo> lastExecutors = lastLevel.Executors;

        if (lastExecutors.Count == 1)
        {
            return results.TryGetValue(lastExecutors[0].ExecutorId, out string? singleResult) ? singleResult : string.Empty;
        }

        List<string> finalResults = new(lastExecutors.Count);
        foreach (WorkflowExecutorInfo executor in lastExecutors)
        {
            if (results.TryGetValue(executor.ExecutorId, out string? result))
            {
                finalResults.Add(result);
            }
        }

        return string.Join("\n---\n", finalResults);
    }
}
