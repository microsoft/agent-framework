// Copyright (c) Microsoft. All rights reserved.

// ConfigureAwait Usage in Orchestration Code:
// This file uses ConfigureAwait(true) because it runs within orchestration context.
// Durable Task orchestrations require deterministic replay - the same code must execute
// identically across replays. ConfigureAwait(true) ensures continuations run on the
// orchestration's synchronization context, which is essential for replay correctness.
// Using ConfigureAwait(false) here could cause non-deterministic behavior during replay.

// Superstep execution walkthrough for a workflow like below:
//
//     [A] ──► [B] ──► [C] ──► [E]          (B→D has condition: x => x.NeedsReview)
//              │               ▲
//              └──► [D] ──────┘
//
//  Superstep 1 — A runs
//    Queues before:  A:[input]                   Results: {}
//    Dispatch:       A executes, returns resultA
//    Route:          EdgeMap routes A's output → B's queue
//    Queues after:   B:[resultA]                 Results: {A: resultA}
//
//  Superstep 2 — B runs
//    Queues before:  B:[resultA]                 Results: {A: resultA}
//    Dispatch:       B executes, returns resultB (type: Order)
//    Route:          FanOutRouter sends resultB to:
//                      C's queue (unconditional)
//                      D's queue (only if resultB.NeedsReview == true)
//    Queues after:   C:[resultB], D:[resultB]    Results: {A: .., B: resultB}
//                    (D may be empty if condition was false)
//
//  Superstep 3 — C and D run in parallel
//    Queues before:  C:[resultB], D:[resultB]
//    Dispatch:       C and D execute concurrently via Task.WhenAll
//    Route:          Both route output → E's queue
//    Queues after:   E:[resultC, resultD]        Results: {.., C: resultC, D: resultD}
//
//  Superstep 4 — E runs (fan-in)
//    Queues before:  E:[resultC, resultD]        ◄── IsFanInExecutor("E") = true
//    Collect:        AggregateQueueMessages merges into JSON array ["resultC","resultD"]
//    Dispatch:       E executes with aggregated input
//    Route:          E has no successors → nothing enqueued
//    Queues after:   (all empty)                 Results: {.., E: resultE}
//
//  Superstep 5 — loop exits (no pending messages)
//    GetFinalResult returns resultE

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

// Superstep loop:
//
//  ┌───────────────┐    ┌───────────────┐    ┌───────────────────┐
//  │ Collect       │───►│ Dispatch      │───►│ Process Results   │
//  │ Executor      │    │ Executors     │    │ & Route Messages  │
//  │ Inputs        │    │ in Parallel   │    │                   │
//  └───────────────┘    └───────────────┘    └───────────────────┘
//         ▲                                           │
//         └───────────────────────────────────────────┘
//                    (repeat until no pending messages)

/// <summary>
/// Runs workflow orchestrations using message-driven superstep execution with Durable Task.
/// </summary>
internal sealed class DurableWorkflowRunner
{
    private const int MaxSupersteps = 100;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowRunner"/> class.
    /// </summary>
    /// <param name="durableOptions">The durable options containing workflow configurations.</param>
    public DurableWorkflowRunner(DurableOptions durableOptions)
    {
        ArgumentNullException.ThrowIfNull(durableOptions);

        this.Options = durableOptions.Workflows;
    }

    /// <summary>
    /// Gets the workflow options.
    /// </summary>
    private DurableWorkflowOptions Options { get; }

    /// <summary>
    /// Runs a workflow orchestration.
    /// </summary>
    /// <param name="context">The task orchestration context.</param>
    /// <param name="workflowInput">The workflow input envelope containing workflow input and metadata.</param>
    /// <param name="logger">The replay-safe logger for orchestration logging.</param>
    /// <returns>The result of the workflow execution.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the specified workflow is not found.</exception>
    internal async Task<string> RunWorkflowOrchestrationAsync(
        TaskOrchestrationContext context,
        DurableWorkflowInput<object> workflowInput,
        ILogger logger)
    {
        ArgumentNullException.ThrowIfNull(context);
        ArgumentNullException.ThrowIfNull(workflowInput);

        Workflow workflow = this.GetWorkflowOrThrow(context.Name);

        string workflowName = context.Name;
        string instanceId = context.InstanceId;
        logger.LogWorkflowStarting(workflowName, instanceId);

        WorkflowGraphInfo graphInfo = WorkflowAnalyzer.BuildGraphInfo(workflow);
        DurableEdgeMap edgeMap = new(graphInfo);

        // Extract input - the start executor determines the expected input type from its own InputTypes
        object input = workflowInput.Input;

        return await RunSuperstepLoopAsync(context, workflow, edgeMap, input, logger).ConfigureAwait(true);
    }

