// Copyright (c) Microsoft. All rights reserved.

// ConfigureAwait Usage in Orchestration Code:
// This file uses ConfigureAwait(true) because it runs within orchestration context.
// Durable Task orchestrations require deterministic replay - the same code must execute
// identically across replays. ConfigureAwait(true) ensures continuations run on the
// orchestration's synchronization context, which is essential for replay correctness.
// Using ConfigureAwait(false) here could cause non-deterministic behavior during replay.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

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
    internal DurableWorkflowRunner(DurableOptions durableOptions)
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

        // Convert input to string for the message queue - serialize if not already a string
        string inputString = initialInput is string s ? s : JsonSerializer.Serialize(initialInput);

        // Pass null for inputTypeName - the start executor determines its input type from its own InputTypes
        edgeMap.EnqueueInput(inputString, inputTypeName: null, state.MessageQueues);

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

            string[] results = await DispatchExecutorsInParallelAsync(context, executorInputs, logger).ConfigureAwait(true);

            ProcessSuperstepResults(executorInputs, results, state, logger);

            // Check if we've reached the limit and still have work remaining
            if (superstep == MaxSupersteps)
            {
                int remainingExecutors = CountRemainingExecutors(state.MessageQueues);
                if (remainingExecutors > 0)
                {
                    logger.LogWorkflowMaxSuperstepsExceeded(context.InstanceId, MaxSupersteps, remainingExecutors);
                }
            }
        }

        string finalResult = GetFinalResult(state.LastResults);
        logger.LogWorkflowCompleted();

        return finalResult;
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
        ILogger logger)
    {
        Task<string>[] dispatchTasks = executorInputs
            .Select(input => DurableExecutorDispatcher.DispatchAsync(context, input.Info, input.Envelope, logger))
            .ToArray();

        return await Task.WhenAll(dispatchTasks).ConfigureAwait(true);
    }

    /// <summary>
    /// Holds state that accumulates and changes across superstep iterations during workflow execution.
    /// </summary>
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
    private static void ProcessSuperstepResults(
        List<ExecutorInput> inputs,
        string[] rawResults,
        SuperstepState state,
        ILogger logger)
    {
        for (int i = 0; i < inputs.Count; i++)
        {
            string executorId = inputs[i].ExecutorId;
            (string result, List<SentMessageInfo> sentMessages) = ParseActivityResult(rawResults[i]);

            logger.LogExecutorResultReceived(executorId, result.Length, sentMessages.Count);

            state.LastResults[executorId] = result;
            RouteOutputToSuccessors(executorId, result, sentMessages, state, logger);
        }
    }

    /// <summary>
    /// Routes executor output (explicit messages or return value) to successor executors.
    /// </summary>
    private static void RouteOutputToSuccessors(
        string executorId,
        string result,
        List<SentMessageInfo> sentMessages,
        SuperstepState state,
        ILogger logger)
    {
        if (sentMessages.Count > 0)
        {
            // Only route messages that have content
            foreach (SentMessageInfo message in sentMessages.Where(m => !string.IsNullOrEmpty(m.Message)))
            {
                state.EdgeMap.RouteMessage(executorId, message.Message!, message.TypeName, state.MessageQueues, logger);
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
    /// Parses the raw activity result to extract the result string and any sent messages.
    /// </summary>
    private static (string Result, List<SentMessageInfo> SentMessages) ParseActivityResult(string rawResult)
    {
        if (string.IsNullOrEmpty(rawResult))
        {
            return (rawResult, []);
        }

        try
        {
            DurableActivityOutput? output = JsonSerializer.Deserialize(
                rawResult,
                DurableWorkflowJsonContext.Default.DurableActivityOutput);

            if (output is null || !HasMeaningfulContent(output))
            {
                return (rawResult, []);
            }

            return (output.Result ?? string.Empty, output.SentMessages);
        }
        catch (JsonException)
        {
            return (rawResult, []);
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
        return output.Result is not null || output.SentMessages.Count > 0;
    }
}
