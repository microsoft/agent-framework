// Copyright (c) Microsoft. All rights reserved.

// ConfigureAwait Usage in Orchestration Code:
// This file uses ConfigureAwait(true) because it runs within orchestration context.
// Durable Task orchestrations require deterministic replay - the same code must execute
// identically across replays. ConfigureAwait(true) ensures continuations run on the
// orchestration's synchronization context, which is essential for replay correctness.
// Using ConfigureAwait(false) here could cause non-deterministic behavior during replay.

using System.Text.Json;
using Microsoft.DurableTask;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Dispatches workflow executors to either activities or AI agents.
/// </summary>
internal static class DurableExecutorDispatcher
{
    /// <summary>
    /// Dispatches an executor based on its type (activity or AI agent).
    /// </summary>
    /// <param name="context">The task orchestration context.</param>
    /// <param name="executorInfo">Information about the executor to dispatch.</param>
    /// <param name="envelope">The message envelope containing input and type information.</param>
    /// <param name="logger">The logger for tracing.</param>
    /// <returns>The result from the executor.</returns>
    internal static async Task<string> DispatchAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        DurableMessageEnvelope envelope,
        ILogger logger)
    {
        logger.LogDispatchingExecutor(executorInfo.ExecutorId, executorInfo.IsAgenticExecutor);

        if (executorInfo.IsAgenticExecutor)
        {
            return await ExecuteAgentAsync(context, executorInfo, logger, envelope.Message).ConfigureAwait(true);
        }

        return await ExecuteActivityAsync(context, executorInfo, envelope.Message, envelope.InputTypeName).ConfigureAwait(true);
    }

    private static async Task<string> ExecuteActivityAsync(
        TaskOrchestrationContext context,
        WorkflowExecutorInfo executorInfo,
        string input,
        string? inputTypeName)
    {
        string executorName = WorkflowNamingHelper.GetExecutorName(executorInfo.ExecutorId);
        string activityName = WorkflowNamingHelper.ToOrchestrationFunctionName(executorName);

        DurableActivityInput activityInput = new()
        {
            Input = input,
            InputTypeName = inputTypeName
        };

        string serializedInput = JsonSerializer.Serialize(activityInput, DurableWorkflowJsonContext.Default.DurableActivityInput);

        return await context.CallActivityAsync<string>(activityName, serializedInput).ConfigureAwait(true);
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

        AgentSession session = await agent.GetNewSessionAsync().ConfigureAwait(true);
        AgentResponse response = await agent.RunAsync(input, session).ConfigureAwait(true);

        return response.Text;
    }
}