    private Workflow GetWorkflowOrThrow(string orchestrationName)
    {
        string workflowName = WorkflowNamingHelper.ToWorkflowName(orchestrationName);

        if (!this.Options.Workflows.TryGetValue(workflowName, out Workflow? workflow))
        {
            throw new InvalidOperationException($"Workflow '{workflowName}' not found.");
        }

        return workflow;
    }

    /// <summary>
    /// Runs the workflow execution loop using superstep-based processing.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL2026:RequiresUnreferencedCode", Justification = "Input types are preserved by the Durable Task framework's DataConverter.")]
    [UnconditionalSuppressMessage("AOT", "IL3050:RequiresDynamicCode", Justification = "Input types are preserved by the Durable Task framework's DataConverter.")]
    private static async Task<string> RunSuperstepLoopAsync(
        TaskOrchestrationContext context,
        Workflow workflow,
        DurableEdgeMap edgeMap,
        object initialInput,
        ILogger logger)
    {
        SuperstepState state = new(workflow, edgeMap);

        // Convert input to string for the message queue.
        // When DurableWorkflowInput<string> is deserialized as DurableWorkflowInput<object>,
        // the Input property becomes a JsonElement instead of a string.
        // We must extract the raw string value to avoid double-serialization.
        string inputString = initialInput switch
        {
            string s => s,
            JsonElement je when je.ValueKind == JsonValueKind.String => je.GetString() ?? string.Empty,
            _ => JsonSerializer.Serialize(initialInput)
        };

        edgeMap.EnqueueInitialInput(inputString, state.MessageQueues);

        for (int superstep = 1; superstep <= MaxSupersteps; superstep++)
        {
            List<ExecutorInput> executorInputs = CollectExecutorInputs(state, logger);
            if (executorInputs.Count == 0)
            {
                break;
            }

            logger.LogSuperstepStarting(superstep, executorInputs.Count);
            if (logger.IsEnabled(LogLevel.Debug))
            {
                logger.LogSuperstepExecutors(superstep, string.Join(", ", executorInputs.Select(e => e.ExecutorId)));
            }

            string[] results = await DispatchExecutorsInParallelAsync(context, executorInputs, state.SharedState, logger).ConfigureAwait(true);

            bool haltRequested = ProcessSuperstepResults(executorInputs, results, state, context, logger);

            if (haltRequested)
            {
                logger.LogWorkflowCompleted();
                break;
            }

            // Check if we've reached the limit and still have work remaining
            int remainingExecutors = CountRemainingExecutors(state.MessageQueues);
            if (superstep == MaxSupersteps && remainingExecutors > 0)
            {
                logger.LogWorkflowMaxSuperstepsExceeded(context.InstanceId, MaxSupersteps, remainingExecutors);
            }
        }

        // Publish final events for live streaming (skip during replay)
        if (!context.IsReplaying)
        {
            PublishEventsToCustomStatus(context, state);
        }

        string finalResult = GetFinalResult(state.LastResults);
        logger.LogWorkflowCompleted();

        // Return wrapper with both result and events so streaming clients can
        // retrieve events from SerializedOutput after the orchestration completes
        // (SerializedCustomStatus is cleared by the framework on completion).
        DurableWorkflowResult workflowResult = new()
        {
            Result = finalResult,
            Events = state.AccumulatedEvents
        };

        return JsonSerializer.Serialize(workflowResult, DurableWorkflowJsonContext.Default.DurableWorkflowResult);
    }

    /// <summary>
    /// Counts the number of executors with pending messages in their queues.
    /// </summary>
    private static int CountRemainingExecutors(Dictionary<string, Queue<DurableMessageEnvelope>> messageQueues)
    {
        return messageQueues.Count(kvp => kvp.Value.Count > 0);
    }

