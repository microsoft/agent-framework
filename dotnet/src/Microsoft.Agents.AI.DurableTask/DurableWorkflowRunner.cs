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

        // Use message-driven execution for all workflows
        // This approach naturally handles both DAGs and cyclic workflows
        return await this.ExecuteMessageDrivenAsync(context, workflow, plan, initialInput, logger).ConfigureAwait(true);
    }

    /// <summary>
    /// Executes a workflow using message-driven execution.
    /// Messages are routed through edges dynamically, naturally supporting both DAGs and cycles.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private async Task<string> ExecuteMessageDrivenAsync(
        TaskOrchestrationContext context,
        Workflow workflow,
        WorkflowExecutionPlan plan,
        string initialInput,
        ILogger logger)
    {
        const int MaxSupersteps = 100;

        // Message queues per executor - stores (message, inputTypeName) tuples
        Dictionary<string, Queue<(string Message, string? InputTypeName)>> messageQueues = [];

        // Last result from each executor (for edge condition evaluation and final result)
        Dictionary<string, string> lastResults = [];

        // Track accumulated events and shared state
        DurableWorkflowCustomStatus customStatus = new();
        Dictionary<string, string> sharedState = [];

        // Get executor bindings for creating WorkflowExecutorInfo
        Dictionary<string, ExecutorBinding> executorBindings = workflow.ReflectExecutors();

        // Initialize: queue input to start executor (initial input is a string)
        EnqueueMessage(messageQueues, plan.StartExecutorId, initialInput, typeof(string).FullName);

        int superstep = 0;
        bool haltRequested = false;
        string? finalOutput = null;

        while (superstep < MaxSupersteps && !haltRequested)
        {
            superstep++;

            // Collect all executors with pending messages
            List<string> activeExecutors = messageQueues
                .Where(kv => kv.Value.Count > 0)
                .Select(kv => kv.Key)
                .ToList();

            if (activeExecutors.Count == 0)
            {
                break; // No more work
            }

#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates, expensive evaluation
            logger.LogDebug("Superstep {Step}: {Count} active executor(s): {Executors}",
                superstep, activeExecutors.Count, string.Join(", ", activeExecutors));
#pragma warning restore CA1848, CA1873

            // Process each active executor
            foreach (string executorId in activeExecutors)
            {
                Queue<(string Message, string? InputTypeName)> queue = messageQueues[executorId];

                // Process all messages for this executor in this superstep
                while (queue.Count > 0)
                {
                    (string input, string? inputTypeName) = queue.Dequeue();

                    // Create executor info
                    WorkflowExecutorInfo executorInfo = CreateExecutorInfo(executorId, executorBindings);

                    // Execute the activity with type information
                    string rawResult = await this.ExecuteExecutorAsync(
                        context, executorInfo, input, inputTypeName, logger, customStatus, sharedState).ConfigureAwait(true);

                    (string result, List<SentMessageInfo> sentMessages) = UnwrapActivityResult(rawResult, customStatus, sharedState);
                    lastResults[executorId] = result;

                    // Check for explicit halt request (via RequestHaltAsync)
                    if (CheckForHalt(customStatus, executorId))
                    {
                        haltRequested = true;
                        finalOutput = result;
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
                        logger.LogDebug("Halt requested by executor {ExecutorId}", executorId);
#pragma warning restore CA1848, CA1873
                        break;
                    }

                    // Route messages sent via SendMessageAsync (takes priority for void-returning executors)
                    if (sentMessages.Count > 0)
                    {
                        foreach (SentMessageInfo sentMessage in sentMessages)
                        {
                            if (!string.IsNullOrEmpty(sentMessage.Message))
                            {
                                // Route to successors with the sent message's type
                                RouteMessageToSuccessors(
                                    executorId, sentMessage.Message, sentMessage.TypeName, plan, messageQueues, logger);
                            }
                        }
                    }
                    else if (!string.IsNullOrEmpty(result))
                    {
                        // Route executor's return value to successor executors via edges (for non-void executors)
                        RouteMessageToSuccessors(
                            executorId, result, plan, messageQueues, logger);
                    }
                }

                if (haltRequested)
                {
                    break;
                }
            }

            UpdateCustomStatus(context, customStatus);
        }

        if (superstep >= MaxSupersteps)
        {
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
            logger.LogWarning("Workflow reached maximum superstep limit ({MaxSteps})", MaxSupersteps);
#pragma warning restore CA1848, CA1873
        }

        // Return final output or last result from output executors
        return finalOutput ?? GetMessageDrivenFinalResult(workflow, lastResults, customStatus);
    }

    /// <summary>
    /// Enqueues a message to an executor's message queue with type information.
    /// </summary>
    private static void EnqueueMessage(
        Dictionary<string, Queue<(string Message, string? InputTypeName)>> queues,
        string executorId,
        string message,
        string? inputTypeName)
    {
        if (!queues.TryGetValue(executorId, out Queue<(string, string?)>? queue))
        {
            queue = new Queue<(string, string?)>();
            queues[executorId] = queue;
        }

        queue.Enqueue((message, inputTypeName));
    }

    /// <summary>
    /// Creates a WorkflowExecutorInfo for the given executor ID.
    /// </summary>
    private static WorkflowExecutorInfo CreateExecutorInfo(
        string executorId,
        Dictionary<string, ExecutorBinding> executorBindings)
    {
        if (!executorBindings.TryGetValue(executorId, out ExecutorBinding? binding))
        {
            throw new InvalidOperationException($"Executor '{executorId}' not found in workflow bindings.");
        }

        bool isAgentic = WorkflowHelper.IsAgentExecutorType(binding.ExecutorType);
        RequestPort? requestPort = (binding is RequestPortBinding rpb) ? rpb.Port : null;

        return new WorkflowExecutorInfo(executorId, isAgentic, requestPort);
    }

    /// <summary>
    /// Checks if the workflow should halt based on halt request events.
    /// Note: YieldOutputAsync does NOT halt the workflow - it just yields intermediate output.
    /// Only explicit RequestHaltAsync calls should halt the workflow.
    /// </summary>
    private static bool CheckForHalt(
        DurableWorkflowCustomStatus customStatus,
        string executorId)
    {
        // Look for explicit halt request events from this executor
        for (int i = customStatus.Events.Count - 1; i >= 0; i--)
        {
            string eventJson = customStatus.Events[i];

            // Check for DurableHaltRequestedEvent - this is the ONLY event that should halt
            if (eventJson.Contains("DurableHaltRequestedEvent", StringComparison.Ordinal) &&
                eventJson.Contains(executorId, StringComparison.Ordinal))
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Routes a message through edges to successor executors.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static void RouteMessageToSuccessors(
        string sourceId,
        string message,
        WorkflowExecutionPlan plan,
        Dictionary<string, Queue<(string Message, string? InputTypeName)>> messageQueues,
        ILogger logger)
    {
        if (!plan.Successors.TryGetValue(sourceId, out List<string>? successors))
        {
            return; // No outgoing edges
        }

        // Get the output type of the source executor to pass as input type to successors
        plan.ExecutorOutputTypes.TryGetValue(sourceId, out Type? sourceOutputType);
        string? inputTypeName = sourceOutputType?.FullName;

        foreach (string sinkId in successors)
        {
            // Check edge condition
            if (plan.EdgeConditions.TryGetValue((sourceId, sinkId), out Func<object?, bool>? condition)
                && condition is not null)
            {
                try
                {
                    // Deserialize the message for condition evaluation
                    object? messageObj = DeserializeForCondition(message, sourceOutputType);

                    if (!condition(messageObj))
                    {
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
                        logger.LogDebug("Edge {Source} -> {Sink}: condition returned false, skipping",
                            sourceId, sinkId);
#pragma warning restore CA1848, CA1873
                        continue;
                    }
                }
                catch (Exception ex)
                {
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
                    logger.LogWarning(ex, "Failed to evaluate condition for edge {Source} -> {Sink}, skipping",
                        sourceId, sinkId);
#pragma warning restore CA1848, CA1873
                    continue;
                }
            }

            // Queue message to successor with type information
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
            logger.LogDebug("Edge {Source} -> {Sink}: routing message", sourceId, sinkId);
#pragma warning restore CA1848, CA1873
            EnqueueMessage(messageQueues, sinkId, message, inputTypeName);
        }
    }

    /// <summary>
    /// Routes a message through edges to successor executors, with an explicit type name for the message.
    /// Used for messages sent via SendMessageAsync.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2057", Justification = "Type resolution for workflow message types.")]
    private static void RouteMessageToSuccessors(
        string sourceId,
        string message,
        string? explicitTypeName,
        WorkflowExecutionPlan plan,
        Dictionary<string, Queue<(string Message, string? InputTypeName)>> messageQueues,
        ILogger logger)
    {
        if (!plan.Successors.TryGetValue(sourceId, out List<string>? successors))
        {
            return; // No outgoing edges
        }

        // Use explicit type name if provided, otherwise fall back to executor output type
        string? inputTypeName = explicitTypeName;
        Type? messageType = null;

        if (!string.IsNullOrEmpty(explicitTypeName))
        {
            messageType = Type.GetType(explicitTypeName);
        }

        if (messageType is null && plan.ExecutorOutputTypes.TryGetValue(sourceId, out Type? sourceOutputType))
        {
            messageType = sourceOutputType;
            inputTypeName = sourceOutputType?.FullName;
        }

        foreach (string sinkId in successors)
        {
            // Check edge condition
            if (plan.EdgeConditions.TryGetValue((sourceId, sinkId), out Func<object?, bool>? condition)
                && condition is not null)
            {
                try
                {
                    // Deserialize the message for condition evaluation
                    object? messageObj = DeserializeForCondition(message, messageType);

                    if (!condition(messageObj))
                    {
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
                        logger.LogDebug("Edge {Source} -> {Sink}: condition returned false, skipping",
                            sourceId, sinkId);
#pragma warning restore CA1848, CA1873
                        continue;
                    }
                }
                catch (Exception ex)
                {
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
                    logger.LogWarning(ex, "Failed to evaluate condition for edge {Source} -> {Sink}, skipping",
                        sourceId, sinkId);
#pragma warning restore CA1848, CA1873
                    continue;
                }
            }

            // Queue message to successor with type information
#pragma warning disable CA1848, CA1873 // Use LoggerMessage delegates
            logger.LogDebug("Edge {Source} -> {Sink}: routing sent message (type: {TypeName})", sourceId, sinkId, inputTypeName);
#pragma warning restore CA1848, CA1873
            EnqueueMessage(messageQueues, sinkId, message, inputTypeName);
        }
    }

    /// <summary>
    /// Gets the final result for a message-driven workflow execution.
    /// Checks yielded outputs first (from YieldOutputAsync calls), then falls back to executor results.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing event types.")]
    private static string GetMessageDrivenFinalResult(
        Workflow workflow,
        Dictionary<string, string> lastResults,
        DurableWorkflowCustomStatus customStatus)
    {
        // First, check for yielded outputs from YieldOutputAsync calls (most recent first)
        // These take priority as they represent explicit workflow outputs
        string? yieldedOutput = GetLastYieldedOutput(customStatus);
        if (!string.IsNullOrEmpty(yieldedOutput))
        {
            return yieldedOutput;
        }

        HashSet<string> outputExecutors = workflow.ReflectOutputExecutors();

        // If specific output executors are defined, use their results
        if (outputExecutors.Count > 0)
        {
            List<string> outputResults = [];
            foreach (string outputExecutorId in outputExecutors)
            {
                if (lastResults.TryGetValue(outputExecutorId, out string? result) && !string.IsNullOrEmpty(result))
                {
                    outputResults.Add(result);
                }
            }

            if (outputResults.Count > 0)
            {
                return outputResults.Count == 1
                    ? outputResults[0]
                    : string.Join("\n---\n", outputResults);
            }
        }

        // Otherwise, return the last non-empty result from any executor
        return lastResults.Values.LastOrDefault(v => !string.IsNullOrEmpty(v)) ?? string.Empty;
    }

    /// <summary>
    /// Extracts the most recent yielded output from the custom status events.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing event types.")]
    private static string? GetLastYieldedOutput(DurableWorkflowCustomStatus customStatus)
    {
        // Look for DurableYieldedOutputEvent in events (most recent first)
        for (int i = customStatus.Events.Count - 1; i >= 0; i--)
        {
            string eventJson = customStatus.Events[i];

            if (eventJson.Contains("DurableYieldedOutputEvent", StringComparison.Ordinal))
            {
                try
                {
                    // Parse the wrapper to get the inner Data
                    using JsonDocument doc = JsonDocument.Parse(eventJson);
                    if (doc.RootElement.TryGetProperty("Data", out JsonElement dataElement))
                    {
                        string? dataJson = dataElement.GetString();
                        if (dataJson is not null)
                        {
                            using JsonDocument dataDoc = JsonDocument.Parse(dataJson);
                            if (dataDoc.RootElement.TryGetProperty("Output", out JsonElement outputElement))
                            {
                                // The output could be a string or a serialized object
                                return outputElement.ValueKind == JsonValueKind.String
                                    ? outputElement.GetString()
                                    : outputElement.GetRawText();
                            }
                        }
                    }
                }
                catch (JsonException)
                {
                    // Continue to next event if parsing fails
                }
            }
        }

        return null;
    }

    /// <summary>
    /// Unwraps an activity result, extracting state updates, events, sent messages, and returning the actual result.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing known wrapper type.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing known wrapper type.")]
    private static (string Result, List<SentMessageInfo> SentMessages) UnwrapActivityResult(
        string rawResult,
        DurableWorkflowCustomStatus customStatus,
        Dictionary<string, string> sharedState)
    {
        if (string.IsNullOrEmpty(rawResult))
        {
            return (rawResult, []);
        }

        try
        {
            // Try to deserialize as DurableActivityOutput
            DurableActivityOutput? output = JsonSerializer.Deserialize<DurableActivityOutput>(rawResult);

            // Check if this is actually a DurableActivityOutput (has Result property set or state updates or sent messages)
            // This distinguishes it from other JSON objects that would deserialize with default/empty values
            if (output is not null && (output.Result is not null || output.StateUpdates.Count > 0 || output.ClearedScopes.Count > 0 || output.Events.Count > 0 || output.SentMessages.Count > 0))
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

                return (output.Result ?? string.Empty, output.SentMessages);
            }
        }
        catch (JsonException)
        {
            // Not a wrapped result, return as-is
        }

        return (rawResult, []);
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
    /// Wrapper for activity input that includes shared state and type information.
    /// </summary>
    internal sealed class ActivityInputWithState
    {
        /// <summary>
        /// Gets or sets the serialized executor input.
        /// </summary>
        public string? Input { get; set; }

        /// <summary>
        /// Gets or sets the assembly-qualified type name of the input, used for proper deserialization.
        /// </summary>
        public string? InputTypeName { get; set; }

        /// <summary>
        /// Gets or sets the shared state dictionary.
        /// </summary>
        public Dictionary<string, string> State { get; set; } = [];
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

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing known wrapper type.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing known wrapper type.")]
    private async Task<string> ExecuteExecutorAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        string? inputTypeName,
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

            // Wrap input with shared state and type information for the activity
            ActivityInputWithState inputWithState = new()
            {
                Input = input,
                InputTypeName = inputTypeName,
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
}
