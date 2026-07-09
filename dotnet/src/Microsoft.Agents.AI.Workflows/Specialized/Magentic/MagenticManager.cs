// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.ExceptionServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Specialized.Magentic;

internal class MagenticManager(AIAgent managerAgent)
{
    private static async ValueTask<ChatMessage> CheckResponseAsync(Task<AgentResponse> responseTask, IWorkflowContext context, CancellationToken cancellationToken)
    {
        AgentResponse response = await responseTask.ConfigureAwait(false);

        if (response.Messages.Count == 0)
        {
            throw new InvalidOperationException("Planner Agent did not return any messages.");
        }

        if (response.Messages.Count > 1)
        {
            await context.AddEventAsync(new WorkflowWarningEvent("Planner Agent returned multiple messages; using the last one."), cancellationToken)
                         .ConfigureAwait(false);
        }

        return response.Messages[response.Messages.Count - 1];
    }

    private ValueTask<ChatMessage> InvokeAgentAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken, AgentSession? session = null)
        => CheckResponseAsync(managerAgent.RunAsync(messages, session, cancellationToken: cancellationToken), context, cancellationToken);

    public async ValueTask<TaskLedger> UpdatePlanAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken)
    {
        // If we already have a TaskLedger, we need to update the facts based on the existing factset; otherwise, we use the initial facts construction
        bool isReplan = taskContext.TaskLedger != null;

        AgentSession localSession = await managerAgent.CreateSessionAsync(cancellationToken).ConfigureAwait(false);

        ChatMessage factsRequest = new(ChatRole.User, isReplan ? taskContext.ToTaskLedgerFactsUpdatePrompt() : taskContext.ToTaskLedgerFactsPrompt());
        ChatMessage updatedFacts = await this.InvokeAgentAsync(
                                                messages: [.. taskContext.ChatHistory, factsRequest],
                                                context,
                                                cancellationToken,
                                                localSession)
                                             .ConfigureAwait(false);

        ChatMessage planRequest = new(ChatRole.User, isReplan ? taskContext.ToTaskLedgerPlanUpdatePrompt() : taskContext.ToTaskLedgerPlanPrompt());
        ChatMessage updatedPlan = await this.InvokeAgentAsync(
                                                // We rely on the AgentSession to maintain the context of the conversation, so we don't include the
                                                // history, facts request, or updated facts in the messages list.
                                                messages: [planRequest],
                                                context,
                                                cancellationToken,
                                                localSession)
                                             .ConfigureAwait(false);

        taskContext.ChatHistory.AddRange([factsRequest, updatedFacts, planRequest, updatedPlan]);

        return new(updatedFacts, updatedPlan);
    }

    public async ValueTask UpdateProgressLedgerAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken)
    {
        ChatMessage progressRequest = new(ChatRole.User, taskContext.ToProgressLedgerPrompt());

        ExceptionDispatchInfo? lastException = null;
        int maxRetryCount = taskContext.TaskLimits.MaxProgressLedgerRetryCount;
        for (int attempts = 0; attempts < maxRetryCount; attempts++)
        {
            ChatMessage progressUpdateMessage = await this.InvokeAgentAsync(
                                                              messages: [.. taskContext.ChatHistory, progressRequest],
                                                              context,
                                                              cancellationToken)
                                                           .ConfigureAwait(false);

            try
            {
                lastException = null;
                JsonElement stateUpdateJson = progressUpdateMessage.ExtractJson();
                if (!taskContext.ProgressLedger.TryUpdateState(stateUpdateJson))
                {
                    throw new InvalidOperationException("Could not answer progress ledger questions with provided JSON.");
                }

                break;
            }
            catch (Exception e)
            {
                lastException = ExceptionDispatchInfo.Capture(e);

                string warnString = $"Progress ledger JSON parse failed (attempt {attempts}/{maxRetryCount}): {e}";
                await context.AddEventAsync(new WorkflowWarningEvent(warnString), cancellationToken).ConfigureAwait(false);

                if (attempts < maxRetryCount)
                {
                    await Task.Delay(250 * attempts, cancellationToken).ConfigureAwait(false);
                }
            }
        }

        lastException?.Throw();
    }

    public async ValueTask<ChatMessage> PrepareFinalAnswerAsync(MagenticTaskContext taskContext, IWorkflowContext context, CancellationToken cancellationToken)
    {
        ChatMessage finalAnswerRequest = new(ChatRole.User, taskContext.ToFinalAnswerPrompt());
        ChatMessage finalAnswer = await this.InvokeAgentAsync([.. taskContext.ChatHistory, finalAnswerRequest], context, cancellationToken)
                                            .ConfigureAwait(false);

        return new(ChatRole.Assistant, finalAnswer.Text)
        {
            AuthorName = finalAnswer.AuthorName ?? nameof(MagenticManager),
            MessageId = finalAnswer.MessageId ?? Guid.NewGuid().ToString("N"),
            CreatedAt = finalAnswer.CreatedAt ?? DateTimeOffset.UtcNow,
            RawRepresentation = finalAnswer.RawRepresentation,
        };
    }
}