    private static async Task<string[]> DispatchExecutorsInParallelAsync(
        TaskOrchestrationContext context,
        List<ExecutorInput> executorInputs,
        Dictionary<string, string> sharedState,
        ILogger logger)
    {
        Task<string>[] dispatchTasks = executorInputs
            .Select(input => DurableExecutorDispatcher.DispatchAsync(context, input.Info, input.Envelope, sharedState, logger))
            .ToArray();

        return await Task.WhenAll(dispatchTasks).ConfigureAwait(true);
    }

    /// <summary>
    /// Holds state that accumulates and changes across superstep iterations during workflow execution.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <c>MessageQueues</c> starts with one entry (the start executor's queue, seeded by
    /// <see cref="DurableEdgeMap.EnqueueInitialInput"/>). After each superstep, <c>RouteOutputToSuccessors</c>
    /// adds entries for successor executors that receive routed messages. Queues are drained during
    /// <c>CollectExecutorInputs</c>; empty queues are skipped.
    /// </para>
    /// <para>
    /// <c>LastResults</c> is updated after every superstep with the result of each executor that ran.
    /// At workflow completion, the last non-empty value is returned as the workflow's final result.
    /// </para>
    /// </remarks>
    private sealed class SuperstepState
    {
        public SuperstepState(Workflow workflow, DurableEdgeMap edgeMap)
        {
            this.EdgeMap = edgeMap;
            this.ExecutorBindings = workflow.ReflectExecutors();
        }

        public DurableEdgeMap EdgeMap { get; }

        public Dictionary<string, ExecutorBinding> ExecutorBindings { get; }

        public Dictionary<string, Queue<DurableMessageEnvelope>> MessageQueues { get; } = [];

        public Dictionary<string, string> LastResults { get; } = [];

        /// <summary>
        /// Shared state dictionary across supersteps (scope-prefixed key -> serialized value).
        /// </summary>
        public Dictionary<string, string> SharedState { get; } = [];

        /// <summary>
        /// Accumulated workflow events for custom status (streaming consumption).
        /// </summary>
        public List<string> AccumulatedEvents { get; } = [];
    }

    /// <summary>
    /// Represents prepared input for an executor ready for dispatch.
    /// </summary>
    private sealed record ExecutorInput(string ExecutorId, DurableMessageEnvelope Envelope, WorkflowExecutorInfo Info);

    /// <summary>
    /// Collects inputs for all active executors, applying Fan-In aggregation where needed.
    /// </summary>
    private static List<ExecutorInput> CollectExecutorInputs(
        SuperstepState state,
        ILogger logger)
    {
        List<ExecutorInput> inputs = [];

        // Only process queues that have pending messages
        foreach ((string executorId, Queue<DurableMessageEnvelope> queue) in state.MessageQueues
            .Where(kvp => kvp.Value.Count > 0))
        {
            DurableMessageEnvelope envelope = GetNextEnvelope(executorId, queue, state.EdgeMap, logger);
            WorkflowExecutorInfo executorInfo = CreateExecutorInfo(executorId, state.ExecutorBindings);

            inputs.Add(new ExecutorInput(executorId, envelope, executorInfo));
        }

        return inputs;
    }

    private static DurableMessageEnvelope GetNextEnvelope(
        string executorId,
        Queue<DurableMessageEnvelope> queue,
        DurableEdgeMap edgeMap,
        ILogger logger)
    {
        bool shouldAggregate = edgeMap.IsFanInExecutor(executorId) && queue.Count > 1;

        return shouldAggregate
            ? AggregateQueueMessages(queue, executorId, logger)
            : queue.Dequeue();
    }

    /// <summary>
    /// Aggregates all messages in a queue into a JSON array for Fan-In executors.
    /// </summary>
    private static DurableMessageEnvelope AggregateQueueMessages(
        Queue<DurableMessageEnvelope> queue,
        string executorId,
        ILogger logger)
    {
        List<string> messages = [];
        List<string> sourceIds = [];

        while (queue.Count > 0)
        {
            DurableMessageEnvelope envelope = queue.Dequeue();
            messages.Add(envelope.Message);

            if (envelope.SourceExecutorId is not null)
            {
                sourceIds.Add(envelope.SourceExecutorId);
            }
        }

        if (logger.IsEnabled(LogLevel.Debug))
        {
            logger.LogFanInAggregated(executorId, messages.Count, string.Join(", ", sourceIds));
        }

        return new DurableMessageEnvelope
        {
            Message = SerializeToJsonArray(messages),
            InputTypeName = typeof(string[]).FullName,
            SourceExecutorId = sourceIds.Count > 0 ? string.Join(",", sourceIds) : null
        };
    }

