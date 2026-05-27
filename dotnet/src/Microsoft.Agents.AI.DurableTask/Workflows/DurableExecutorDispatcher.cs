// Copyright (c) Microsoft. All rights reserved.

// ConfigureAwait Usage in Orchestration Code:
// This file uses ConfigureAwait(true) because it runs within orchestration context.
// Durable Task orchestrations require deterministic replay - the same code must execute
// identically across replays. ConfigureAwait(true) ensures continuations run on the
// orchestration's synchronization context, which is essential for replay correctness.
// Using ConfigureAwait(false) here could cause non-deterministic behavior during replay.

using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Dispatches workflow executors to activities, AI agents, sub-orchestrations, or external events (human-in-the-loop).
/// </summary>
/// <remarks>
/// Called during the dispatch phase of each superstep by
/// <c>DurableWorkflowRunner.DispatchExecutorsInParallelAsync</c>. For each executor that has
/// pending input, this dispatcher determines whether the executor is an AI agent (stateful,
/// backed by Durable Entities), a request port (human-in-the-loop, backed by external events),
/// a sub-workflow (dispatched as a sub-orchestration), or a regular activity, and invokes the
/// appropriate Durable Task API.
/// The serialised string result is returned to the runner for the routing phase.
/// </remarks>
internal static class DurableExecutorDispatcher
{
    /// <summary>
    /// Dispatches an executor based on its type (activity, AI agent, request port, or sub-workflow).
    /// </summary>
    /// <param name="context">The task orchestration context.</param>
    /// <param name="executorInfo">Information about the executor to dispatch.</param>
    /// <param name="envelope">The message envelope containing input and type information.</param>
    /// <param name="sharedState">The shared state dictionary to pass to the executor.</param>
    /// <param name="liveStatus">The live workflow status used to publish events and pending request port state.</param>
    /// <param name="logger">The logger for tracing.</param>
    /// <returns>The result from the executor.</returns>
    internal static async Task<string> DispatchAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        DurableMessageEnvelope envelope,
        Dictionary<string, string> sharedState,
        DurableWorkflowLiveStatus liveStatus,
        ILogger logger)
    {
        logger.LogDispatchingExecutor(executorInfo.ExecutorId, executorInfo.IsAgenticExecutor);

        if (executorInfo.IsRequestPortExecutor)
        {
            return await ExecuteRequestPortAsync(context, executorInfo, envelope.Message, liveStatus, logger).ConfigureAwait(true);
        }

        if (executorInfo.IsAgenticExecutor)
        {
            return await ExecuteAgentAsync(context, executorInfo, logger, envelope.Message).ConfigureAwait(true);
        }

        if (executorInfo.IsSubworkflowExecutor)
        {
            return await ExecuteSubWorkflowAsync(context, executorInfo, envelope.Message).ConfigureAwait(true);
        }

        return await ExecuteActivityAsync(context, executorInfo, envelope.Message, envelope.InputTypeName, sharedState).ConfigureAwait(true);
    }

    private static async Task<string> ExecuteActivityAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        string? inputTypeName,
        Dictionary<string, string> sharedState)
    {
        string executorName = WorkflowNamingHelper.GetExecutorName(executorInfo.ExecutorId);
        string activityName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);

        DurableActivityInput activityInput = new()
        {
            Input = input,
            InputTypeName = inputTypeName,
            State = sharedState
        };

        string serializedInput = JsonSerializer.Serialize(activityInput, DurableWorkflowJsonContext.Default.DurableActivityInput);

        return await context.CallActivityAsync<string>(activityName, serializedInput).ConfigureAwait(true);
    }

    /// <summary>
    /// Executes a request port executor by waiting for an external event (human-in-the-loop).
    /// </summary>
    /// <remarks>
    /// When the workflow reaches a <see cref="RequestPort"/> executor, the orchestration publishes
    /// the pending request to <see cref="DurableWorkflowLiveStatus"/> and waits for an external actor
    /// (e.g., a UI or API) to raise the corresponding event via
    /// <see cref="IStreamingWorkflowRun.SendResponseAsync{TResponse}(DurableWorkflowWaitingForInputEvent, TResponse, CancellationToken)"/>.
    /// Multiple RequestPorts may be dispatched in parallel during a fan-out superstep.
    /// Each adds its pending request to <see cref="DurableWorkflowLiveStatus.PendingEvents"/>.
    /// The wait has no built-in timeout; for time-limited approvals, callers can combine
    /// <c>context.CreateTimer</c> with <c>Task.WhenAny</c> in a wrapper executor.
    /// </remarks>
    private static async Task<string> ExecuteRequestPortAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        DurableWorkflowLiveStatus liveStatus,
        ILogger logger)
    {
        RequestPort requestPort = executorInfo.RequestPort!;
        string eventName = requestPort.Id;

        logger.LogWaitingForExternalEvent(eventName);

        // Publish pending request so external clients can discover what input is needed
        liveStatus.PendingEvents.Add(new PendingRequestPortStatus(EventName: eventName, Input: input));
        context.SetCustomStatus(liveStatus);

        // Wait until the external actor raises the event
        string response = await context.WaitForExternalEvent<string>(eventName).ConfigureAwait(true);

        // Remove this pending request after receiving the response
        liveStatus.PendingEvents.RemoveAll(p => p.EventName == eventName);
        context.SetCustomStatus(liveStatus.Events.Count > 0 || liveStatus.PendingEvents.Count > 0 ? liveStatus : null);

        logger.LogReceivedExternalEvent(eventName);

        return response;
    }

    /// <summary>
    /// Executes an AI agent executor through Durable Entities.
    /// </summary>
    /// <remarks>
    /// AI agents are stateful and maintain conversation history. They use Durable Entities
    /// to persist state across orchestration replays.
    /// </remarks>
    private static async Task<string> ExecuteAgentAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        ILogger logger,
        string input)
    {
        string agentName = WorkflowNamingHelper.GetExecutorName(executorInfo.ExecutorId);
        DurableAIAgent agent = context.GetAgent(agentName);

        if (agent is null)
        {
            logger.LogAgentNotFound(agentName);
            return $"Agent '{agentName}' not found";
        }

        AgentSession session = await agent.CreateSessionAsync().ConfigureAwait(true);
        AgentResponse response = await agent.RunAsync(input, session).ConfigureAwait(true);

        return response.Text;
    }

    /// <summary>
    /// Dispatches a sub-workflow executor as a sub-orchestration.
    /// </summary>
    /// <remarks>
    /// Sub-workflows run as separate orchestration instances, providing independent
    /// checkpointing, replay, and hierarchical visualization in the DTS dashboard.
    /// The input is wrapped in <see cref="DurableWorkflowInput{T}"/> so the sub-orchestration
    /// can extract it using the same envelope structure. The sub-orchestration returns a
    /// <see cref="DurableWorkflowResult"/> directly (deserialized by the Durable Task SDK),
    /// which this method converts to a <see cref="DurableExecutorOutput"/> so the parent
    /// workflow's result processing picks up both the result and any accumulated events.
    /// </remarks>
    private static async Task<string> ExecuteSubWorkflowAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input)
    {
        string orchestrationName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorInfo.SubWorkflow!.Name!);

        DurableWorkflowInput<string> workflowInput = new() { Input = input };

        DurableWorkflowResult? workflowResult = await context.CallSubOrchestratorAsync<DurableWorkflowResult?>(
            orchestrationName,
            workflowInput).ConfigureAwait(true);

        return ConvertWorkflowResultToExecutorOutput(workflowResult);
    }

    /// <summary>
    /// Converts a <see cref="DurableWorkflowResult"/> from a sub-orchestration
    /// into a <see cref="DurableExecutorOutput"/> JSON string. This bridges the sub-workflow's
    /// output format to the parent workflow's result processing, preserving both the result
    /// and any accumulated events from the sub-workflow.
    /// </summary>
    private static string ConvertWorkflowResultToExecutorOutput(DurableWorkflowResult? workflowResult)
    {
        if (workflowResult is null)
        {
            return string.Empty;
        }

        // Propagate the result, events, and sent messages from the sub-workflow.
        // SentMessages carry the sub-workflow's output for typed routing in the parent,
        // matching the in-process WorkflowHostExecutor behavior.
        // Shared state is not included because each workflow instance maintains its own
        // independent shared state; it is not shared between parent and sub-workflows.
        DurableExecutorOutput executorOutput = new()
        {
            Result = workflowResult.Result,
            Events = workflowResult.Events ?? [],
            SentMessages = workflowResult.SentMessages ?? [],
            HaltRequested = workflowResult.HaltRequested,
        };

        return JsonSerializer.Serialize(executorOutput, DurableWorkflowJsonContext.Default.DurableExecutorOutput);
    }
}
