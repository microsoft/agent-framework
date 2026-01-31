// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

#pragma warning disable CA1848 // Use LoggerMessage delegates
#pragma warning disable CA1873 // Expensive evaluation

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents the custom status set when the orchestration is waiting for an external event.
/// </summary>
/// <param name="EventName">The name of the event being waited for (the RequestPort ID).</param>
/// <param name="Input">The serialized input data that was passed to the RequestPort.</param>
/// <param name="RequestType">The full type name of the request type.</param>
/// <param name="ResponseType">The full type name of the expected response type.</param>
/// <remarks>
/// <para>
/// This status is set when a workflow reaches a human-in-the-loop point (RequestPort executor).
/// External actors can query this status to:
/// </para>
/// <list type="bullet">
/// <item><description>Discover which event name to raise</description></item>
/// <item><description>See the input/context that prompted the request</description></item>
/// <item><description>Understand the expected request and response types for proper serialization</description></item>
/// </list>
/// </remarks>
internal sealed record PendingExternalEventStatus(
    string EventName,
    string Input,
    string RequestType,
    string ResponseType);

/// <summary>
/// Represents the complete custom status for a durable workflow orchestration.
/// </summary>
/// <remarks>
/// <para>
/// This status object is serialized and stored as the orchestration's custom status,
/// making it visible in the Durable Task dashboard and queryable via the client API.
/// </para>
/// <para>
/// It serves two primary purposes:
/// </para>
/// <list type="bullet">
/// <item><description>
/// <strong>Event Accumulation:</strong> Collects workflow events (yields, halts, etc.) emitted
/// by executors during the workflow run for final result determination.
/// </description></item>
/// <item><description>
/// <strong>HITL Status:</strong> Indicates when the workflow is waiting for external input,
/// including the event name to raise and context about the request.
/// </description></item>
/// </list>
/// </remarks>
internal sealed class DurableWorkflowCustomStatus
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
/// <remarks>
/// <para>
/// <strong>Architecture Overview:</strong>
/// </para>
/// <para>
/// The DurableWorkflowRunner implements a message-driven execution model that naturally supports
/// both directed acyclic graphs (DAGs) and cyclic workflows. Each executor in the workflow is
/// treated as a message processor that receives input, executes logic, and routes output to successors.
/// </para>
/// <para>
/// <strong>Execution Flow:</strong>
/// </para>
/// <list type="number">
/// <item>
/// <description>
/// <strong>Initialization:</strong> The workflow starts by queueing the initial input to the start executor.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Superstep Processing:</strong> In each superstep, all executors with pending messages are processed.
/// This continues until no messages remain or a halt is requested.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Activity Execution:</strong> Each executor runs as a Durable Task activity. The activity receives
/// wrapped input containing the message, type information, and shared workflow state.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Result Unwrapping:</strong> Activity results are unwrapped to extract the actual result,
/// state updates, workflow events, and any messages sent via <c>SendMessageAsync</c>.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Message Routing:</strong> Results are routed to successor executors based on workflow edges.
/// Edge conditions are evaluated to determine if a message should be forwarded.
/// </description>
/// </item>
/// </list>
/// <para>
/// <strong>Key Data Structures:</strong>
/// </para>
/// <list type="bullet">
/// <item>
/// <description>
/// <strong>Message Queues:</strong> Each executor has a queue of pending messages (input + type information).
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Shared State:</strong> A dictionary of scope-prefixed key-value pairs shared across executors.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Custom Status:</strong> Tracks workflow events and pending external event info for observability.
/// </description>
/// </item>
/// </list>
/// <para>
/// <strong>Executor Types:</strong>
/// </para>
/// <list type="bullet">
/// <item>
/// <description>
/// <strong>Regular Executors:</strong> Run as Durable Task activities. Can return values or use <c>SendMessageAsync</c>.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Agent Executors:</strong> AI agents that run via Durable Entities for stateful conversations.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>Request Port Executors:</strong> Human-in-the-loop points that wait for external events.
/// </description>
/// </item>
/// </list>
/// <para>
/// <strong>Input/Output Flow:</strong>
/// </para>
/// <code>
/// ┌─────────────────────────────────────────────────────────────────────────────────┐
/// │ Orchestrator (DurableWorkflowRunner)                                            │
/// │                                                                                 │
/// │  ┌─────────────┐    ActivityInputWithState     ┌─────────────────────────────┐  │
/// │  │ Message     │ ──────────────────────────▶  │ Activity                     │  │
/// │  │ Queue       │    {Input, InputTypeName,    │ (ExecuteActivityAsync)       │  │
/// │  │             │     State}                   │                              │  │
/// │  │             │                              │ - Deserialize input          │  │
/// │  │             │                              │ - Execute executor logic     │  │
/// │  │             │                              │ - Collect state updates      │  │
/// │  │             │    DurableActivityOutput     │ - Collect events             │  │
/// │  │             │ ◀──────────────────────────  │ - Collect sent messages      │  │
/// │  └─────────────┘    {Result, StateUpdates,    └─────────────────────────────┘  │
/// │         │            ClearedScopes, Events,                                     │
/// │         │            SentMessages}                                              │
/// │         ▼                                                                       │
/// │  ┌─────────────┐                                                                │
/// │  │ Route to    │ ── Evaluate edge conditions ──▶ Queue to successor executors  │
/// │  │ Successors  │                                                                │
/// │  └─────────────┘                                                                │
/// └─────────────────────────────────────────────────────────────────────────────────┘
/// </code>
/// </remarks>
internal class DurableWorkflowRunner
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

        return await this.ExecuteWorkflowAsync(context, workflow, input, logger).ConfigureAwait(true);
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
    /// Serializes a list of strings to JSON using source-generated serialization.
    /// </summary>
    protected static string SerializeToJson(List<string> values)
    {
        return JsonSerializer.Serialize(values, DurableWorkflowJsonContext.Default.ListString);
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

    /// <summary>
    /// Executes a workflow by building an execution plan and delegating to message-driven execution.
    /// </summary>
    /// <param name="context">The Durable Task orchestration context.</param>
    /// <param name="workflow">The workflow definition to execute.</param>
    /// <param name="initialInput">The initial input string to pass to the start executor.</param>
    /// <param name="logger">The replay-safe logger for orchestration logging.</param>
    /// <returns>The final result of the workflow execution.</returns>
    /// <remarks>
    /// This method serves as the entry point for workflow execution after the workflow has been
    /// resolved from the orchestration name. It builds a <see cref="WorkflowExecutionPlan"/> that
    /// contains the graph structure (successors, predecessors), edge conditions, and executor
    /// output types needed for message routing.
    /// </remarks>
    private async Task<string> ExecuteWorkflowAsync(
        TaskOrchestrationContext context,
        Workflow workflow,
        string initialInput,
        ILogger logger)
    {
        WorkflowExecutionPlan plan = WorkflowHelper.GetExecutionPlan(workflow);

        // Use superstep-based execution for all workflows
        // This approach naturally handles both DAGs and cyclic workflows
        return await this.RunSuperstepLoopAsync(context, workflow, plan, initialInput, logger).ConfigureAwait(true);
    }

    /// <summary>
    /// Runs the workflow execution loop using superstep-based processing.
    /// </summary>
    /// <remarks>
    /// Implements Bulk Synchronous Parallel (BSP) style execution where each superstep
    /// processes all pending messages for active executors in parallel. Terminates when
    /// no messages remain, halt is requested, or max supersteps reached.
    /// </remarks>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private async Task<string> RunSuperstepLoopAsync(
        TaskOrchestrationContext context,
        Workflow workflow,
        WorkflowExecutionPlan plan,
        string initialInput,
        ILogger logger)
    {
        const int MaxSupersteps = 100;

        SuperstepState state = new(workflow, plan);
        EnqueueMessage(state.MessageQueues, plan.StartExecutorId, initialInput, typeof(string).FullName);

        for (int superstep = 1; superstep <= MaxSupersteps; superstep++)
        {
            List<ExecutorInput> inputs = PrepareExecutorInputs(state, logger);
            if (inputs.Count == 0)
            {
                break;
            }

            logger.LogDebug("Superstep {Step}: {Count} active executor(s)", superstep, inputs.Count);

            // Dispatch all executors in parallel
            Task<string>[] tasks = inputs
                .Select(e => this.DispatchExecutorAsync(context, e.Info, e.Input, e.InputTypeName, logger, state.CustomStatus, state.SharedState))
                .ToArray();

            string[] results = await Task.WhenAll(tasks).ConfigureAwait(true);

            // Process results and route to successors
            string? haltOutput = ProcessSuperstepResults(inputs, results, state, logger);
            if (haltOutput is not null)
            {
                return haltOutput;
            }

            UpdateCustomStatus(context, state.CustomStatus);
        }

        return DetermineFinalResult(workflow, state.LastResults, state.CustomStatus);
    }

    /// <summary>
    /// Holds mutable state for superstep-based workflow execution.
    /// </summary>
    private sealed class SuperstepState(Workflow workflow, WorkflowExecutionPlan plan)
    {
        public WorkflowExecutionPlan Plan { get; } = plan;
        public Dictionary<string, ExecutorBinding> ExecutorBindings { get; } = workflow.ReflectExecutors();
        public Dictionary<string, Queue<(string Message, string? InputTypeName)>> MessageQueues { get; } = [];
        public Dictionary<string, string> LastResults { get; } = [];
        public Dictionary<string, string> SharedState { get; } = [];
        public DurableWorkflowCustomStatus CustomStatus { get; } = new();
    }

    /// <summary>
    /// Represents prepared input for an executor ready for dispatch.
    /// </summary>
    private sealed record ExecutorInput(string ExecutorId, string Input, string? InputTypeName, WorkflowExecutorInfo Info);

    /// <summary>
    /// Prepares inputs for all active executors, handling Fan-In aggregation.
    /// </summary>
    private static List<ExecutorInput> PrepareExecutorInputs(SuperstepState state, ILogger logger)
    {
        List<ExecutorInput> inputs = [];

        foreach ((string executorId, Queue<(string Message, string? InputTypeName)> queue) in state.MessageQueues)
        {
            if (queue.Count == 0)
            {
                continue;
            }

            bool isFanIn = state.Plan.Predecessors.TryGetValue(executorId, out List<string>? predecessors) && predecessors.Count > 1;
            (string input, string? inputTypeName) = isFanIn && queue.Count > 1
                ? AggregateQueueMessages(queue, executorId, logger)
                : queue.Dequeue();

            inputs.Add(new ExecutorInput(executorId, input, inputTypeName, CreateExecutorInfo(executorId, state.ExecutorBindings)));
        }

        return inputs;
    }

    /// <summary>
    /// Aggregates all messages in a queue into a JSON array for Fan-In executors.
    /// </summary>
    private static (string Input, string? TypeName) AggregateQueueMessages(
        Queue<(string Message, string? InputTypeName)> queue,
        string executorId,
        ILogger logger)
    {
        List<string> messages = [];
        while (queue.Count > 0)
        {
            messages.Add(queue.Dequeue().Message);
        }

        logger.LogDebug("Fan-In executor {ExecutorId}: aggregated {Count} messages", executorId, messages.Count);
        return (AggregateMessagesToJsonArray(messages), typeof(string[]).FullName);
    }

    /// <summary>
    /// Processes results from a superstep, updating state and routing messages.
    /// </summary>
    /// <returns>The halt output if halt was requested; otherwise null.</returns>
    private static string? ProcessSuperstepResults(
        List<ExecutorInput> inputs,
        string[] rawResults,
        SuperstepState state,
        ILogger logger)
    {
        for (int i = 0; i < inputs.Count; i++)
        {
            string executorId = inputs[i].ExecutorId;
            (string result, List<SentMessageInfo> sentMessages) = UnwrapActivityResult(rawResults[i], state.CustomStatus, state.SharedState);
            state.LastResults[executorId] = result;

            if (HasHaltBeenRequested(state.CustomStatus, executorId))
            {
                logger.LogDebug("Halt requested by executor {ExecutorId}", executorId);
                return result;
            }

            RouteExecutorOutput(executorId, result, sentMessages, state, logger);
        }

        return null;
    }

    /// <summary>
    /// Routes executor output (explicit messages or return value) to successors.
    /// </summary>
    private static void RouteExecutorOutput(
        string executorId,
        string result,
        List<SentMessageInfo> sentMessages,
        SuperstepState state,
        ILogger logger)
    {
        if (sentMessages.Count > 0)
        {
            foreach (SentMessageInfo msg in sentMessages)
            {
                if (!string.IsNullOrEmpty(msg.Message))
                {
                    RouteMessageToSuccessors(executorId, msg.Message, msg.TypeName, state.Plan, state.MessageQueues, logger);
                }
            }
        }
        else if (!string.IsNullOrEmpty(result))
        {
            RouteMessageToSuccessors(executorId, result, state.Plan, state.MessageQueues, logger);
        }
    }

    /// <summary>
    /// Aggregates multiple messages into a JSON array.
    /// </summary>
    /// <param name="messages">The messages to aggregate.</param>
    /// <returns>A JSON array string containing all messages.</returns>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing string array.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing string array.")]
    private static string AggregateMessagesToJsonArray(List<string> messages)
    {
        return JsonSerializer.Serialize(messages);
    }

    /// <summary>
    /// Enqueues a message to an executor's message queue with type information.
    /// </summary>
    /// <param name="queues">The dictionary of message queues, keyed by executor ID.</param>
    /// <param name="executorId">The target executor ID to queue the message for.</param>
    /// <param name="message">The serialized message content.</param>
    /// <param name="inputTypeName">The full type name of the message, used for deserialization hints.</param>
    /// <remarks>
    /// Creates a new queue for the executor if one doesn't exist. Messages are processed
    /// in FIFO order during each superstep.
    /// </remarks>
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
    /// Creates a <see cref="WorkflowExecutorInfo"/> for the given executor ID.
    /// </summary>
    /// <param name="executorId">The executor ID to look up.</param>
    /// <param name="executorBindings">The dictionary of executor bindings from the workflow.</param>
    /// <returns>A <see cref="WorkflowExecutorInfo"/> containing metadata about the executor.</returns>
    /// <exception cref="InvalidOperationException">Thrown when the executor ID is not found in bindings.</exception>
    /// <remarks>
    /// This method determines the executor type (agentic, sub-workflow, request port, or regular)
    /// and extracts the appropriate metadata for each type.
    /// </remarks>
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
        Workflow? subWorkflow = (binding is SubworkflowBinding swb) ? swb.WorkflowInstance : null;

        return new WorkflowExecutorInfo(executorId, isAgentic, requestPort, subWorkflow);
    }

    /// <summary>
    /// Checks if the workflow should halt based on halt request events.
    /// </summary>
    /// <param name="customStatus">The custom status containing accumulated workflow events.</param>
    /// <param name="executorId">The executor ID that just completed execution.</param>
    /// <returns><c>true</c> if a halt was requested; otherwise, <c>false</c>.</returns>
    /// <remarks>
    /// <para>
    /// Only <c>DurableHaltRequestedEvent</c> triggers a halt. Note that <c>YieldOutputAsync</c>
    /// does NOT halt the workflow - it just yields intermediate output that can be used as
    /// the final result if no other output is produced.
    /// </para>
    /// <para>
    /// Events are searched in reverse order (most recent first) for efficiency.
    /// </para>
    /// </remarks>
    private static bool HasHaltBeenRequested(
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
    /// <param name="sourceId">The source executor ID.</param>
    /// <param name="message">The serialized message to route.</param>
    /// <param name="plan">The workflow execution plan.</param>
    /// <param name="messageQueues">The message queues for each executor.</param>
    /// <param name="logger">The logger instance.</param>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static void RouteMessageToSuccessors(
        string sourceId,
        string message,
        WorkflowExecutionPlan plan,
        Dictionary<string, Queue<(string Message, string? InputTypeName)>> messageQueues,
        ILogger logger)
    {
        plan.ExecutorOutputTypes.TryGetValue(sourceId, out Type? sourceOutputType);
        RouteMessageToSuccessorsCore(sourceId, message, sourceOutputType?.FullName, sourceOutputType, plan, messageQueues, logger);
    }

    /// <summary>
    /// Routes a message through edges to successor executors, with an explicit type name.
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
        Type? messageType = !string.IsNullOrEmpty(explicitTypeName) ? Type.GetType(explicitTypeName) : null;
        string? inputTypeName = explicitTypeName;

        if (messageType is null && plan.ExecutorOutputTypes.TryGetValue(sourceId, out Type? sourceOutputType))
        {
            messageType = sourceOutputType;
            inputTypeName = sourceOutputType?.FullName;
        }

        RouteMessageToSuccessorsCore(sourceId, message, inputTypeName, messageType, plan, messageQueues, logger);
    }

    /// <summary>
    /// Core implementation for routing messages to successor executors.
    /// </summary>
    /// <param name="sourceId">The source executor ID that produced the message.</param>
    /// <param name="message">The serialized message content to route.</param>
    /// <param name="inputTypeName">The type name to pass to successors for deserialization.</param>
    /// <param name="messageType">The resolved <see cref="Type"/> for edge condition evaluation.</param>
    /// <param name="plan">The workflow execution plan containing the graph structure.</param>
    /// <param name="messageQueues">The message queues to enqueue messages into.</param>
    /// <param name="logger">The logger for debug output.</param>
    /// <remarks>
    /// For each successor of the source executor, this method:
    /// <list type="number">
    /// <item><description>Evaluates the edge condition (if any)</description></item>
    /// <item><description>Enqueues the message if the condition passes or no condition exists</description></item>
    /// </list>
    /// </remarks>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static void RouteMessageToSuccessorsCore(
        string sourceId,
        string message,
        string? inputTypeName,
        Type? messageType,
        WorkflowExecutionPlan plan,
        Dictionary<string, Queue<(string Message, string? InputTypeName)>> messageQueues,
        ILogger logger)
    {
        if (!plan.Successors.TryGetValue(sourceId, out List<string>? successors))
        {
            return;
        }

        foreach (string sinkId in successors)
        {
            if (!TryEvaluateEdgeCondition(sourceId, sinkId, message, messageType, plan, logger))
            {
                continue;
            }

            logger.LogDebug("Edge {Source} -> {Sink}: routing message", sourceId, sinkId);
            EnqueueMessage(messageQueues, sinkId, message, inputTypeName);
        }
    }

    /// <summary>
    /// Evaluates an edge condition if one exists for the given source-sink pair.
    /// </summary>
    /// <param name="sourceId">The source executor ID.</param>
    /// <param name="sinkId">The target (sink) executor ID.</param>
    /// <param name="message">The serialized message to evaluate.</param>
    /// <param name="messageType">The type to deserialize the message to for condition evaluation.</param>
    /// <param name="plan">The execution plan containing edge conditions.</param>
    /// <param name="logger">The logger for debug/warning output.</param>
    /// <returns>
    /// <c>true</c> if the message should be routed (no condition exists or condition passed);
    /// <c>false</c> if the condition returned false or evaluation failed.
    /// </returns>
    /// <remarks>
    /// Edge conditions are user-defined predicates that filter which messages flow through an edge.
    /// If evaluation throws an exception, the edge is skipped (fail-safe behavior) and a warning is logged.
    /// </remarks>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static bool TryEvaluateEdgeCondition(
        string sourceId,
        string sinkId,
        string message,
        Type? messageType,
        WorkflowExecutionPlan plan,
        ILogger logger)
    {
        if (!plan.EdgeConditions.TryGetValue((sourceId, sinkId), out Func<object?, bool>? condition) || condition is null)
        {
            return true;
        }

        try
        {
            object? messageObj = DeserializeMessageForCondition(message, messageType);
            if (!condition(messageObj))
            {
                logger.LogDebug("Edge {Source} -> {Sink}: condition returned false, skipping", sourceId, sinkId);
                return false;
            }

            return true;
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to evaluate condition for edge {Source} -> {Sink}, skipping", sourceId, sinkId);
            return false;
        }
    }

    /// <summary>
    /// Determines the final result for a workflow execution.
    /// </summary>
    /// <param name="workflow">The workflow definition.</param>
    /// <param name="lastResults">Dictionary of last results from each executor.</param>
    /// <param name="customStatus">The custom status containing workflow events.</param>
    /// <returns>The final workflow result string.</returns>
    /// <remarks>
    /// <para>
    /// Result priority (highest to lowest):
    /// </para>
    /// <list type="number">
    /// <item><description>Most recent <c>YieldOutputAsync</c> call (explicit workflow output)</description></item>
    /// <item><description>Results from designated output executors (via <c>WithOutputFrom</c>)</description></item>
    /// <item><description>Last non-empty result from any executor</description></item>
    /// </list>
    /// <para>
    /// If multiple output executors are defined, their results are joined with <c>\n---\n</c>.
    /// </para>
    /// </remarks>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing event types.")]
    private static string DetermineFinalResult(
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
    /// <param name="customStatus">The custom status containing serialized workflow events.</param>
    /// <returns>The yielded output string, or <c>null</c> if no yield event was found.</returns>
    /// <remarks>
    /// <para>
    /// Searches for <c>DurableYieldedOutputEvent</c> in reverse order (most recent first).
    /// The event structure is:
    /// </para>
    /// <code>
    /// {
    ///   "TypeName": "...DurableYieldedOutputEvent...",
    ///   "Data": "{\"Output\": \"actual output value\"}"
    /// }
    /// </code>
    /// <para>
    /// The output can be either a string or a serialized object (returned as raw JSON).
    /// </para>
    /// </remarks>
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
    /// Unwraps an activity result, extracting state updates, events, sent messages, and the actual result.
    /// </summary>
    /// <param name="rawResult">The raw JSON string returned from the activity.</param>
    /// <param name="customStatus">The custom status to append events to.</param>
    /// <param name="sharedState">The shared state dictionary to apply updates to.</param>
    /// <returns>
    /// A tuple containing the executor's result and any messages sent via <c>SendMessageAsync</c>.
    /// </returns>
    /// <remarks>
    /// <para>
    /// Activities return a <see cref="DurableActivityOutput"/> wrapper containing:
    /// </para>
    /// <list type="bullet">
    /// <item><description><strong>Result:</strong> The serialized return value of the executor</description></item>
    /// <item><description><strong>StateUpdates:</strong> Key-value pairs to add/update/remove from shared state</description></item>
    /// <item><description><strong>ClearedScopes:</strong> Scope prefixes to bulk-remove from shared state</description></item>
    /// <item><description><strong>Events:</strong> Workflow events (yield, halt, etc.) to propagate</description></item>
    /// <item><description><strong>SentMessages:</strong> Messages sent via <c>SendMessageAsync</c></description></item>
    /// </list>
    /// <para>
    /// If the raw result is not a valid <see cref="DurableActivityOutput"/>, it's returned as-is
    /// (backward compatibility for activities that return plain values).
    /// </para>
    /// </remarks>
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
            DurableActivityOutput? output = JsonSerializer.Deserialize(rawResult, DurableWorkflowJsonContext.Default.DurableActivityOutput);

            if (output is null || !IsValidActivityOutput(output))
            {
                return (rawResult, []);
            }

            ApplyClearedScopes(output.ClearedScopes, sharedState);
            ApplyStateUpdates(output.StateUpdates, sharedState);

            if (output.Events.Count > 0)
            {
                customStatus.Events.AddRange(output.Events);
            }

            return (output.Result ?? string.Empty, output.SentMessages);
        }
        catch (JsonException)
        {
            return (rawResult, []);
        }
    }

    /// <summary>
    /// Checks if the deserialized output is a valid <see cref="DurableActivityOutput"/> (not just default values).
    /// </summary>
    /// <param name="output">The deserialized output to validate.</param>
    /// <returns><c>true</c> if the output has any meaningful content; otherwise, <c>false</c>.</returns>
    /// <remarks>
    /// This check distinguishes actual activity output from arbitrary JSON that happened to
    /// deserialize successfully but with all default/empty values.
    /// </remarks>
    private static bool IsValidActivityOutput(DurableActivityOutput output)
    {
        return output.Result is not null
            || output.StateUpdates.Count > 0
            || output.ClearedScopes.Count > 0
            || output.Events.Count > 0
            || output.SentMessages.Count > 0;
    }

    /// <summary>
    /// Clears all state entries matching the specified scopes.
    /// </summary>
    /// <param name="clearedScopes">The list of scope names to clear.</param>
    /// <param name="sharedState">The shared state dictionary to modify.</param>
    /// <remarks>
    /// <para>
    /// State keys are prefixed with their scope (e.g., <c>myScope:keyName</c>).
    /// The special scope <c>__default__</c> is used for keys without an explicit scope.
    /// </para>
    /// <para>
    /// Clearing a scope removes all keys that start with <c>{scope}:</c>.
    /// </para>
    /// </remarks>
    private static void ApplyClearedScopes(List<string> clearedScopes, Dictionary<string, string> sharedState)
    {
        foreach (string clearedScope in clearedScopes)
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
    }

    /// <summary>
    /// Applies state updates to the shared state dictionary.
    /// </summary>
    /// <param name="stateUpdates">The updates to apply (key -> value, where null value means delete).</param>
    /// <param name="sharedState">The shared state dictionary to modify.</param>
    /// <remarks>
    /// A <c>null</c> value in the updates dictionary signals that the key should be removed
    /// from the shared state, enabling executors to delete state entries.
    /// </remarks>
    private static void ApplyStateUpdates(Dictionary<string, string?> stateUpdates, Dictionary<string, string> sharedState)
    {
        foreach (KeyValuePair<string, string?> update in stateUpdates)
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
    }

    /// <summary>
    /// Updates the orchestration custom status with current events and pending event info.
    /// </summary>
    /// <param name="context">The orchestration context to set the status on.</param>
    /// <param name="customStatus">The custom status object containing events and pending event info.</param>
    /// <remarks>
    /// The custom status is visible in the Durable Task dashboard and can be queried via the
    /// Durable Task client. It includes:
    /// <list type="bullet">
    /// <item><description>Accumulated workflow events from all executors</description></item>
    /// <item><description>Pending external event info when waiting for human-in-the-loop input</description></item>
    /// </list>
    /// Only updates if there's meaningful content to report.
    /// </remarks>
    private static void UpdateCustomStatus(TaskOrchestrationContext context, DurableWorkflowCustomStatus customStatus)
    {
        // Only update if there are events or a pending event
        if (customStatus.Events.Count > 0 || customStatus.PendingEvent is not null)
        {
            context.SetCustomStatus(customStatus);
        }
    }

    /// <summary>
    /// Deserializes a JSON message string into an object for edge condition evaluation.
    /// </summary>
    /// <param name="json">The JSON string to deserialize.</param>
    /// <param name="targetType">The target type to deserialize to, or <c>null</c> to deserialize as <see cref="object"/>.</param>
    /// <returns>
    /// The deserialized object, or the original string if deserialization fails (graceful fallback).
    /// </returns>
    /// <remarks>
    /// This method is used to prepare the message for edge condition predicates.
    /// If the JSON is invalid, it returns the raw string to allow conditions to handle string inputs.
    /// </remarks>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static object? DeserializeMessageForCondition(string json, Type? targetType)
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

    /// <summary>
    /// Dispatches execution to the appropriate handler based on executor type.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method routes execution to the appropriate handler based on executor type:
    /// </para>
    /// <list type="bullet">
    /// <item>
    /// <description>
    /// <strong>Request Port Executors:</strong> Handled via <see cref="ExecuteRequestPortAsync"/>.
    /// Sets custom status and waits for an external event (human-in-the-loop).
    /// </description>
    /// </item>
    /// <item>
    /// <description>
    /// <strong>Sub-Workflow Executors:</strong> Executed as sub-orchestrations.
    /// The child workflow runs as a separate orchestration instance with its own instance ID.
    /// </description>
    /// </item>
    /// <item>
    /// <description>
    /// <strong>Regular Executors:</strong> Invoked as Durable Task activities. Input is wrapped
    /// with state and type information via <see cref="ActivityInputWithState"/>.
    /// </description>
    /// </item>
    /// <item>
    /// <description>
    /// <strong>Agent Executors:</strong> Handled via <see cref="ExecuteAgentAsync"/>.
    /// AI agents run through Durable Entities for stateful conversation management.
    /// </description>
    /// </item>
    /// </list>
    /// </remarks>
    private async Task<string> DispatchExecutorAsync(
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

        // Handle Sub-Workflow executors by calling as sub-orchestrations
        if (executorInfo.IsSubworkflowExecutor)
        {
            return await ExecuteSubWorkflowAsync(context, executorInfo, input, logger).ConfigureAwait(true);
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

            string wrappedInput = JsonSerializer.Serialize(inputWithState, DurableWorkflowJsonContext.Default.ActivityInputWithState);
            return await context.CallActivityAsync<string>(triggerName, wrappedInput).ConfigureAwait(true);
        }

        return await ExecuteAgentAsync(context, executorInfo, input, logger).ConfigureAwait(true);
    }

    /// <summary>
    /// Executes a sub-workflow as a sub-orchestration.
    /// </summary>
    /// <param name="context">The orchestration context for calling sub-orchestrations.</param>
    /// <param name="executorInfo">The executor info containing the sub-workflow reference.</param>
    /// <param name="input">The input to pass to the sub-workflow.</param>
    /// <param name="logger">The logger for tracing.</param>
    /// <returns>The result of the sub-workflow execution.</returns>
    /// <remarks>
    /// <para>
    /// Sub-workflows are executed as separate orchestration instances.
    /// This provides:
    /// </para>
    /// <list type="bullet">
    /// <item><description>Separate instance ID for the child workflow (visible in dashboard)</description></item>
    /// <item><description>Independent checkpointing and replay</description></item>
    /// <item><description>Failure isolation (child failure doesn't corrupt parent state)</description></item>
    /// <item><description>Hierarchical visualization in the Durable Task dashboard</description></item>
    /// </list>
    /// </remarks>
    private static async Task<string> ExecuteSubWorkflowAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        ILogger logger)
    {
        Workflow subWorkflow = executorInfo.SubWorkflow!;
        string subOrchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(subWorkflow.Name!);

        logger.LogDebug(
            "Calling sub-orchestration '{SubOrchestrationName}' for sub-workflow '{SubWorkflowName}'",
            subOrchestrationName,
            subWorkflow.Name);

        // Call the sub-workflow as a sub-orchestration
        // The Durable Task Framework handles checkpointing, replay, and failure isolation
        string result = await context.CallSubOrchestratorAsync<string>(
            subOrchestrationName,
            input).ConfigureAwait(true);

        logger.LogDebug(
            "Sub-orchestration '{SubOrchestrationName}' completed with result length: {ResultLength}",
            subOrchestrationName,
            result?.Length ?? 0);

        return result ?? string.Empty;
    }

    /// <summary>
    /// Executes a request port executor by waiting for an external event (human-in-the-loop).
    /// </summary>
    /// <param name="context">The orchestration context for waiting on external events.</param>
    /// <param name="executorInfo">The executor info containing the request port configuration.</param>
    /// <param name="input">The input data that prompted this request (visible to the external actor).</param>
    /// <param name="logger">The logger for tracing.</param>
    /// <param name="customStatus">The custom status to update with pending event info.</param>
    /// <returns>The response string from the external actor.</returns>
    /// <remarks>
    /// <para>
    /// Request ports enable human-in-the-loop workflows. When a request port executor is reached:
    /// </para>
    /// <list type="number">
    /// <item><description>The custom status is updated with <see cref="PendingExternalEventStatus"/> including
    /// the event name, input, and expected request/response types.</description></item>
    /// <item><description>The orchestration waits for an external event with the port's ID as the event name.</description></item>
    /// <item><description>Once the event is received, the custom status is cleared and the response is returned.</description></item>
    /// </list>
    /// <para>
    /// External actors can query the custom status to discover what input is needed and raise
    /// the appropriate event via the Durable Task client.
    /// </para>
    /// </remarks>
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

    /// <summary>
    /// Executes an AI agent executor through Durable Entities.
    /// </summary>
    /// <param name="context">The orchestration context for entity communication.</param>
    /// <param name="executorInfo">The executor info containing the agent configuration.</param>
    /// <param name="input">The input/prompt to send to the AI agent.</param>
    /// <param name="logger">The logger for warnings.</param>
    /// <returns>The agent's response text.</returns>
    /// <remarks>
    /// <para>
    /// AI agents are stateful components that maintain conversation history and context.
    /// They are implemented using Durable Entities to persist their state across orchestration replays.
    /// </para>
    /// <para>
    /// Each agent invocation:
    /// </para>
    /// <list type="number">
    /// <item><description>Retrieves the agent proxy via <c>context.GetAgent()</c></description></item>
    /// <item><description>Creates a new thread for this conversation turn</description></item>
    /// <item><description>Runs the agent with the input and returns the response text</description></item>
    /// </list>
    /// <para>
    /// If the agent is not found (not registered in <see cref="DurableAgentsOptions"/>),
    /// an error message is returned instead of throwing.
    /// </para>
    /// </remarks>
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

/// <summary>
/// Wrapper for serialized workflow events that includes type information for proper deserialization.
/// </summary>
/// <remarks>
/// Workflow events (e.g., <c>DurableYieldedOutputEvent</c>, <c>DurableHaltRequestedEvent</c>) are
/// serialized with their type information so they can be properly deserialized and processed
/// by the orchestrator. This enables type-safe event handling across the activity boundary.
/// </remarks>
internal sealed class SerializedWorkflowEvent
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
/// <remarks>
/// <para>
/// This wrapper is serialized and passed to each activity execution. It contains:
/// </para>
/// <list type="bullet">
/// <item>
/// <description><strong>Input:</strong> The serialized message/data for the executor to process.</description>
/// </item>
/// <item>
/// <description>
/// <strong>InputTypeName:</strong> The full type name of the input, used to deserialize to the correct type.
/// This is especially important when an executor accepts multiple input types.
/// </description>
/// </item>
/// <item>
/// <description>
/// <strong>State:</strong> A snapshot of the shared workflow state at the time of execution.
/// Activities can read from and write to this state via <see cref="IWorkflowContext"/>.
/// </description>
/// </item>
/// </list>
/// </remarks>
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