    /// <summary>
    /// Processes results from a superstep, updating state and routing messages to successors.
    /// </summary>
    /// <returns><c>true</c> if a halt was requested by any executor; otherwise, <c>false</c>.</returns>
    private static bool ProcessSuperstepResults(
        List<ExecutorInput> inputs,
        string[] rawResults,
        SuperstepState state,
        TaskOrchestrationContext context,
        ILogger logger)
    {
        bool haltRequested = false;

        for (int i = 0; i < inputs.Count; i++)
        {
            string executorId = inputs[i].ExecutorId;
            ExecutorResultInfo resultInfo = ParseActivityResult(rawResults[i]);

            logger.LogExecutorResultReceived(executorId, resultInfo.Result.Length, resultInfo.SentMessages.Count);

            state.LastResults[executorId] = resultInfo.Result;

            // Merge state updates from activity into shared state
            MergeStateUpdates(state, resultInfo.StateUpdates, resultInfo.ClearedScopes);

            // Accumulate events for custom status (streaming)
            state.AccumulatedEvents.AddRange(resultInfo.Events);

            // Check for halt request
            haltRequested |= resultInfo.HaltRequested;

            // Publish events for live streaming (skip during replay)
            if (!context.IsReplaying)
            {
                PublishEventsToCustomStatus(context, state);
            }

            RouteOutputToSuccessors(executorId, resultInfo.Result, resultInfo.SentMessages, state, logger);
        }

        return haltRequested;
    }

    /// <summary>
    /// Merges state updates from an executor into the shared state.
    /// </summary>
    private static void MergeStateUpdates(
        SuperstepState state,
        Dictionary<string, string?> stateUpdates,
        List<string> clearedScopes)
    {
        Dictionary<string, string> shared = state.SharedState;

        ApplyClearedScopes(shared, clearedScopes);

        // Apply individual state updates
        foreach ((string key, string? value) in stateUpdates)
        {
            if (value is null)
            {
                shared.Remove(key);
            }
            else
            {
                shared[key] = value;
            }
        }
    }

    /// <summary>
    /// Removes all keys belonging to the specified scopes from the shared state dictionary.
    /// </summary>
    private static void ApplyClearedScopes(Dictionary<string, string> shared, List<string> clearedScopes)
    {
        if (clearedScopes.Count == 0 || shared.Count == 0)
        {
            return;
        }

        List<string> keysToRemove = [];

        foreach (string clearedScope in clearedScopes)
        {
            string scopePrefix = string.Concat(clearedScope, ":");
            keysToRemove.Clear();

            foreach (string key in shared.Keys)
            {
                if (key.StartsWith(scopePrefix, StringComparison.Ordinal))
                {
                    keysToRemove.Add(key);
                }
            }

            foreach (string key in keysToRemove)
            {
                shared.Remove(key);
            }

            if (shared.Count == 0)
            {
                break;
            }
        }
    }

    /// <summary>
    /// Publishes accumulated workflow events to the orchestration's custom status,
    /// making them available to <see cref="DurableStreamingWorkflowRun"/> for live streaming.
    /// </summary>
    /// <remarks>
    /// Custom status is the only orchestration metadata readable by external clients while
    /// the orchestration is still running. It is cleared by the framework on completion,
    /// so events are also included in <see cref="DurableWorkflowResult"/> for final retrieval.
    /// </remarks>
    private static void PublishEventsToCustomStatus(TaskOrchestrationContext context, SuperstepState state)
    {
        DurableWorkflowCustomStatus customStatus = new()
        {
            Events = state.AccumulatedEvents
        };

        // Pass the object directly — the framework's DataConverter handles serialization.
        // Pre-serializing would cause double-serialization (string wrapped in JSON quotes).
        context.SetCustomStatus(customStatus);
    }

    /// <summary>
    /// Routes executor output (explicit messages or return value) to successor executors.
    /// </summary>
    private static void RouteOutputToSuccessors(
        string executorId,
        string result,
        List<TypedPayload> sentMessages,
        SuperstepState state,
        ILogger logger)
    {
        if (sentMessages.Count > 0)
        {
            // Only route messages that have content
            foreach (TypedPayload message in sentMessages.Where(m => !string.IsNullOrEmpty(m.Data)))
            {
                state.EdgeMap.RouteMessage(executorId, message.Data!, message.TypeName, state.MessageQueues, logger);
            }

            return;
        }

        if (!string.IsNullOrEmpty(result))
        {
            state.EdgeMap.RouteMessage(executorId, result, inputTypeName: null, state.MessageQueues, logger);
        }
    }

    /// <summary>
    /// Serializes a list of messages into a JSON array.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing string array.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing string array.")]
    private static string SerializeToJsonArray(List<string> messages)
    {
        return JsonSerializer.Serialize(messages);
    }

    /// <summary>
    /// Creates a <see cref="WorkflowExecutorInfo"/> for the given executor ID.
    /// </summary>
    /// <exception cref="InvalidOperationException">Thrown when the executor ID is not found in bindings.</exception>
    private static WorkflowExecutorInfo CreateExecutorInfo(
        string executorId,
        Dictionary<string, ExecutorBinding> executorBindings)
    {
        if (!executorBindings.TryGetValue(executorId, out ExecutorBinding? binding))
        {
            throw new InvalidOperationException($"Executor '{executorId}' not found in workflow bindings.");
        }

        bool isAgentic = WorkflowAnalyzer.IsAgentExecutorType(binding.ExecutorType);
        RequestPort? requestPort = (binding is RequestPortBinding rpb) ? rpb.Port : null;
        Workflow? subWorkflow = (binding is SubworkflowBinding swb) ? swb.WorkflowInstance : null;

        return new WorkflowExecutorInfo(executorId, isAgentic, requestPort, subWorkflow);
    }

    /// <summary>
    /// Returns the last non-empty result from executed steps, or empty string if none.
    /// </summary>
    private static string GetFinalResult(Dictionary<string, string> lastResults)
    {
        return lastResults.Values.LastOrDefault(value => !string.IsNullOrEmpty(value)) ?? string.Empty;
    }

    /// <summary>
    /// Output from an executor invocation, including its result,
    /// messages, state updates, and emitted workflow events.
    /// </summary>
    private sealed record ExecutorResultInfo(
        string Result,
        List<TypedPayload> SentMessages,
        Dictionary<string, string?> StateUpdates,
        List<string> ClearedScopes,
        List<string> Events,
        bool HaltRequested);

    /// <summary>
    /// Parses the raw activity result to extract result, messages, events, and state updates.
    /// </summary>
    private static ExecutorResultInfo ParseActivityResult(string rawResult)
    {
        if (string.IsNullOrEmpty(rawResult))
        {
            return new ExecutorResultInfo(rawResult, [], [], [], [], false);
        }

        try
        {
            DurableActivityOutput? output = JsonSerializer.Deserialize(
                rawResult,
                DurableWorkflowJsonContext.Default.DurableActivityOutput);

            if (output is null || !HasMeaningfulContent(output))
            {
                return new ExecutorResultInfo(rawResult, [], [], [], [], false);
            }

            return new ExecutorResultInfo(
                output.Result ?? string.Empty,
                output.SentMessages,
                output.StateUpdates,
                output.ClearedScopes,
                output.Events,
                output.HaltRequested);
        }
        catch (JsonException)
        {
            return new ExecutorResultInfo(rawResult, [], [], [], [], false);
        }
    }

    /// <summary>
    /// Determines whether the activity output contains meaningful content.
    /// </summary>
    /// <remarks>
    /// Distinguishes actual activity output from arbitrary JSON that deserialized
    /// successfully but with all default/empty values.
    /// </remarks>
    private static bool HasMeaningfulContent(DurableActivityOutput output)
    {
        return output.Result is not null
            || output.SentMessages.Count > 0
            || output.Events.Count > 0
            || output.StateUpdates.Count > 0
            || output.ClearedScopes.Count > 0
            || output.HaltRequested;
    }
}
